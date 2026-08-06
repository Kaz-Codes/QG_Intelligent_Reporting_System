import { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { FormProvider, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import type { z } from 'zod'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  DRAFT_DEFAULT_VALUES,
  WIZARD_STEPS,
  truckingDraftSchema,
  type TruckingDraft,
} from '../schema'
import { getTruckingJob, isKnownRecord, updateTruckingJob } from '@/lib/truckingStatusData'
import { WizardStepper } from './WizardStepper'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { Step1Movement } from './steps/Step1Movement'
import { Step2Vehicles } from './steps/Step2Vehicles'
import { Step3Freight } from './steps/Step3Freight'
import { Step4Tracking } from './steps/Step4Tracking'

const STEP_COMPONENTS = [Step1Movement, Step2Vehicles, Step3Freight, Step4Tracking]

/**
 * Mirrors the edit-mode behavior established for importsStatus/logisticsStatus:
 *   - edit mode (:id present) loads the existing record into defaultValues;
 *   - stepper steps are freely clickable in edit mode, gated by Next-validation
 *     in new mode;
 *   - a dirty-form guard shows a 3-option dialog on navigation away.
 *
 * Dirtiness is tracked manually against a normalized snapshot (undefined / null
 * / '' treated as equal) rather than react-hook-form's isDirty, to avoid the
 * proxy/empty-string false-positive that bit the other two modules. Claude Code
 * should reconcile the exact snapshot helper with whatever those modules now use
 * so all three share one implementation.
 */
export function TruckingStatusWizard() {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()
  const isNew = !id

  const currentStep = isNew ? 1 : Number(step) || 1
  const stepIndex = Math.min(Math.max(currentStep, 1), WIZARD_STEPS.length) - 1
  const stepDef = WIZARD_STEPS[stepIndex]
  const StepComponent = STEP_COMPONENTS[stepIndex]

  const existing = useMemo(() => (id ? getTruckingJob(id) : undefined), [id])
  // `isNew` (no :id at all) is only true on the very first page of the /new
  // flow — Next mints a real id and navigates to /:id/edit/2, at which point
  // `isNew` alone would (wrongly) read as "editing an existing job" even
  // though nothing has been submitted yet.
  //
  // `/new` → `/:id/edit/2` is a route CHANGE (different <Route> match, same
  // component), so this component genuinely remounts on that transition —
  // whatever was typed on step 1 would be silently lost unless it's
  // persisted first (see navToStep below). `isKnownRecord` — not
  // `!!existing` — is what decides new-vs-edit mode: a mid-creation draft
  // gets persisted (so `existing` is truthy and step-1 data survives the
  // remount) but must still behave like new mode — sequential
  // Next-validation, no free stepper jumps, no dirty guard — all the way to
  // Submit, since it isn't a real record yet (`isKnownRecord` only looks at
  // manual jobs and live-derived rows, never the in-progress-draft cache).
  const trulyNew = !id || !isKnownRecord(id)

  // takenSnapshot (and a couple of other fields) carry a zod `.default()`,
  // which makes the resolver's INPUT type diverge from TruckingDraft (the
  // OUTPUT type) — same divergence already fixed the same way in
  // importsStatus/logisticsStatus's wizards; see the note there.
  const methods = useForm<z.input<typeof truckingDraftSchema>, unknown, TruckingDraft>({
    resolver: zodResolver(truckingDraftSchema),
    defaultValues: DRAFT_DEFAULT_VALUES,
    mode: 'onBlur',
  })

  // Load the existing record once it's resolved (edit mode). reset() re-baselines
  // the form so the dirty snapshot below starts from the loaded values.
  const snapshotRef = useRef<string>('')
  useEffect(() => {
    if (existing) {
      methods.reset(existing)
      snapshotRef.current = JSON.stringify(normalize(existing))
    } else {
      snapshotRef.current = JSON.stringify(normalize(DRAFT_DEFAULT_VALUES))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing])

  const [pendingNav, setPendingNav] = useState<number | null>(null)

  const allowed = trulyNew ? can(user, 'enter') : can(user, 'editAny') || can(user, 'editOwnDraft')
  if (!allowed) return <Navigate to="/trucking-status" replace />

  function isDirty(): boolean {
    const current = JSON.stringify(normalize(methods.getValues()))
    return current !== snapshotRef.current
  }

  function rebaseline() {
    snapshotRef.current = JSON.stringify(normalize(methods.getValues()))
  }

  async function navToStep(nextStep: number) {
    const clamped = Math.min(Math.max(nextStep, 1), WIZARD_STEPS.length)
    if (trulyNew) {
      // Whole creation flow (from the id-less /new page through every step
      // until Submit actually persists it) keeps Next-validation gating.
      const valid = await methods.trigger(stepDef.fields)
      if (!valid) return
      const targetId = id ?? crypto.randomUUID()
      if (!id && clamped === 1) return
      // Persist under targetId before navigating: the step change is a real
      // remount (see the trulyNew comment above), so without this, whatever
      // was just filled in would vanish the moment the next step's fresh
      // useForm mounts with DRAFT_DEFAULT_VALUES instead.
      // getValues() returns the resolver's INPUT type (fields with a zod
      // `.default()` are optional there); updateTruckingJob wants the OUTPUT
      // type. Safe to cast — those defaulted fields are always populated
      // once the form has mounted with defaultValues.
      updateTruckingJob(targetId, methods.getValues() as TruckingDraft)
      navigate(`/trucking-status/${targetId}/edit/${clamped}`)
      return
    }
    navigate(`/trucking-status/${id}/edit/${clamped}`)
  }

  // Entry point for both the Back/Next buttons and (in edit mode) stepper clicks.
  function requestNav(nextStep: number) {
    if (!trulyNew && isDirty()) {
      setPendingNav(nextStep)
      return
    }
    void navToStep(nextStep)
  }

  function onDialogSaveAndMove() {
    if (id) updateTruckingJob(id, methods.getValues() as TruckingDraft)
    rebaseline()
    const target = pendingNav
    setPendingNav(null)
    if (target != null) void navToStep(target)
  }

  function onDialogMoveWithout() {
    // Discard this step's edits: restore to the last baseline, then navigate.
    if (existing) methods.reset(existing)
    rebaseline()
    const target = pendingNav
    setPendingNav(null)
    if (target != null) void navToStep(target)
  }

  function onSubmit(data: TruckingDraft) {
    if (id) updateTruckingJob(id, data)
    else console.log('submit trucking draft', data) // placeholder until API exists
    navigate(id ? `/trucking-status/${id}` : '/trucking-status')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={trulyNew ? 'New Trucking Job' : `Edit Trucking Job ${id}`}
        subtitle={`Step ${stepDef.step} of ${WIZARD_STEPS.length} — ${stepDef.label}`}
        module="truckingStatus"
      />

      <WizardStepper
        steps={WIZARD_STEPS}
        current={stepDef.step}
        clickable={!trulyNew}
        onStepClick={(s) => requestNav(s)}
      />

      <Card>
        <CardContent className="p-6">
          <FormProvider {...methods}>
            <form onSubmit={methods.handleSubmit(onSubmit)}>
              <StepComponent />

              <div className="mt-6 flex justify-between">
                <Button
                  type="button"
                  variant="outline"
                  disabled={stepDef.step === 1}
                  onClick={() => requestNav(stepDef.step - 1)}
                >
                  Back
                </Button>
                {stepDef.step < WIZARD_STEPS.length ? (
                  <Button type="button" onClick={() => requestNav(stepDef.step + 1)}>
                    Next
                  </Button>
                ) : (
                  <Button type="submit">Submit</Button>
                )}
              </div>
            </form>
          </FormProvider>
        </CardContent>
      </Card>

      <UnsavedChangesDialog
        open={pendingNav != null}
        onSaveAndMove={onDialogSaveAndMove}
        onMoveWithout={onDialogMoveWithout}
        onCancel={() => setPendingNav(null)}
      />
    </div>
  )
}

/** Normalize undefined/null/'' as equivalent so a field flipping undefined→''
 * on mount doesn't register as a user edit. Recurses into arrays/objects. */
function normalize(value: unknown): unknown {
  if (value == null || value === '') return null
  if (Array.isArray(value)) return value.map(normalize)
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = normalize(v)
    }
    return out
  }
  return value
}
