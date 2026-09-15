import type { ReactNode } from 'react'
import { useBatchContext } from '../BatchContext'

/**
 * A whole step that belongs to the ORDER, shown read-only on a later batch.
 *
 * THE REQUIREMENTS, verbatim: *"Entered once, on the first batch only.
 * Editable only on batch 1; read-only on later batches, which display the same
 * values"* — Step 2 (Finance, the whole step) and Step 4 (Payments).
 *
 * THIS IS NOT THE FREEZE, and conflating the two would be a mistake worth
 * naming. The freeze (§3.9) bites once a batch has CLOSED and is about money
 * that has already moved; it applies to batch 1 as much as to batch 3. This
 * rule bites the moment an order SPLITS and is about where a value is entered,
 * not whether it may change — batch 1 stays editable however many batches
 * follow it. A record can be under both, one, or neither.
 *
 * A `fieldset` RATHER THAN PER-FIELD READ-ONLY RENDERING. The freeze shows a
 * value and removes its input, which is right for the handful of fields it
 * covers. Here it is two entire steps, including a priced item table; turning
 * every control into a display component would be a large diff whose only
 * effect is the one `disabled` already has natively, and it would be a second
 * spelling of "this is not editable" for a reader to reconcile with the first.
 * The banner is what carries the reason, which is the part that actually helps.
 *
 * NOTHING IS PREVENTED SERVER-SIDE BY THIS, deliberately. These fields live on
 * the order and any batch may legitimately write them — the freeze is the rule
 * with teeth. This stops an operator editing batch 3's copy of a value that was
 * agreed on batch 1, which is a question of where work happens rather than of
 * what is permitted.
 */
export function EnteredOnBatchOne({ what, children }: { what: string; children: ReactNode }) {
  const ctx = useBatchContext()
  const readOnly = ctx.isSplit && !ctx.isFoundingBatch
  const first = ctx.batches[0]?.consignment_number

  if (!readOnly) return <>{children}</>

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-line bg-canvas-alt px-3.5 py-2.5 text-sm">
        <span className="font-medium text-ink">{what} is entered once, on the order.</span>{' '}
        <span className="text-muted">
          These values were set on batch{first ? ` ${first}` : ' 1'} and are shared by every
          batch of this order, so they are shown here rather than re-entered.
          {first && <> To change them, open batch <span className="font-medium text-ink">{first}</span>.</>}
        </span>
      </div>
      {/* One attribute disables every control inside, including ones added
          later — which is the property that keeps this correct as the step
          grows. */}
      <fieldset disabled className="space-y-5 opacity-90">
        {children}
      </fieldset>
    </div>
  )
}
