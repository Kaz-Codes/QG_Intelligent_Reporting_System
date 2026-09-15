import { useMemo, useState } from 'react'
import { useFormContext } from 'react-hook-form'
import { createBatchApi, type BatchNumbering } from '@/lib/api/imports'
import { ApiError } from '@/lib/api/client'
import { Button } from '@/components/ui/button'
import { useBatchContext } from '../BatchContext'
import type { ConsignmentDraft } from '../../schema'

/**
 * Step 3's allocation view — the screen that makes batching reachable.
 *
 * WHAT IT IS. An order buys 250 kg; a shipment brings 100. This table is where
 * an operator sees the difference and turns the remainder into the next batch.
 * Quantity ALWAYS, never weight (requirements, Step 3), with the unit beside
 * it, because "100" of an order for 250 kg is not a number anyone can act on.
 *
 * A COMPACT TABLE, NOT A CARD GRID. Every row carries the same five figures, so
 * a table lets an operator scan the outstanding column down the page — which is
 * the one question this screen exists to answer. Cards would earn their place
 * once a batch can hold per-batch specifications worth showing, and nothing
 * produces those yet.
 *
 * IT READS THE SERVER'S ALLOCATION, NEVER THE FORM'S. `allocated` is the sum
 * across every batch of the order and is owned by `reconcile_allocation`; the
 * quantity in the form is one batch's line. Deriving the first from the second
 * is exactly the drift the order-item table exists to prevent — it would be
 * right on a single-batch order and silently wrong the moment one split.
 */

function n(v: string | number | null | undefined): number {
  if (v === null || v === undefined || v === '') return 0
  const x = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(x) ? x : 0
}

/** Trailing zeros off a Decimal, so `6.916000` reads as `6.916`. */
function qty(v: string | number | null | undefined, unit: string | null): string {
  const s = n(v).toFixed(3).replace(/\.?0+$/, '')
  return unit ? `${s} ${unit}` : s
}

export function AllocationPanel() {
  const { watch, setValue } = useFormContext<ConsignmentDraft>()
  const ctx = useBatchContext()
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)
  const [result, setResult] = useState<BatchNumbering | null>(null)
  const [draftAlloc, setDraftAlloc] = useState<Record<number, string>>({})

  const number = watch('consignmentNumber') || 'this consignment'

  const rows = ctx.allocation
  const pending = useMemo(
    () => rows.filter((r) => n(r.outstanding_quantity) > 0),
    [rows],
  )

  // WHAT THE NEXT BATCH WOULD BE CALLED, previewed before it exists.
  //
  // The rule is §3.5a/A1 and it is the whole reason the warning is meaningful:
  // a single-batch order shows the PLAIN number, so creating the second batch
  // renumbers the first. `177` becomes `177-1` and the new one is `177-2`.
  // Once an order has already split nothing is renumbered, and the dialog says
  // so rather than warning about a change that will not happen.
  const willRenumber = !ctx.isSplit && ctx.batches.length === 1
  const founding = ctx.batches[0]?.consignment_number ?? number
  const base = founding.split('-')[0]
  const nextSeq = ctx.batches.length + 1

  async function create() {
    const allocations = pending
      .map((r) => ({
        order_item_id: r.order_item_id,
        quantity: Number(draftAlloc[r.order_item_id] ?? n(r.outstanding_quantity)),
      }))
      .filter((a) => a.quantity > 0)

    if (allocations.length === 0) {
      setError('Enter a quantity for at least one item.')
      return
    }

    setCreating(true)
    setError(null)
    try {
      // The id of the batch we are looking at. Any batch of the order is a
      // valid entry point — the route resolves the ORDER from it.
      const res = await createBatchApi(watch('systemId'), allocations)
      setResult(res.numbering)
      setConfirm(false)
      setDraftAlloc({})
      ctx.refresh()

      // THE HEADER HAS TO MOVE TOO. The split renames THIS consignment, and
      // `consignmentNumber` is form state seeded at load - so without this the
      // page said "Batch created. 176 is now 176-1" in the panel while the
      // heading two inches above still read "Edit Consignment 176". Two
      // numbers for one record on one screen, which is the whole failure the
      // numbering rules exist to prevent.
      //
      // Taken from the API's `numbering` block rather than assembled here: the
      // server is what decides what a batch is called (§0.4), and it has just
      // said so in the response. `shouldDirty: false` because nothing the
      // operator typed has changed - marking the form dirty would raise an
      // "unsaved changes" prompt on the way out of a step they did not edit.
      const mine = res.numbering.batches.find(
        (b) => String(b.consignment_id) === String(watch('systemId')),
      )
      if (mine) setValue('consignmentNumber', mine.consignment_number, { shouldDirty: false })
    } catch (e) {
      // The server's own words. It refuses an over-allocation naming the item
      // and the overage, and an order line that ordered nothing with the fix —
      // restating either here would be a second copy that drifts.
      setError(e instanceof ApiError ? e.message : 'Could not create the batch')
    } finally {
      setCreating(false)
    }
  }

  if (rows.length === 0) return null

  return (
    <section className="rounded-xl border border-line bg-surface">
      <h3 className="flex items-center justify-between border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
        <span>Allocation — what this order bought, and where it has gone</span>
        {pending.length > 0 && (
          <span className="rounded-full bg-[var(--color-watch)]/15 px-2 py-0.5 text-[11px] font-medium normal-case text-[var(--color-watch)]">
            {pending.length} item{pending.length > 1 ? 's' : ''} pending allocation
          </span>
        )}
      </h3>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="bg-canvas-alt text-xs text-muted">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Item</th>
              <th className="px-3 py-2 text-right font-medium">Ordered</th>
              <th className="px-3 py-2 text-right font-medium">Allocated</th>
              <th className="px-3 py-2 text-right font-medium">Outstanding</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const out = n(r.outstanding_quantity)
              return (
                <tr key={r.order_item_id} className="border-t border-line">
                  <td className="px-3 py-2">
                    {r.item || <span className="text-muted">Unnamed item</span>}
                    {r.item_code && <div className="text-[11px] text-muted">{r.item_code}</div>}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {qty(r.ordered_quantity, r.unit_of_measurement)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {qty(r.allocated_quantity, r.unit_of_measurement)}
                  </td>
                  <td className={`px-3 py-2 text-right tabular-nums ${out > 0 ? 'font-semibold text-[var(--color-watch)]' : 'text-muted'}`}>
                    {qty(r.outstanding_quantity, r.unit_of_measurement)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* SIBLINGS. Read-only, and present even when there is only one, so the
          screen reads the same before and after a split. */}
      {ctx.batches.length > 0 && (
        <div className="border-t border-line px-4 py-3">
          <div className="mb-2 text-xs font-medium text-muted">Batches on this order</div>
          <div className="flex flex-wrap gap-2">
            {ctx.batches.map((b) => (
              <div
                key={b.id}
                className={`rounded-lg border px-3 py-2 text-xs ${
                  String(b.id) === watch('systemId')
                    ? 'border-brand bg-brand/5' : 'border-line'
                }`}
              >
                <div className="font-semibold tabular-nums">{b.consignment_number}</div>
                <div className="text-muted">{b.current_status || 'No status'}</div>
                <div className="text-muted">{b.etd ? `ETD ${b.etd}` : 'No ETD yet'}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
        <Button
          type="button"
          variant="outline"
          disabled={pending.length === 0 || creating}
          onClick={() => { setError(null); setResult(null); setConfirm(true) }}
        >
          Create next batch
        </Button>
        <span className="text-xs text-muted">
          {pending.length === 0
            ? 'Everything this order bought is allocated to a batch.'
            : 'The outstanding quantity becomes a new arrival on this order.'}
        </span>
      </div>

      {error && (
        <div className="border-t border-line px-4 py-3 text-sm text-[var(--color-late)]">{error}</div>
      )}

      {/* WHAT ACTUALLY HAPPENED, after the fact, from the API's own numbering
          block rather than from diffing two fetches (§3.5a). */}
      {result && (
        <div className="border-t border-line px-4 py-3 text-sm">
          <div className="font-medium text-ink">Batch created.</div>
          <ul className="mt-1 space-y-0.5 text-xs text-muted">
            {result.batches.map((b) => (
              <li key={b.consignment_id} className="tabular-nums">
                {b.previous_consignment_number
                  ? <>{b.previous_consignment_number} is now <span className="font-semibold text-ink">{b.consignment_number}</span></>
                  : <>{b.consignment_number} — new</>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {confirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-xl border border-line bg-surface p-5 shadow-xl">
            <h4 className="text-base font-semibold text-ink">Create the next batch?</h4>

            {/* THE RENUMBERING WARNING, WITH THE NUMBERS IN IT.
                "Numbers may change" is a dialog people click through; showing
                177 becoming 177-1 is the thing that makes an operator stop and
                think about the paperwork they have already issued. */}
            {willRenumber ? (
              <p className="mt-2 rounded-lg bg-[var(--color-watch)]/10 px-3 py-2 text-sm text-ink">
                This renames the consignment you are looking at.
                <span className="mt-1 block font-semibold tabular-nums">
                  {base} → {base}-1
                </span>
                <span className="block text-xs text-muted">
                  The new batch will be {base}-{nextSeq}. Anything already issued
                  quoting {base} will need the suffix. Numbers are permanent —
                  deleting a batch later does not give {base} back.
                </span>
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">
                This order has already split, so no existing number changes. The
                new batch will be <span className="font-semibold tabular-nums text-ink">{base}-{nextSeq}</span>.
              </p>
            )}

            <div className="mt-3 space-y-2">
              <div className="text-xs font-medium text-muted">How much goes into it?</div>
              {pending.map((r) => (
                <label key={r.order_item_id} className="flex items-center justify-between gap-3 text-sm">
                  <span className="truncate">{r.item || `Order line ${r.order_item_id}`}</span>
                  <span className="flex items-center gap-2">
                    <input
                      type="number"
                      min="0"
                      step="any"
                      className="w-28 rounded border border-line bg-canvas px-2 py-1 text-right tabular-nums"
                      value={draftAlloc[r.order_item_id] ?? String(n(r.outstanding_quantity))}
                      onChange={(e) => setDraftAlloc((d) => ({ ...d, [r.order_item_id]: e.target.value }))}
                    />
                    <span className="w-10 text-xs text-muted">{r.unit_of_measurement}</span>
                  </span>
                </label>
              ))}
              <div className="text-[11px] text-muted">
                Defaults to everything outstanding. The server refuses more than
                the order has left.
              </div>
            </div>

            {error && <div className="mt-3 text-sm text-[var(--color-late)]">{error}</div>}

            <div className="mt-4 flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setConfirm(false)} disabled={creating}>
                Cancel
              </Button>
              <Button type="button" onClick={() => void create()} disabled={creating}>
                {creating ? 'Creating…' : willRenumber ? `Create ${base}-${nextSeq} and rename ${base}` : `Create ${base}-${nextSeq}`}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
