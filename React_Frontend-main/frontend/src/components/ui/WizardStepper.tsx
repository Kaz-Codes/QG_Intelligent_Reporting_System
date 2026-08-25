import { cn } from '@/lib/utils'

/** The bits of a module's WizardStepDef the pills actually need — each
 *  wizard's own richer step-definition type (which also carries `key`,
 *  `fields`, ...) satisfies this structurally, so no per-module import. */
export interface WizardStepLike {
  step: number
  label: string
}

/**
 * Step pills shared by the imports/logistics/trucking wizards.
 *
 * A step is a clickable button whenever `onStepClick` is supplied, otherwise
 * plain non-interactive text. There is deliberately no separate `clickable`
 * flag — that was trucking's own stepper's bug: the prop existed, defaulted
 * to false, and its wizard never passed `clickable` alongside `onStepClick`,
 * so the pills looked ready to click but silently never were. Whether
 * `onStepClick` is supplied is the only signal now, so that failure mode
 * can't recur.
 */
export function WizardStepper({
  steps, current, onStepClick,
}: {
  steps: WizardStepLike[]
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
