import { useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { FormProvider, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { getConsignmentDraft, updateConsignment } from '@/lib/importsStatusData'
import { consignmentDraftSchema, DRAFT_DEFAULT_VALUES, WIZARD_STEPS, type ConsignmentDraft } from '../schema'
import { WizardStepper } from './WizardStepper'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { Step1Consignment } from './steps/Step1Consignment'
import { Step2Finance } from './steps/Step2Finance'
import { Step3Shipping } from './steps/Step3Shipping'
import { Step4Payments } from './steps/Step4Payments'
import { Step5StatusRemarks } from './steps/Step5StatusRemarks'
import { Step6Clearance } from './steps/Step6Clearance'
import { Step7LandedCost } from './steps/Step7LandedCost'

const STEP_COMPONENTS = [
  Step1Consignment, Step2Finance, Step3Shipping, Step4Payments,
  Step5StatusRemarks, Step6Clearance, Step7LandedCost,
]

/**
 * A field that's never been keyed in starts life as `undefined` (see
 * schema.ts's `optionalNumber`/`emptyItem`). But once the wizard step that
 * registers that field mounts — even without the user typing anything — its
 * native input's naturally-empty DOM value (`''`) gets synced into
 * react-hook-form, silently turning `undefined` into `''`. That's invisible
 * to the user but not to a raw JSON comparison, so both react-hook-form's
 * own `isDirty` and a naive manual diff flag a step as "edited" just for
 * having been visited. Normalizing undefined/null/'' to one canonical value
 * before comparing is what makes the dirty-guard only fire on real edits.
 */
function normalizeForDirtyCheck(value: unknown): unknown {
  if (value === undefined || value === null || value === '') return null
  if (Array.isArray(value)) return value.map(normalizeForDirtyCheck)
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = normalizeForDirtyCheck(v)
    return out
  }
  return value
}
const snapshot = (v: unknown) => JSON.stringify(normalizeForDirtyCheck(v))

export function ImportsStatusWizard() {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()
  const isNew = !id
  const [pendingStep, setPendingStep] = useState<number | null>(null)

  const currentStep = isNew ? 1 : Number(step) || 1
  const stepIndex = Math.min(Math.max(currentStep, 1), WIZARD_STEPS.length) - 1
  const stepDef = WIZARD_STEPS[stepIndex]
  const StepComponent = STEP_COMPONENTS[stepIndex]

  // Edit mode loads the existing record synchronously from the mock store —
  // no loading state needed since it's in-memory. New mode always starts
  // blank. `useForm` only reads `defaultValues` on the very first render;
  // that's fine for the very first step landed on, but note that React
  // Router does NOT remount this component between wizard steps (only the
  // `:step` route param changes, not the route element) — the same `methods`
  // instance is reused across the whole edit session for one record, which
  // is exactly why the dirty-baseline resets in handleSaveAndMove/
  // handleDiscardAndMove below matter. See lib/importsStatusData.ts's
  // getConsignmentDraft/updateConsignment.
  const existingDraft = id ? getConsignmentDraft(id) : undefined

  const methods = useForm<ConsignmentDraft>({
    resolver: zodResolver(consignmentDraftSchema),
    defaultValues: existingDraft ?? DRAFT_DEFAULT_VALUES,
    mode: 'onBlur',
  })
  // react-hook-form's own `formState.isDirty` gets stuck `true` after a
  // `reset()`, because visiting a step "materializes" that step's
  // never-been-touched fields from `undefined` to `''` just by mounting —
  // see normalizeForDirtyCheck above. Tracking dirtiness manually against a
  // normalized baseline snapshot sidesteps that rather than fighting it.
  const baselineRef = useRef(snapshot(existingDraft ?? DRAFT_DEFAULT_VALUES))
  const isFormDirty = () => snapshot(methods.getValues()) !== baselineRef.current

  // Same actions the list/detail views gate on — a viewer or a user without
  // create rights should never land on this route, hyperlink or not.
  const allowed = isNew ? can(user, 'enter') : can(user, 'editAny') || can(user, 'editOwnDraft')
  if (!allowed) return <Navigate to="/imports-status" replace />

  function commitNavigate(clamped: number) {
    if (isNew) {
      if (clamped === 1) return
      // Placeholder: a real step-1 submit would return the new consignment's
      // id from the API. Steps 2-7 always live under /:id/edit/:step, so we
      // stand in a client-generated id until that API exists.
      navigate(`/imports-status/${crypto.randomUUID()}/edit/${clamped}`)
    } else {
      navigate(`/imports-status/${id}/edit/${clamped}`)
    }
  }

  async function goToStep(nextStep: number) {
    const clamped = Math.min(Math.max(nextStep, 1), WIZARD_STEPS.length)
    if (clamped === stepDef.step) return

    if (isNew) {
      // New-record mode is unchanged: gated behind the current step's fields
      // validating, since there's no existing record to jump around in yet.
      const valid = await methods.trigger(stepDef.fields)
      if (!valid) return
      commitNavigate(clamped)
      return
    }

    // Edit mode: free navigation, guarded only by unsaved changes.
    if (isFormDirty()) {
      setPendingStep(clamped)
      return
    }
    commitNavigate(clamped)
  }

  function handleSaveAndMove() {
    if (id && pendingStep !== null) {
      const values = methods.getValues()
      updateConsignment(id, values)
      // React Router keeps this component mounted across step navigation
      // (only the `:step` param changes, not the route element) — so the
      // dirty baseline has to move forward explicitly, or the guard fires
      // again for no reason on the very next navigation.
      baselineRef.current = snapshot(values)
      commitNavigate(pendingStep)
    }
    setPendingStep(null)
  }

  function handleDiscardAndMove() {
    // Same reasoning as above in reverse: since the wizard doesn't remount
    // between steps, discarding has to actually revert the fields this step
    // owns — otherwise they'd still show the discarded edit if the user
    // navigates back to this step later in the session. Re-deriving the
    // baseline from the now-reverted values (rather than assuming it goes
    // back to matching baselineRef exactly) correctly leaves any other
    // steps' still-unsaved edits, if any, still flagged dirty.
    stepDef.fields.forEach((f) => methods.resetField(f))
    baselineRef.current = snapshot(methods.getValues())
    if (pendingStep !== null) commitNavigate(pendingStep)
    setPendingStep(null)
  }

  function handleCancelNavigate() {
    setPendingStep(null)
  }

  function onSubmit(data: ConsignmentDraft) {
    // Placeholder: wire up to the real API once it exists.
    console.log('submit consignment draft', data)
    navigate(id ? `/imports-status/${id}` : '/imports-status')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={isNew ? 'New Consignment' : `Edit Consignment ${id}`}
        subtitle={`Step ${stepDef.step} of ${WIZARD_STEPS.length} — ${stepDef.label}`}
        module="importsStatus"
      />

      <WizardStepper steps={WIZARD_STEPS} current={stepDef.step} onStepClick={isNew ? undefined : goToStep} />

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
                  onClick={() => goToStep(stepDef.step - 1)}
                >
                  Back
                </Button>
                {stepDef.step < WIZARD_STEPS.length ? (
                  <Button type="button" onClick={() => goToStep(stepDef.step + 1)}>
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
        open={pendingStep !== null}
        onSaveAndMove={handleSaveAndMove}
        onDiscardAndMove={handleDiscardAndMove}
        onCancel={handleCancelNavigate}
      />
    </div>
  )
}
