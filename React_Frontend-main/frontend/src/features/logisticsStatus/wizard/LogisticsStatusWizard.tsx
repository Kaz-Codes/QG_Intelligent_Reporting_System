import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { FormProvider, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import type { z } from 'zod'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { ApiError } from '@/lib/api/client'
import {
  getLogisticsOrder, createLogisticsOrder, updateLogisticsOrder, submitLogisticsOrder,
  parseSubmitErrors, type LogisticsPayload,
} from '@/lib/api/logistics'
import { apiToDraft, draftToPayload, remapNewChildIds } from '@/lib/api/logisticsMap'
import {
  consignmentDraftSchema, DRAFT_DEFAULT_VALUES, WIZARD_STEPS, emptyItem,
  submitRequirements,
  type LogisticsDraft, type JobKind,
} from '../schema'
import { SubmitRequirements } from '@/components/SubmitRequirements'
import { requirementsTooltip } from '@/lib/submitRequirements'
import { WizardStepper } from '@/components/ui/WizardStepper'
import { useStepNavigation } from '@/lib/useStepNavigation'
import { Step1Order } from './steps/Step1Order'
import { Step2Packing } from './steps/Step2Packing'
import { Step3Shipping } from './steps/Step3Shipping'
import { Step4Expenditures } from './steps/Step4Expenditures'
import { Step5Status } from './steps/Step5Status'
import { uuid } from '@/lib/uuid'

const STEP_COMPONENTS = [
  Step1Order, Step2Packing, Step3Shipping, Step4Expenditures, Step5Status,
]

/** "Delivered" is the terminal status; reaching it on a SUBMIT closes the
 *  order (helpers.is_closed = Delivered AND submitted). */
const CLOSED_STATUS = 'Delivered'

function freshDraftDefaults(jobKind: JobKind = 'standard'): LogisticsDraft {
  return { ...DRAFT_DEFAULT_VALUES, jobKind, items: [emptyItem(`item-${uuid()}`)] }
}

/**
 * Logistics Status wizard — ORDERS wired to the live backend.
 *
 * Same shape as the imports and trucking wizards, and for the same reasons:
 *
 *  - Back and "Save and Next" always save the current form state first (POST
 *    the first time, PUT after) and only move once that succeeds.
 *  - Clicking a STEP PILL is different: via useStepNavigation/WizardStepper
 *    (shared with imports and trucking), it jumps there directly with no save
 *    if the form is clean, and otherwise asks whether to save first or move
 *    without saving — the "Unsaved changes" dialog below.
 *  - SUBMIT sits on every step, not just the last. It saves, then calls the
 *    strict /submit endpoint, which reports back anything still missing.
 *  - A CLOSED order is read-only. Only /submit can close one (Delivered AND
 *    submitted), so the confirmation fires on Submit alone — a draft save that
 *    merely sets the status to Delivered closes nothing, and stepping between
 *    steps never runs that confirmation either (only Submit does, unchanged).
 *
 * react-hook-form holds ONE draft across all five steps (this component is not
 * remounted between them — only the `:step` param changes), so every save
 * sends the FULL draft. That is required for correctness: the update route
 * diffs children against what it has, and a line missing from the payload
 * reads as deleted.
 *
 * BOTH JOB KINDS use this one component and the same endpoints. A customer-
 * rework job is structurally an order — same items, packing, shipping,
 * expenditures and status — so it is stored in the same table with
 * `job_kind: 'rework'` as the discriminator, and gets change history, submit
 * and the closed lock for free.
 *
 * `jobKind` is never a form field. It comes from the route ("New Logistics
 * Order" vs "New Rework Job"), is sent on create, and is IGNORED by the
 * update route — so a save can't move a record between the Orders and
 * Service Jobs tabs. On an existing record it is read from the server, not
 * from `initialJobKind`.
 */
export function LogisticsStatusWizard({ initialJobKind = 'standard' }: { initialJobKind?: JobKind } = {}) {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()

  const currentStep = id ? Number(step) || 1 : 1
  const stepIndex = Math.min(Math.max(currentStep, 1), WIZARD_STEPS.length) - 1
  const stepDef = WIZARD_STEPS[stepIndex]
  const StepComponent = STEP_COMPONENTS[stepIndex]

  const [initialValues] = useState<LogisticsDraft>(() => freshDraftDefaults(initialJobKind))
  // What KIND of record this is. Seeded from the route for a brand-new one and
  // overwritten by the server once an existing record loads — the URL says
  // nothing about the kind when editing (/logistics-status/:id/edit/:step is
  // shared), so trusting `initialJobKind` there would mislabel every rework
  // job opened for editing.
  const [jobKind, setJobKind] = useState<JobKind>(initialJobKind)

  const methods = useForm<z.input<typeof consignmentDraftSchema>, unknown, LogisticsDraft>({
    resolver: zodResolver(consignmentDraftSchema),
    defaultValues: initialValues,
    mode: 'onBlur',
  })

  // --- loading the existing order (edit mode, standard orders only) ---
  const [orderId, setOrderId] = useState<number | null>(id ? Number(id) : null)
  const [loadingRecord, setLoadingRecord] = useState(!!id)
  const [notFound, setNotFound] = useState(false)
  const [loadErrorMsg, setLoadErrorMsg] = useState<string | null>(null)
  const [isLocked, setIsLocked] = useState(false)
  const [recordState, setRecordState] = useState('draft')

  const loadRecord = useCallback(() => {
    if (!id) return
    setLoadingRecord(true)
    setNotFound(false)
    setLoadErrorMsg(null)
    getLogisticsOrder(id)
      .then((o) => {
        setOrderId(o.id)
        setIsLocked(o.is_locked)
        setRecordState(o.record_state ?? 'draft')
        setJobKind((o.job_kind ?? 'standard') as JobKind)
        methods.reset(apiToDraft(o))
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setLoadErrorMsg(err instanceof Error ? err.message : 'Could not load this order')
      })
      .finally(() => setLoadingRecord(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  useEffect(() => { loadRecord() }, [loadRecord])

  // --- saving ---
  const [saving, setSaving] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [saveErrorMsg, setSaveErrorMsg] = useState<string | null>(null)
  const [submitErrors, setSubmitErrors] = useState<string[] | null>(null)
  const [justSaved, setJustSaved] = useState(false)
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null)

  // navigateToStep/doGoToStep are defined below (hoisted function
  // declarations — referencing them here before their textual definition is
  // fine); this hook has to sit before the `allowed` early return like every
  // other hook in this component.
  const {
    goToStep, pendingStep, saveThenMove, moveWithoutSaving, cancelMove,
  } = useStepNavigation({
    currentStep: stepDef.step,
    totalSteps: WIZARD_STEPS.length,
    isDirty: methods.formState.isDirty,
    clearDirty: () => methods.reset(methods.getValues()),
    navigateToStep,
    saveAndNavigateToStep: (step) => doGoToStep(step),
  })

  const isNew = !orderId
  const allowed = isNew ? can(user, 'enter') : can(user, 'editAny') || can(user, 'editOwnDraft')
  if (!allowed) return <Navigate to="/logistics-status" replace />

  function buildPayload(): LogisticsPayload {
    return draftToPayload(methods.getValues() as LogisticsDraft)
  }

  /**
   * POST the first time, PUT after. Returns the saved id + whether that save
   * closed the order, or null (with saveErrorMsg set) on failure.
   */
  async function saveDraft(): Promise<{ id: number; isLocked: boolean } | null> {
    setSaving(true)
    setSaveErrorMsg(null)
    setSubmitErrors(null)
    try {
      const payload = buildPayload()
      const response = orderId
        ? await updateLogisticsOrder(orderId, payload)
        : await createLogisticsOrder(payload)

      if (!orderId) setOrderId(response.id)
      setRecordState(response.record_state ?? 'draft')
      setIsLocked(response.is_locked)

      // Rows that were brand-new now have real ids; adopt them (and repoint
      // any allocation that referenced their temporary uuid) so the NEXT save
      // updates them instead of inserting duplicates.
      const current = methods.getValues() as LogisticsDraft
      const remapped = remapNewChildIds(current, response)
      if (remapped !== current) {
        methods.setValue('items', remapped.items, { shouldDirty: false })
        methods.setValue('packages', remapped.packages, { shouldDirty: false })
        methods.setValue('containers', remapped.containers, { shouldDirty: false })
      }

      return { id: response.id, isLocked: response.is_locked }
    } catch (err) {
      setSaveErrorMsg(err instanceof Error ? err.message : 'Could not save')
      return null
    } finally {
      setSaving(false)
    }
  }

  /** Only a SUBMIT can close an order, so only Submit needs confirming. */
  function willClose(isSubmitAction: boolean): boolean {
    if (!isSubmitAction) return false
    const closing = methods.getValues('status') === CLOSED_STATUS
    const alreadyClosed = recordState === 'submitted' && isLocked
    return closing && !alreadyClosed
  }

  function runWithCloseConfirm(action: () => void, opts: { isSubmit?: boolean } = {}) {
    if (willClose(!!opts.isSubmit)) setPendingAction(() => action)
    else action()
  }

  function confirmClose() {
    const action = pendingAction
    setPendingAction(null)
    action?.()
  }

  /* ---- navigation ---- */

  /** Navigate to a step WITHOUT saving. For a brand-new unsaved order
   *  there's no id yet, so we can only move once it's been saved at least
   *  once. */
  function navigateToStep(clamped: number) {
    if (isNew) {
      void doGoToStep(clamped, true)
      return
    }
    navigate(`/logistics-status/${orderId}/edit/${clamped}`)
  }

  async function doGoToStep(clamped: number, keepDirtyReset = false) {
    const saved = await saveDraft()
    if (saved === null) return // error already shown; stay put
    if (keepDirtyReset) methods.reset(methods.getValues())
    // A save that closed the order leaves nothing further to edit — land on
    // the read-only detail view rather than an edit route that would bounce.
    navigate(saved.isLocked
      ? `/logistics-status/${saved.id}`
      : `/logistics-status/${saved.id}/edit/${clamped}`)
  }

  function handleSaveOnly() {
    void doHandleSaveOnly()
  }

  async function doHandleSaveOnly() {
    const saved = await saveDraft()
    if (saved === null) return
    setJustSaved(true)
    setTimeout(() => setJustSaved(false), 2000)
    if (isNew) navigate(`/logistics-status/${saved.id}/edit/${stepDef.step}`, { replace: true })
  }

  function handleSubmit() {
    runWithCloseConfirm(() => void doHandleSubmit(), { isSubmit: true })
  }

  async function doHandleSubmit() {
    const saved = await saveDraft()
    if (saved === null) return

    setSubmitting(true)
    setSubmitErrors(null)
    try {
      await submitLogisticsOrder(saved.id)
      // A rework job's home is the Service Jobs tab, not the order book — so
      // a freshly submitted one lands back there with its filter applied,
      // rather than on a detail page the user would have to navigate out of.
      navigate(jobKind === 'rework'
        ? '/logistics-status?tab=services&serviceType=customer-rework'
        : `/logistics-status/${saved.id}`)
    } catch (err) {
      if (err instanceof ApiError) {
        const parsed = parseSubmitErrors(err.detail)
        if (parsed) { setSubmitErrors(parsed.errors); return }
      }
      setSaveErrorMsg(err instanceof Error ? err.message : 'Could not submit')
    } finally {
      setSubmitting(false)
    }
  }

  /* ---- render ---- */

  if (loadingRecord) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Loading order…" module="logisticsStatus" />
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Logistics order not found" module="logisticsStatus" />
        <button onClick={() => navigate('/logistics-status')} className="text-sm text-accent hover:underline">
          ← Back to logistics orders
        </button>
      </div>
    )
  }

  if (loadErrorMsg) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Logistics order" module="logisticsStatus" />
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>{loadErrorMsg}</span>
          <button type="button" onClick={loadRecord} className="underline">Retry</button>
        </div>
      </div>
    )
  }

  if (isLocked) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={`Logistics order ${id}`} subtitle="Closed" module="logisticsStatus" />
        <div className="rounded-lg border border-line bg-canvas-alt px-3.5 py-2.5 text-sm text-muted">
          This order is closed. An admin must reopen it before it can be edited.
        </div>
        <button onClick={() => navigate(`/logistics-status/${id}`)} className="text-sm text-accent hover:underline">
          ← View order
        </button>
      </div>
    )
  }

  const busy = saving || submitting
  const isLastStep = stepDef.step === WIZARD_STEPS.length

  // WATCHED, NOT READ ONCE: the banner and the Submit button have to reflect
  // what is on screen right now, so this re-evaluates on every edit rather
  // than only after a save. methods.watch() with no argument subscribes to the
  // whole draft, which is what these rules read.
  const outstanding = submitRequirements(methods.watch())
  const blocked = outstanding.length > 0
  const title = jobKind === 'rework'
    ? (isNew ? 'New Customer Rework Job' : `Edit Rework Job ${orderId ?? id}`)
    : (isNew ? 'New Logistics Order' : `Edit Logistics Order ${orderId ?? id}`)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={title}
        subtitle={`Step ${stepDef.step} of ${WIZARD_STEPS.length} — ${stepDef.label}`}
        module="logisticsStatus"
      />

      <WizardStepper steps={WIZARD_STEPS} current={stepDef.step} onStepClick={busy ? undefined : goToStep} />

      <Card>
        <CardContent className="p-6">
          <FormProvider {...methods}>
            <form onSubmit={(e) => e.preventDefault()}>
              <StepComponent />

              {saveErrorMsg && (
                <p className="mt-4 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">{saveErrorMsg}</p>
              )}
              {submitErrors && submitErrors.length > 0 && (
                <div className="mt-4 rounded-lg bg-risk-bg px-3 py-2.5 text-sm text-risk">
                  <p className="font-medium">This order can’t be submitted yet:</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-5">
                    {submitErrors.map((e, i) => <li key={i}>{e}</li>)}
                  </ul>
                </div>
              )}

              {/* Shown on EVERY step, so a step 1 gap is visible while the
                  user is on step 5 rather than only after they hit Submit. */}
              <SubmitRequirements
                requirements={outstanding}
                currentStep={stepDef.step}
                onGoToStep={goToStep}
              />

              <div className="mt-6 flex items-center justify-between">
                <Button
                  type="button"
                  variant="outline"
                  disabled={stepDef.step === 1 || busy}
                  onClick={() => goToStep(stepDef.step - 1)}
                >
                  Back
                </Button>

                <div className="flex items-center gap-3">
                  {justSaved && <span className="text-xs text-[var(--color-healthy)]">Saved</span>}
                  {isLastStep ? (
                    <Button type="button" variant="outline" disabled={busy} onClick={handleSaveOnly}>
                      {saving ? 'Saving…' : 'Save'}
                    </Button>
                  ) : (
                    <Button type="button" variant="outline" disabled={busy} onClick={() => goToStep(stepDef.step + 1)}>
                      {saving ? 'Saving…' : 'Save and Next'}
                    </Button>
                  )}
                  {/* DISABLED WITH A REASON, never hidden — the same
                      principle as the FOB send buttons. The tooltip names
                      exactly what is outstanding, so the button explains
                      itself without the banner having to be open. */}
                  <Button
                    type="button"
                    disabled={busy || blocked}
                    title={requirementsTooltip(outstanding)}
                    onClick={handleSubmit}
                  >
                    {submitting ? 'Submitting…' : 'Submit'}
                  </Button>
                </div>
              </div>
            </form>
          </FormProvider>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={pendingStep != null}
        title="Unsaved changes"
        description={
          <>
            You have unsaved changes on this step. Save them before moving, or move
            without saving and lose them?
          </>
        }
        confirmLabel="Save and move"
        confirmingLabel="Saving…"
        confirming={busy}
        onConfirm={() => void saveThenMove()}
        onCancel={cancelMove}
        secondaryLabel="Move without saving"
        onSecondary={moveWithoutSaving}
      />

      <ConfirmDialog
        open={!!pendingAction}
        title="Close this order?"
        description={
          <>
            Submitting at status <span className="font-medium text-ink">"Delivered"</span> closes this order.
            Once closed, no one but an admin can edit it (an admin can reopen it later).
          </>
        }
        confirmLabel="Yes, submit and close it"
        confirmingLabel="Submitting…"
        confirming={busy}
        onConfirm={confirmClose}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  )
}
