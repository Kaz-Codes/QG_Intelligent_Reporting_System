import { useState } from 'react'

/**
 * Free stepper navigation, shared by the imports/logistics/trucking wizards
 * — lifted from TruckingStatusWizard, the only one of the three that had
 * this right (the other two force-saved on every step click; trucking's own
 * stepper just never rendered its pills as clickable — see WizardStepper).
 *
 * Clicking a step tries to jump there directly. If the form has unsaved
 * edits, it instead asks whether to save first or move without saving —
 * `pendingStep` is non-null exactly while that question is open, so the
 * wizard can drive its own confirm dialog off it.
 */
export interface UseStepNavigationOptions {
  /** The step currently showing. */
  currentStep: number
  totalSteps: number
  /** react-hook-form's formState.isDirty, read fresh on every render. */
  isDirty: boolean
  /** Marks the form clean without changing its values or saving anything —
   *  called when the user picks "move without saving", so the SAME edit
   *  doesn't re-trigger this prompt on the very next step click. */
  clearDirty: () => void
  /** Navigate to `step` without saving first — a plain route change, or (for
   *  a brand-new record with no id yet) a forced save, since there is
   *  nowhere to navigate to until one exists. Each wizard already had this
   *  exact branch (trucking's navigateToStep); it stays wizard-local because
   *  the forced-save path and the route shape are both module-specific. */
  navigateToStep: (step: number) => void
  /** Save the current form state, then navigate to `step`. */
  saveAndNavigateToStep: (step: number) => Promise<void>
}

export function useStepNavigation({
  currentStep, totalSteps, isDirty, clearDirty, navigateToStep, saveAndNavigateToStep,
}: UseStepNavigationOptions) {
  // The step the user clicked while the form was dirty. Null means the
  // "unsaved changes" dialog is closed.
  const [pendingStep, setPendingStep] = useState<number | null>(null)

  function goToStep(nextStep: number) {
    const clamped = Math.min(Math.max(nextStep, 1), totalSteps)
    if (clamped === currentStep) return
    // No unsaved edits — jump straight there, no save round-trip. Unsaved
    // edits — ask whether to save first or move without saving.
    if (isDirty) {
      setPendingStep(clamped)
    } else {
      navigateToStep(clamped)
    }
  }

  async function saveThenMove() {
    const target = pendingStep
    setPendingStep(null)
    if (target != null) await saveAndNavigateToStep(target)
  }

  function moveWithoutSaving() {
    const target = pendingStep
    setPendingStep(null)
    // Drop the dirty flag so we don't re-prompt, then navigate.
    clearDirty()
    if (target != null) navigateToStep(target)
  }

  function cancelMove() {
    setPendingStep(null)
  }

  return { goToStep, pendingStep, saveThenMove, moveWithoutSaving, cancelMove }
}
