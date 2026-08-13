import { cn } from '@/lib/utils'
import type { WizardStepDef } from '../schema'

/**
 * `onStepClick` is only passed in edit mode — the wizard has an existing
 * record to jump around in. In new-record mode there's nowhere to jump to
 * until Next has minted an id, so the steps stay plain, non-interactive text.
 */
export function WizardStepper({
  steps, current, onStepClick,
}: {
  steps: WizardStepDef[]
  current: number
  onStepClick?: (step: number) => void
}) {
  return (
    <ol className="flex flex-wrap gap-2">
      {steps.map((s) => {
        const pillClass = cn(
          'rounded-full border px-3 py-1 text-xs font-medium',
          s.step === current
            ? 'border-brand bg-brand text-on-brand'
            : s.step < current
              ? 'border-line bg-canvas-alt text-ink'
              : 'border-line text-muted',
          onStepClick && s.step !== current && 'cursor-pointer transition-colors hover:border-brand',
        )
        return (
          <li key={s.step}>
            {onStepClick ? (
              <button type="button" className={pillClass} onClick={() => onStepClick(s.step)}>
                {s.step}. {s.label}
              </button>
            ) : (
              <span className={pillClass}>{s.step}. {s.label}</span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
