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
  type LogisticsDraft, type JobKind,
} from '../schema'
import { WizardStepper } from './WizardStepper'
import { Step1Order } from './steps/Step1Order'
import { Step2Packing } from './steps/Step2Packing'
import { Step3Shipping } from './steps/Step3Shipping'
import { Step4Expenditures } from './steps/Step4Expenditures'
import { Step5Status } from './steps/Step5Status'

const STEP_COMPONENTS = [
  Step1Order, Step2Packing, Step3Shipping, Step4Expenditures, Step5Status,
]

/** "Delivered" is the terminal status; reaching it on a SUBMIT closes the
 *  order (helpers.is_closed = Delivered AND submitted). */
const CLOSED_STATUS = 'Delivered'

function freshDraftDefaults(jobKind: JobKind = 'standard'): LogisticsDraft {
  return { ...DRAFT_DEFAULT_VALUES, jobKind, items: [emptyItem(`item-${crypto.randomUUID()}`)] }
}

/**
 * Logistics Status wizard — ORDERS wired to the live backend.
 *
 * Same shape as the imports wizard, and for the same reasons:
 *
 *  - NO unsaved-changes dialog. Every navigation — Back, "Save and Next", or
 *    clicking a step in the stepper — saves the current form state first (POST
 *    the first time, PUT after) and only moves once that succeeds. There is
 *    nothing left to lose, so there is nothing to warn about.
 *  - SUBMIT sits on every step, not just the last. It saves, then calls the
 *    strict /submit endpoint, which reports back anything still missing.
 *  - A CLOSED order is read-only. Only /submit can close one (Delivered AND
 *    submitted), so the confirmation fires on Submit alone — a draft save that
 *    merely sets the status to Delivered closes nothing.
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

  function goToStep(nextStep: number) {
    const clamped = Math.min(Math.max(nextStep, 1), WIZARD_STEPS.length)
    if (clamped === stepDef.step) return
    void doGoToStep(clamped)
  }

  async function doGoToStep(clamped: number) {
    const saved = await saveDraft()
    if (saved === null) return // error already shown; stay put
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
                  <Button type="button" disabled={busy} onClick={handleSubmit}>
                    {submitting ? 'Submitting…' : 'Submit'}
                  </Button>
                </div>
              </div>
            </form>
          </FormProvider>
        </CardContent>
      </Card>

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
