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
  getConsignment, createConsignment, updateConsignmentApi, submitConsignmentApi,
  parseSubmitErrors, type ConsignmentPayload,
} from '@/lib/api/imports'
import {
  draftToPayload, apiToDraft, syncItemBackendIds, syncPaymentBackendIds, type WizardMasters,
} from '@/lib/api/importsMap'
import {
  consignmentDraftSchema, DRAFT_DEFAULT_VALUES, WIZARD_STEPS, CLOSED_STATUS,
  type ConsignmentDraft, type ConsignmentItem, type Payment,
} from '../schema'
import { MastersProvider, useMasters } from './MastersContext'
import { WizardStepper } from '@/components/ui/WizardStepper'
import { useStepNavigation } from '@/lib/useStepNavigation'
import { Step1Consignment } from './steps/Step1Consignment'
import { Step2Finance } from './steps/Step2Finance'
import { Step3Shipping } from './steps/Step3Shipping'
import { Step4Payments } from './steps/Step4Payments'
import { Step5StatusRemarks } from './steps/Step5StatusRemarks'
import { Step6Clearance } from './steps/Step6Clearance'

const STEP_COMPONENTS = [
  Step1Consignment, Step2Finance, Step3Shipping, Step4Payments,
  Step5StatusRemarks, Step6Clearance,
]

/**
 * Imports Status wizard.
 *
 * Back and "Save and Next" always save the current form state first (POST
 * the first time, PUT after) and only move once that succeeds; if it fails,
 * the error shows and the page stays put. "Next" reads "Save and Next" for
 * exactly that reason. Submit (available on every step) saves the same way,
 * then calls the strict /submit endpoint, which validates server-side and
 * reports back anything still missing.
 *
 * Clicking a STEP PILL is different: via useStepNavigation/WizardStepper
 * (shared with logistics and trucking), it jumps there directly with no save
 * if the form is clean, and otherwise asks whether to save first or move
 * without saving — the "Unsaved changes" dialog below. Either way, a save
 * that would happen along that path still goes through runWithCloseConfirm
 * (see saveAndNavigateToStepConfirmed) — the "Close this consignment?" prompt
 * is a DIFFERENT question from "you have unsaved edits", and both can fire
 * for the same click, one after the other.
 *
 * react-hook-form holds ONE draft across all six steps (this component is not
 * remounted between them — only the `:step` route param changes), so every
 * save sends the FULL current draft, not just the step being left. That's
 * required for correctness: the update route diffs items/payments against
 * what it already has, and a line missing from the payload reads as deleted.
 */
export function ImportsStatusWizard() {
  return (
    <MastersProvider>
      <ImportsStatusWizardInner />
    </MastersProvider>
  )
}

function ImportsStatusWizardInner() {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()
  const isNew = !id
  const masters = useMasters()

  const currentStep = isNew ? 1 : Number(step) || 1
  const stepIndex = Math.min(Math.max(currentStep, 1), WIZARD_STEPS.length) - 1
  const stepDef = WIZARD_STEPS[stepIndex]
  const StepComponent = STEP_COMPONENTS[stepIndex]

  const methods = useForm<z.input<typeof consignmentDraftSchema>, unknown, ConsignmentDraft>({
    resolver: zodResolver(consignmentDraftSchema),
    defaultValues: DRAFT_DEFAULT_VALUES,
    mode: 'onBlur',
  })


  // --- loading the existing record (edit mode only) ---
  const [consignmentId, setConsignmentId] = useState<number | null>(id ? Number(id) : null)
  const [loadingRecord, setLoadingRecord] = useState(!!id)
  const [notFound, setNotFound] = useState(false)
  const [loadErrorMsg, setLoadErrorMsg] = useState<string | null>(null)
  const [isLocked, setIsLocked] = useState(false)
  // The status/record_state this consignment was loaded with. The backend
  // only actually closes a consignment when BOTH current_status is
  // "Arrived at Works" AND record_state is "submitted" (helpers.is_closed) —
  // so the confirmation needs both, not status alone. A new consignment has
  // neither, so it never matches on its own.
  const [originalStatus, setOriginalStatus] = useState('')
  const [recordState, setRecordState] = useState('draft')

  const loadRecord = useCallback(() => {
    if (!id) return
    setLoadingRecord(true)
    setNotFound(false)
    setLoadErrorMsg(null)
    getConsignment(id)
      .then((c) => {
        setConsignmentId(c.id)
        setIsLocked(c.is_locked)
        setOriginalStatus(c.current_status ?? '')
        setRecordState(c.record_state ?? 'draft')
        methods.reset(apiToDraft(c))
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setLoadErrorMsg(err instanceof Error ? err.message : 'Could not load this consignment')
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

  // Same actions the list/detail views gate on — a viewer or a user without
  // create rights should never land on this route, hyperlink or not.
  const allowed = isNew
    ? can(user, 'enter', 'imports')
    : can(user, 'editAny', 'imports') || can(user, 'editOwnDraft', 'imports')
  if (!allowed) return <Navigate to="/imports-status" replace />

  function buildPayload(): ConsignmentPayload {
    const wizardMasters: WizardMasters = {
      branches: masters.branches, suppliers: masters.suppliers,
      ports: masters.ports, agents: masters.agents,
    }
    return draftToPayload(methods.getValues() as ConsignmentDraft, wizardMasters)
  }

  // --- confirm-before-closing (a real dialog, not window.confirm — same
  // pattern as change history's RevertConfirmDialog) ---
  // The action Back/Save and Next/Save/Submit were about to run, stashed
  // while the dialog is open; null/undefined means the dialog is closed.
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null)

  // navigateToStep/saveAndNavigateToStepConfirmed are defined below (hoisted
  // function declarations, so referencing them here is fine) — this hook
  // drives the STEPPER's own "unsaved changes" prompt, a different question
  // from the close-confirm above and independent of it.
  const {
    goToStep, pendingStep, saveThenMove, moveWithoutSaving, cancelMove,
  } = useStepNavigation({
    currentStep: stepDef.step,
    totalSteps: WIZARD_STEPS.length,
    isDirty: methods.formState.isDirty,
    clearDirty: () => methods.reset(methods.getValues()),
    navigateToStep,
    saveAndNavigateToStep: saveAndNavigateToStepConfirmed,
  })

  /** "Arrived at Works" locks the consignment for everyone but an admin —
   *  worth a confirmation, since it's not obviously reversible from the
   *  wizard itself. A plain draft save never closes it, no matter what
   *  status is set or whether the record is already submitted — only
   *  submitting does (the backend's update route no longer locks at all;
   *  see update_consignment.py). So this only fires for the Submit action. */
  function willClose(isSubmitAction: boolean): boolean {
    if (!isSubmitAction) return false
    const closing = methods.getValues('status') === CLOSED_STATUS
    const alreadyClosed = originalStatus === CLOSED_STATUS && recordState === 'submitted'
    return closing && !alreadyClosed
  }

  /** Every button that can trigger a save routes its action through here, so
   *  one that would close the consignment pauses for confirmation first. */
  function runWithCloseConfirm(action: () => void, opts: { isSubmit?: boolean } = {}) {
    if (willClose(!!opts.isSubmit)) setPendingAction(() => action)
    else action()
  }

  function confirmClose() {
    const action = pendingAction
    setPendingAction(null)
    action?.()
  }

  /** POST the first time, PUT after. Returns the saved record's id + whether
   *  that save just closed it, or null (with saveErrorMsg set) on failure.
   *  Confirmation (if needed) has already happened by the time this runs —
   *  see runWithCloseConfirm. */
  async function saveDraft(): Promise<{ id: number; isLocked: boolean } | null> {
    setSaving(true)
    setSaveErrorMsg(null)
    setSubmitErrors(null)
    try {
      const payload = buildPayload()
      const response = consignmentId
        ? await updateConsignmentApi(consignmentId, payload)
        : await createConsignment(payload)

      if (!consignmentId) setConsignmentId(response.id)
      setOriginalStatus(response.current_status ?? '')
      setRecordState(response.record_state ?? 'draft')
      setIsLocked(response.is_locked)

      // Newly-created lines had no id when the request went out; attach the
      // ones the backend just assigned so the NEXT save updates them instead
      // of inserting duplicates. getValues() returns the resolver's INPUT
      // type (fields with a zod .default() are optional there); safe to cast
      // to the OUTPUT type — those defaults are always populated once the
      // form has mounted with defaultValues (same reasoning the original
      // wizard's handleSaveAndMove documented).
      const currentItems = (methods.getValues('items') ?? []) as ConsignmentItem[]
      const currentPayments = (methods.getValues('payments') ?? []) as Payment[]
      methods.setValue('items', syncItemBackendIds(currentItems, response.items), { shouldDirty: false })
      methods.setValue('payments', syncPaymentBackendIds(currentPayments, response.payments), { shouldDirty: false })

      return { id: response.id, isLocked: response.is_locked }
    } catch (err) {
      setSaveErrorMsg(err instanceof Error ? err.message : 'Could not save')
      return null
    } finally {
      setSaving(false)
    }
  }

  /** Navigate to a step WITHOUT saving. For a brand-new unsaved consignment
   *  there's no id yet, so we can only move once it's been saved at least
   *  once — routed through runWithCloseConfirm like every other save, since
   *  even that first save could set a closing status. */
  function navigateToStep(clamped: number) {
    if (isNew) {
      runWithCloseConfirm(() => void doGoToStep(clamped, true))
      return
    }
    navigate(`/imports-status/${consignmentId}/edit/${clamped}`)
  }

  async function doGoToStep(clamped: number, keepDirtyReset = false) {
    const saved = await saveDraft()
    if (saved === null) return // error is already shown; stay put
    if (keepDirtyReset) methods.reset(methods.getValues())
    // A save that just closed the consignment leaves nothing further to
    // edit — land on the read-only detail view instead of an edit route
    // that would immediately bounce with "this consignment is closed".
    navigate(saved.isLocked ? `/imports-status/${saved.id}` : `/imports-status/${saved.id}/edit/${clamped}`)
  }

  /** "Save and move" from the unsaved-changes dialog also goes through
   *  runWithCloseConfirm — it is a real save, and the two prompts (unsaved
   *  edits vs. about to close the record) are independent and can both fire
   *  for the same click, one after the other. */
  async function saveAndNavigateToStepConfirmed(clamped: number) {
    runWithCloseConfirm(() => void doGoToStep(clamped))
  }

  /** The last step's "Save" — same save, but nowhere further to go. */
  function handleSaveOnly() {
    runWithCloseConfirm(() => void doHandleSaveOnly())
  }

  async function doHandleSaveOnly() {
    const saved = await saveDraft()
    if (saved === null) return
    setJustSaved(true)
    setTimeout(() => setJustSaved(false), 2000)
    if (isNew) navigate(`/imports-status/${saved.id}/edit/${stepDef.step}`, { replace: true })
  }

  /** Save, then run the strict server-side rule set. Available on every step
   *  (not just the last), but disabled until the draft actually satisfies
   *  those rules — see canSubmit below. A 422 comes back with the full list
   *  of what's missing (submission_errors, mirrored from the same rules the
   *  draft schema's superRefine describes) — shown inline rather than
   *  re-deriving the same list client-side and risking the two drifting
   *  apart. */
  function handleSubmit() {
    runWithCloseConfirm(() => void doHandleSubmit(), { isSubmit: true })
  }

  async function doHandleSubmit() {
    const saved = await saveDraft()
    if (saved === null) return

    setSubmitting(true)
    setSubmitErrors(null)
    try {
      await submitConsignmentApi(saved.id)
      navigate(`/imports-status/${saved.id}`)
    } catch (err) {
      if (err instanceof ApiError) {
        const parsed = parseSubmitErrors(err.detail)
        if (parsed) {
          setSubmitErrors(parsed.errors)
          return
        }
      }
      setSaveErrorMsg(err instanceof Error ? err.message : 'Could not submit')
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingRecord) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Loading consignment…" module="importsStatus" />
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Consignment not found" module="importsStatus" />
        <button onClick={() => navigate('/imports-status')} className="text-sm text-accent hover:underline">
          ← Back to consignments
        </button>
      </div>
    )
  }

  if (loadErrorMsg) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Consignment" module="importsStatus" />
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
        <PageHeader title={`Consignment ${id}`} subtitle="Closed" module="importsStatus" />
        <div className="rounded-lg border border-line bg-canvas-alt px-3.5 py-2.5 text-sm text-muted">
          This consignment is closed. An admin must reopen it before it can be edited.
        </div>
        <button onClick={() => navigate(`/imports-status/${id}`)} className="text-sm text-accent hover:underline">
          ← View consignment
        </button>
      </div>
    )
  }

  const busy = saving || submitting
  const isLastStep = stepDef.step === WIZARD_STEPS.length

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={isNew ? 'New Consignment' : `Edit Consignment ${consignmentId ?? id}`}
        subtitle={`Step ${stepDef.step} of ${WIZARD_STEPS.length} — ${stepDef.label}`}
        module="importsStatus"
      />

      <WizardStepper
        steps={WIZARD_STEPS}
        current={stepDef.step}
        onStepClick={busy ? undefined : goToStep}
      />

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
                  <p className="font-medium">This consignment can’t be submitted yet:</p>
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
        title="Close this consignment?"
        description={
          <>
            Setting status to <span className="font-medium text-ink">"Arrived at Works"</span> closes this
            consignment. Once closed, no one but an admin can edit it (an admin can reopen it later).
          </>
        }
        confirmLabel="Yes, save and close it"
        confirmingLabel="Saving…"
        confirming={busy}
        onConfirm={confirmClose}
        onCancel={() => setPendingAction(null)}
      />
    </div>
  )
}
