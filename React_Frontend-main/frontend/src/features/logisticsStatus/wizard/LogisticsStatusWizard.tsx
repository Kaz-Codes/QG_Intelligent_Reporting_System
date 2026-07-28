import { useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { FormProvider, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { getLogisticsOrder, updateLogisticsOrder } from '@/lib/logisticsStatusData'
import { consignmentDraftSchema, DRAFT_DEFAULT_VALUES, WIZARD_STEPS, type LogisticsDraft } from '../schema'
import { WizardStepper } from './WizardStepper'
import { UnsavedChangesDialog } from './UnsavedChangesDialog'
import { Step1Order } from './steps/Step1Order'
import { Step2Transportation } from './steps/Step2Transportation'
import { Step3Shipping } from './steps/Step3Shipping'
import { Step4Expenditures } from './steps/Step4Expenditures'
import { Step5Status } from './steps/Step5Status'

const STEP_COMPONENTS = [
  Step1Order, Step2Transportation, Step3Shipping, Step4Expenditures, Step5Status,
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

export function LogisticsStatusWizard() {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()
  const isNew = !id
  const [pendingStep, setPendingStep] = useState<number | null>(null)

  const currentStep = isNew ? 1 : Number(step) || 1
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

  const methods = useForm<LogisticsDraft>({
    resolver: zodResolver(consignmentDraftSchema),
    defaultValues: existingOrder ?? DRAFT_DEFAULT_VALUES,
    mode: 'onBlur',
  })
  // Manual dirty tracking against a normalized baseline snapshot rather than
  // react-hook-form's own `formState.isDirty` — see the matching note in
  // features/importsStatus/wizard/ImportsStatusWizard.tsx.
  const baselineRef = useRef(snapshot(existingOrder ?? DRAFT_DEFAULT_VALUES))
  const isFormDirty = () => snapshot(methods.getValues()) !== baselineRef.current

  // Same actions the list/detail views gate on — a viewer or a user without
  // create rights should never land on this route, hyperlink or not.
  const allowed = isNew ? can(user, 'enter') : can(user, 'editAny') || can(user, 'editOwnDraft')
  if (!allowed) return <Navigate to="/logistics-status" replace />

  function commitNavigate(clamped: number) {
    if (isNew) {
      if (clamped === 1) return
      // Placeholder: a real step-1 submit would return the new order's id from
      // the API. Steps 2-5 always live under /:id/edit/:step, so we stand in a
      // client-generated id until that API exists.
      navigate(`/logistics-status/${crypto.randomUUID()}/edit/${clamped}`)
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
      updateLogisticsOrder(id, values)
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
    // Placeholder: wire up to the real API once it exists.
    console.log('submit logistics draft', data)
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
