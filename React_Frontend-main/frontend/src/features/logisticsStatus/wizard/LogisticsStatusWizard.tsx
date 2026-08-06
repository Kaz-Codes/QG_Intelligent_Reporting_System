import { useRef, useState } from 'react'
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
  getLogisticsOrder, updateLogisticsOrder, createLogisticsOrder,
  saveLogisticsDraft, getLogisticsDraft, isKnownLogisticsOrder,
  generateLogisticsSystemId, nextBatchNoForMo,
} from '@/lib/logisticsStatusData'
import { consignmentDraftSchema, DRAFT_DEFAULT_VALUES, WIZARD_STEPS, emptyItem, type LogisticsDraft } from '../schema'
import { WizardStepper } from './WizardStepper'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { Step1Order } from './steps/Step1Order'
import { Step2Packing } from './steps/Step2Packing'
import { Step3Shipping } from './steps/Step3Shipping'
import { Step4Expenditures } from './steps/Step4Expenditures'
import { Step5Status } from './steps/Step5Status'

const STEP_COMPONENTS = [
  Step1Order, Step2Packing, Step3Shipping, Step4Expenditures, Step5Status,
]

/** See the matching function in features/importsStatus/wizard/
 *  ImportsStatusWizard.tsx: normalizes undefined/null/'' to one canonical
 *  value before a dirty comparison, since a field silently materializes from
 *  its schema default to '' the moment its owning step's input mounts —
 *  without the user touching anything. */
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

/**
 * DRAFT_DEFAULT_VALUES is a single shared module-level object — its seed
 * item's id ("item-1") is a fixed literal, not generated per order. That's
 * harmless in isolation, but outstandingByItemAcrossMo now matches
 * allocations across sibling batches BY ITEM ID, so two unrelated brand-new
 * orders both starting from the same literal "item-1" would collide the
 * moment they share an MO: an allocation against one order's "item-1" would
 * incorrectly count against the other's. Regenerating the seed item's id
 * here (once per fresh /new session, not on every render — see the lazy
 * useState below) keeps every new order's starting item globally unique.
 */
function freshDraftDefaults(): LogisticsDraft {
  return { ...DRAFT_DEFAULT_VALUES, items: [emptyItem(`item-${crypto.randomUUID()}`)] }
}

export function LogisticsStatusWizard() {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()
  const [pendingStep, setPendingStep] = useState<number | null>(null)

  const currentStep = id ? Number(step) || 1 : 1
  const stepIndex = Math.min(Math.max(currentStep, 1), WIZARD_STEPS.length) - 1
  const stepDef = WIZARD_STEPS[stepIndex]
  const StepComponent = STEP_COMPONENTS[stepIndex]

  // Edit mode loads the existing order synchronously from the mock store —
  // see lib/logisticsStatusData.ts's getLogisticsOrder/updateLogisticsOrder.
  // Note: React Router does NOT remount this component between wizard steps
  // (only the `:step` route param changes, not the route element) — the same
  // `methods` instance is reused for the whole edit session on one order,
  // which is why the dirty-baseline resets in handleSaveAndMove/
  // handleDiscardAndMove below matter.
  const existingOrder = id ? getLogisticsOrder(id) : undefined
  // A not-yet-submitted new order still needs to survive the /new →
  // /:id/edit/2 remount (see commitNavigate below) — draft holds whatever
  // was persisted there via saveLogisticsDraft, distinct from a real,
  // submitted order in `existingOrder`.
  const draft = id ? getLogisticsDraft(id) : undefined
  // `!id` is only true on the very first page of the /new flow — Next mints
  // a real id and navigates to /:id/edit/2, at which point `!id` alone would
  // (wrongly) read as "editing an existing order" even though nothing has
  // been submitted yet. `isNew` has to check for an actual SUBMITTED record
  // (mirrors TruckingStatusWizard's `trulyNew` / isKnownRecord) — checking
  // "does getLogisticsOrder find it" instead would flip isNew to false the
  // moment the in-progress draft gets persisted for remount-survival, which
  // is exactly the bug this two-tier draft/real split avoids.
  const isNew = !id || !isKnownLogisticsOrder(id)

  // Computed once per mounted instance (lazy useState initializer) so the
  // SAME object seeds both useForm's defaultValues and the dirty baseline
  // below — calling freshDraftDefaults() separately in two places would mint
  // two different random item ids and make the form read as dirty on the
  // very first render.
  const [initialValues] = useState<LogisticsDraft>(() => existingOrder ?? draft ?? freshDraftDefaults())

  const methods = useForm<z.input<typeof consignmentDraftSchema>, unknown, LogisticsDraft>({
    resolver: zodResolver(consignmentDraftSchema),
    defaultValues: initialValues,
    mode: 'onBlur',
  })
  // Manual dirty tracking against a normalized baseline snapshot rather than
  // react-hook-form's own `formState.isDirty` — see the matching note in
  // features/importsStatus/wizard/ImportsStatusWizard.tsx.
  const baselineRef = useRef(snapshot(initialValues))
  const isFormDirty = () => snapshot(methods.getValues()) !== baselineRef.current

  // Same actions the list/detail views gate on — a viewer or a user without
  // create rights should never land on this route, hyperlink or not.
  const allowed = isNew ? can(user, 'enter') : can(user, 'editAny') || can(user, 'editOwnDraft')
  if (!allowed) return <Navigate to="/logistics-status" replace />

  function commitNavigate(clamped: number) {
    if (isNew) {
      if (clamped === 1) return
      // Reuse the id already in the URL once one exists — only the very
      // first Next (bare /new, no id yet) mints one. Minting a fresh id on
      // every step here would silently start a new, disconnected record
      // each time, since nothing would ever tie steps 2-5 back to step 1.
      let targetId = id
      if (!targetId) {
        // The system id is MO-based (see generateLogisticsSystemId), so
        // batchNo has to be resolved first. Step 1's own onBlur/onChange
        // handler already does this as the user types the MO number — this
        // is a defensive re-resolve right before minting, so correctness
        // doesn't depend on that handler having fired (e.g. clicking Next
        // without ever blurring the field).
        const values = methods.getValues()
        const resolvedBatchNo = nextBatchNoForMo(values.moNo ?? '')
        if (resolvedBatchNo !== values.batchNo) methods.setValue('batchNo', resolvedBatchNo)
        targetId = generateLogisticsSystemId(values.moNo, resolvedBatchNo)
      }
      // /new and /:id/edit/:step are separate <Route> entries (see App.tsx),
      // so this specific transition — and ONLY this one, since every later
      // step-to-step move matches the same :id/edit/:step route — genuinely
      // REMOUNTS the component. A fresh useForm() on that remount reads
      // DRAFT_DEFAULT_VALUES again (nothing findable via getLogisticsOrder
      // yet), silently discarding everything just typed on Step 1. Saving a
      // DRAFT here first — before navigating — means the remounted
      // instance's very first render finds it via getLogisticsDraft(id) and
      // seeds useForm's defaultValues from it instead. This deliberately
      // does NOT touch the real `ALL` store (createLogisticsOrder) — doing
      // so would flip isKnownLogisticsOrder(id) true prematurely, which
      // would in turn flip `isNew` false on the very next step and bring
      // back the unsaved-changes dialog for what is still an in-progress
      // creation.
      saveLogisticsDraft(targetId, methods.getValues() as LogisticsDraft)
      navigate(`/logistics-status/${targetId}/edit/${clamped}`)
    } else {
      navigate(`/logistics-status/${id}/edit/${clamped}`)
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
      // getValues() returns the resolver's INPUT type (fields with a zod
      // `.default()` are optional there); updateLogisticsOrder wants the
      // OUTPUT type. Safe to cast — those defaulted fields are always
      // populated once the form has mounted with defaultValues.
      // changedBy is threaded through so updateLogisticsOrder can log an RFD
      // audit event under the right name — see the comment there for why the
      // previous-value comparison has to happen in that function, not here.
      updateLogisticsOrder(id, values as LogisticsDraft, user?.name ?? 'Unknown')
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

  function onSubmit(data: LogisticsDraft) {
    // Edit mode: Submit is how the LAST step's edits get saved (there's no
    // further Next to trigger the unsaved-changes dialog) — without this,
    // e.g. checking "Send to Trucking" on Step 5 and clicking Submit would
    // silently discard it. New-record creation persists under the id minted
    // back on Step 1 — see createLogisticsOrder's comment for why reusing
    // that id (rather than generating a fresh one here) matters.
    if (id) {
      if (existingOrder) updateLogisticsOrder(id, data, user?.name ?? 'Unknown')
      else createLogisticsOrder(id, data)
    }
    navigate(id ? `/logistics-status/${id}` : '/logistics-status')
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={isNew ? 'New Logistics Order' : `Edit Logistics Order ${id}`}
        subtitle={`Step ${stepDef.step} of ${WIZARD_STEPS.length} — ${stepDef.label}`}
        module="logisticsStatus"
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
