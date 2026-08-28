import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SubmitRequirement } from '@/lib/submitRequirements'

/**
 * THE POINT OF THIS COMPONENT: a user should never fill five steps and only
 * then discover that a step 1 field was missing.
 *
 * It is shown on EVERY step of the wizard, summarised to a count, and expands
 * to the list. Each row links to the step that owns the field, because
 * "Branch is required" is not actionable if you are on Clearance and do not
 * know Branch lives on Consignment.
 *
 * DISMISSIBLE, BUT IT COMES BACK IF THINGS GET WORSE. A permanent banner that
 * cannot be closed is nagging; one that stays closed for ever after a single
 * click hides new problems introduced later (deleting the only item, clearing
 * the rate). So dismissal holds while the situation is unchanged or improving,
 * and is reset the moment a NEW requirement appears.
 *
 * The Submit button is disabled alongside this, with the same list in its
 * tooltip — disabled WITH A REASON, never hidden. A hidden button leaves the
 * user with nothing to reason about.
 */
export function SubmitRequirements({
  requirements,
  onGoToStep,
  currentStep,
}: {
  requirements: SubmitRequirement[]
  onGoToStep: (step: number) => void
  currentStep: number
}) {
  const [expanded, setExpanded] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  const count = requirements.length

  // Re-open on a NEW problem, not on every keystroke that changes the list.
  // Tracked by count rather than by comparing messages: going from 3 to 4 is
  // something the user should see again; 3 to 2 is progress and must not
  // re-nag them.
  const previousCount = useRef(count)
  useEffect(() => {
    if (count > previousCount.current) setDismissed(false)
    previousCount.current = count
  }, [count])

  if (count === 0) {
    return (
      <div className="mt-4 flex items-center gap-2 rounded-lg border border-line bg-canvas-alt px-3 py-2 text-sm text-muted">
        <CheckCircle2 size={15} className="shrink-0 text-[var(--color-healthy)]" />
        <span>Everything required to submit is filled in.</span>
      </div>
    )
  }

  if (dismissed) return null

  return (
    <div className="mt-4 rounded-lg border border-watch bg-watch-bg">
      <div className="flex items-center gap-2 px-3 py-2">
        <AlertTriangle size={15} className="shrink-0 text-watch" />

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex flex-1 items-center gap-1.5 text-left text-sm font-semibold text-watch"
        >
          {count} {count === 1 ? 'item' : 'items'} still needed to submit
          <ChevronDown
            size={14}
            className={cn('transition-transform duration-200', expanded && 'rotate-180')}
          />
        </button>

        <button
          type="button"
          onClick={() => setDismissed(true)}
          title="Hide until something new is missing"
          className="shrink-0 rounded p-1 text-watch hover:bg-watch/15"
        >
          <X size={14} />
        </button>
      </div>

      {expanded && (
        <ul className="border-t border-watch/30 px-3 py-2">
          {requirements.map((req, i) => (
            <li key={`${req.step}-${req.message}-${i}`} className="py-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2 text-sm text-ink">
                <span>{req.message}</span>
                {req.step === currentStep ? (
                  // Already here. A link that navigates to the page you are on
                  // reads as broken, so it states the step instead.
                  <span className="text-[11px] text-muted">on this step</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => onGoToStep(req.step)}
                    className="text-[11px] font-semibold text-brand hover:underline"
                  >
                    Go to {req.stepLabel} →
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
