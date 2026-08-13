import { cn } from '@/lib/utils'
import type { WizardStepDef } from '../schema'

/**
 * Same stepper as the other modules, plus optional click-to-jump used in edit
 * mode. When `clickable` is false the steps are inert (new-mode gating lives in
 * the wizard's Next handler).
 */
export function WizardStepper({
  steps,
  current,
  clickable = false,
  onStepClick,
}: {
  steps: WizardStepDef[]
  current: number
  clickable?: boolean
  onStepClick?: (step: number) => void
}) {
  return (
    <ol className="flex flex-wrap gap-2">
      {steps.map((s) => {
        const base = cn(
          'rounded-full border px-3 py-1 text-xs font-medium',
          s.step === current
            ? 'border-brand bg-brand text-on-brand'
            : s.step < current
              ? 'border-line bg-canvas-alt text-ink'
              : 'border-line text-muted',
        )
        if (clickable && onStepClick) {
          return (
            <li key={s.step}>
              <button
                type="button"
                onClick={() => onStepClick(s.step)}
                className={cn(base, 'cursor-pointer transition-colors hover:border-brand')}
              >
                {s.step}. {s.label}
              </button>
            </li>
          )
        }
        return (
          <li key={s.step} className={base}>
            {s.step}. {s.label}
          </li>
        )
      })}
    </ol>
  )
}
