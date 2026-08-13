import { useCallback, useEffect, useState } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { FormProvider, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import type { z } from 'zod'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  DRAFT_DEFAULT_VALUES,
  WIZARD_STEPS,
  truckingDraftSchema,
  type TruckingDraft,
} from '../schema'
import { ApiError } from '@/lib/api/client'
import {
  getTruckingJob, createTruckingJob, updateTruckingJob, submitTruckingJob,
  parseSubmitErrors, type TruckingPayload,
} from '@/lib/api/trucking'
import { apiToDraft, draftToPayload, remapNewVehicleIds } from '@/lib/api/truckingMap'
import { WizardStepper } from './WizardStepper'
import { Step1Movement } from './steps/Step1Movement'
import { Step2Vehicles } from './steps/Step2Vehicles'
import { Step3Freight } from './steps/Step3Freight'
import { Step4Tracking } from './steps/Step4Tracking'

const STEP_COMPONENTS = [Step1Movement, Step2Vehicles, Step3Freight, Step4Tracking]

/**
 * Trucking Status wizard — wired to the live backend.
 *
 * Same shape as the imports and logistics wizards, for the same reasons:
 *
 *  - NO unsaved-changes dialog. Every navigation — Back, "Save and Next", or
 *    clicking a step — saves first (POST the first time, PUT after) and only
 *    moves once that succeeds. Nothing is left to lose, so nothing to warn about.
 *  - SUBMIT sits on every step, not just the last, and reports back whatever
 *    the server says is still missing.
 *  - A CLOSED job is read-only. Only /submit can close one (every vehicle
 *    Delivered AND submitted), so the confirmation fires on Submit alone.
 *
 * TAKE ACTION. Arriving from an open request carries `?source=…&source_ref=…`.
 * Those seed the draft so the resulting job records where it came from — which
 * is what makes the request drop off trucking's queue (open-requests subtracts
 * jobs matched on that pair) and what the detail page links back through. They
 * are read ONCE, for a new job; on an existing record the values come from the
 * server, never from the URL.
 */
export function TruckingStatusWizard() {
  const { user } = useAuth()
  const { id, step } = useParams()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const currentStep = id ? Number(step) || 1 : 1
  const stepIndex = Math.min(Math.max(currentStep, 1), WIZARD_STEPS.length) - 1
  const stepDef = WIZARD_STEPS[stepIndex]
  const StepComponent = STEP_COMPONENTS[stepIndex]

  // Seeded once per mounted instance so the source survives re-renders.
  const [initialValues] = useState<TruckingDraft>(() => {
    const source = searchParams.get('source')
    const sourceRef = searchParams.get('source_ref')
    if (!source || !sourceRef) return DRAFT_DEFAULT_VALUES
    return {
      ...DRAFT_DEFAULT_VALUES,
      source: source as TruckingDraft['source'],
      sourceRef,
      // An inbound FOB import and an outbound logistics order move in
      // different directions; seed the obvious one rather than making the
      // user restate what the hand-off already implies.
      movementType: source === 'from-import-fob' ? 'Inbound' : 'Outbound',
    }
  })

  const methods = useForm<z.input<typeof truckingDraftSchema>, unknown, TruckingDraft>({
    resolver: zodResolver(truckingDraftSchema),
    defaultValues: initialValues,
    mode: 'onBlur',
  })

  // --- loading the existing job (edit mode) ---
  const [jobId, setJobId] = useState<number | null>(id ? Number(id) : null)
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
    getTruckingJob(id)
      .then((j) => {
        setJobId(j.id)
        setIsLocked(j.is_locked)
        setRecordState(j.record_state ?? 'draft')
        methods.reset(apiToDraft(j))
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) setNotFound(true)
        else setLoadErrorMsg(err instanceof Error ? err.message : 'Could not load this job')
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
  const [pendingStep, setPendingStep] = useState<number | null>(null)

  const isNew = !jobId
  const allowed = isNew ? can(user, 'enter') : can(user, 'editAny') || can(user, 'editOwnDraft')
  if (!allowed) return <Navigate to="/trucking-status" replace />

  function buildPayload(): TruckingPayload {
    return draftToPayload(methods.getValues() as TruckingDraft)
  }

  async function saveDraft(): Promise<{ id: number; isLocked: boolean } | null> {
    setSaving(true)
    setSaveErrorMsg(null)
    setSubmitErrors(null)
    try {
      const payload = buildPayload()
      const response = jobId
        ? await updateTruckingJob(jobId, payload)
        : await createTruckingJob(payload)

      if (!jobId) setJobId(response.id)
      setRecordState(response.record_state ?? 'draft')
      setIsLocked(response.is_locked)

      // Vehicles that were brand-new now have real ids; adopt them so the
      // NEXT save updates those rows instead of inserting duplicates.
      const current = methods.getValues() as TruckingDraft
      const remapped = remapNewVehicleIds(current, response)
      if (remapped !== current) {
        methods.setValue('vehicles', remapped.vehicles, { shouldDirty: false })
      }

      return { id: response.id, isLocked: response.is_locked }
    } catch (err) {
      setSaveErrorMsg(err instanceof Error ? err.message : 'Could not save')
      return null
    } finally {
      setSaving(false)
    }
  }

  /** Only a SUBMIT can close a job, so only Submit needs confirming. */
  function willClose(isSubmitAction: boolean): boolean {
    if (!isSubmitAction) return false
    const vehicles = (methods.getValues('vehicles') ?? []) as TruckingDraft['vehicles']
    const allDelivered = vehicles.length > 0
      && vehicles.every((v) => v.trackingStatus === 'Delivered')
    const alreadyClosed = recordState === 'submitted' && isLocked
    return allDelivered && !alreadyClosed
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

  function goToStep(nextStep: number) {
    const clamped = Math.min(Math.max(nextStep, 1), WIZARD_STEPS.length)
    if (clamped === stepDef.step) return
    // No unsaved edits — jump straight there, no save round-trip. Unsaved edits
    // — ask whether to save first or move without saving.
    if (methods.formState.isDirty) {
      setPendingStep(clamped)
    } else {
      navigateToStep(clamped)
    }
  }

  /** Navigate to a step WITHOUT saving. For a brand-new unsaved job there's no
   *  id yet, so we can only move once it's been saved at least once. */
  function navigateToStep(clamped: number) {
    if (isNew || id == null) {
      // Nothing persisted yet — a save is unavoidable to get an id.
      void doGoToStep(clamped, true)
      return
    }
    navigate(`/trucking-status/${id}/edit/${clamped}`)
  }

  async function doGoToStep(clamped: number, keepDirtyReset = false) {
    const saved = await saveDraft()
    if (saved === null) return // error is already shown; stay put
    if (keepDirtyReset) methods.reset(methods.getValues())
    // A save that closed the job leaves nothing further to edit — land on the
    // read-only detail view rather than an edit route that would bounce.
    navigate(saved.isLocked
      ? `/trucking-status/${saved.id}`
      : `/trucking-status/${saved.id}/edit/${clamped}`)
  }

  async function saveThenMove() {
    const target = pendingStep
    setPendingStep(null)
    if (target != null) await doGoToStep(target)
  }

  function moveWithoutSaving() {
    const target = pendingStep
    setPendingStep(null)
    // Drop unsaved edits so we don't re-prompt, then navigate.
    methods.reset(methods.getValues())
    if (target != null) navigateToStep(target)
  }

  async function handleSaveOnly() {
    const saved = await saveDraft()
    if (saved === null) return
    setJustSaved(true)
    setTimeout(() => setJustSaved(false), 2000)
    if (isNew) navigate(`/trucking-status/${saved.id}/edit/${stepDef.step}`, { replace: true })
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
      await submitTruckingJob(saved.id)
      navigate(`/trucking-status/${saved.id}`)
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
        <PageHeader title="Loading job…" module="truckingStatus" />
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Trucking job not found" module="truckingStatus" />
        <button onClick={() => navigate('/trucking-status')} className="text-sm text-accent hover:underline">
          ← Back to trucking
        </button>
      </div>
    )
  }

  if (loadErrorMsg) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Trucking job" module="truckingStatus" />
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
        <PageHeader title={`Trucking job ${id}`} subtitle="Closed" module="truckingStatus" />
        <div className="rounded-lg border border-line bg-canvas-alt px-3.5 py-2.5 text-sm text-muted">
          This job is closed. An admin must reopen it before it can be edited.
        </div>
        <button onClick={() => navigate(`/trucking-status/${id}`)} className="text-sm text-accent hover:underline">
          ← View job
        </button>
      </div>
    )
  }

  const busy = saving || submitting
  const isLastStep = stepDef.step === WIZARD_STEPS.length

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={isNew ? 'New Trucking Job' : `Edit Trucking Job ${jobId ?? id}`}
        subtitle={`Step ${stepDef.step} of ${WIZARD_STEPS.length} — ${stepDef.label}`}
        module="truckingStatus"
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
                  <p className="font-medium">This job can’t be submitted yet:</p>
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
        onCancel={() => setPendingStep(null)}
        secondaryLabel="Move without saving"
        onSecondary={moveWithoutSaving}
      />

      <ConfirmDialog
        open={!!pendingAction}
        title="Close this job?"
        description={
          <>
            Every vehicle on this job is marked <span className="font-medium text-ink">Delivered</span>, so
            submitting closes it. Once closed, no one but an admin can edit it (an admin can reopen it later).
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
