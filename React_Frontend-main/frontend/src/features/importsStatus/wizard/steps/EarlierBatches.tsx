import type { ApiConsignment } from '@/lib/api/imports'
import { useBatchContext } from '../BatchContext'

/**
 * The earlier batches of this order, read-only, above the section the operator
 * is actually filling in.
 *
 * WHY IT EXISTS. Route, schedule and clearance are PER BATCH (requirements,
 * "What is shared, what is per-batch"), and a later batch's own section starts
 * empty. Without the earlier ones on screen an operator filling in batch 3 has
 * no way to see what batches 1 and 2 did without opening them in another tab —
 * which is the moment they start copying values across that were never meant to
 * match.
 *
 * ONE SHELL, TWO CALLERS. Step 3 shows route and schedule; Step 6 shows
 * clearance. The shape is identical and only the columns differ, so the columns
 * are a prop rather than the component being written twice — two copies of a
 * read-only table drift in exactly the way that makes one of them wrong and
 * nobody notice.
 *
 * IT RENDERS NOTHING ON AN UNSPLIT ORDER. There is no "earlier batch" to show,
 * and an empty panel that says so on every ordinary consignment is noise on the
 * 99% to serve the 1%.
 */

export interface BatchColumn {
  label: string
  value: (b: ApiConsignment) => string
}

const dash = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : String(v))

export const SHIPPING_COLUMNS: BatchColumn[] = [
  { label: 'Route', value: (b) => [b.loading_port?.name, b.delivery_port?.name].filter(Boolean).join(' → ') || '—' },
  { label: 'Mode', value: (b) => dash(b.mode_of_shipment) },
  { label: 'ETD / ETA', value: (b) => [b.etd, b.eta].filter(Boolean).join(' → ') || '—' },
  { label: 'Status', value: (b) => dash(b.current_status) },
]

export const CLEARANCE_COLUMNS: BatchColumn[] = [
  { label: 'GD number', value: (b) => dash(b.gd_number) },
  { label: 'Clearing agent', value: (b) => dash(b.clearing_agent?.name) },
  { label: 'Gate out', value: (b) => dash(b.gate_out_date) },
  { label: 'Free days', value: (b) => dash(b.free_days_allowed) },
]

export function EarlierBatches({ title, columns }: { title: string; columns: BatchColumn[] }) {
  const ctx = useBatchContext()
  const mine = ctx.batchSequence ?? 0

  // STRICTLY EARLIER, by SEQUENCE. Not "every other batch": a later batch has
  // not happened yet and showing its empty route above the one being filled in
  // would read as a gap somebody has to close.
  const earlier = ctx.batches.filter((b) => (b.batch_sequence ?? 0) < mine)

  if (!ctx.isSplit || earlier.length === 0) return null

  return (
    <section className="rounded-xl border border-line bg-canvas-alt">
      <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
        {title} — read-only
      </h3>
      <div className="divide-y divide-line">
        {earlier.map((b) => (
          <div key={b.id} className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-5">
            <div>
              <div className="text-[11px] text-muted">Batch</div>
              <div className="font-semibold tabular-nums">{b.consignment_number}</div>
            </div>
            {columns.map((c) => (
              <div key={c.label}>
                <div className="text-[11px] text-muted">{c.label}</div>
                <div>{c.value(b)}</div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  )
}
