import { useFormContext, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, elcTotal, alcTotal, landedCostVariance, alcPerUnit,
  foreignTotal, bankChargesTotal,
} from '../../schema'
import { Field, Input, Callout, CarriedContext, PendingBanner } from './fields'

const pkr = (v: number | undefined) => (v === undefined ? '—' : `PKR ${Math.round(v).toLocaleString('en-US')}`)

/**
 * Step 7 — Landed Cost.
 *
 * ELC and ALC are entered manually, per item, in PKR — the system never
 * calculates them, because accounts hold charges the system can't see. What the
 * system does show, as reference only, is goods value + bank charges +
 * demurrage, so the person entering ALC has a sanity figure. Per-unit ALC is
 * the number supplier-comparison reports key on, since quantities differ
 * between shipments. Optional and finalised long after arrival.
 */
export function Step7LandedCost() {
  const { register, control, watch } = useFormContext<ConsignmentDraft>()
  const items = useWatch({ control, name: 'items' }) ?? []
  const rate = watch('exchangeRate')
  const payments = watch('payments')
  const demurrage = watch('demurrageCost')

  const goodsPkr = rate !== undefined ? foreignTotal({ items } as ConsignmentDraft) * rate : undefined
  const charges = bankChargesTotal({ payments } as ConsignmentDraft)
  const reference = goodsPkr !== undefined ? goodsPkr + charges + (demurrage ?? 0) : undefined

  const elc = elcTotal({ items } as ConsignmentDraft)
  const alc = alcTotal({ items } as ConsignmentDraft)
  const variance = landedCostVariance({ items } as ConsignmentDraft)

  const pendingAlc = items.some((it) => it.alcPkr === undefined)

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Consignment', value: watch('systemId') || 'New' },
        { label: 'Supplier', value: watch('supplier') },
        { label: 'Reference (goods + charges + demurrage)', value: pkr(reference) },
      ]} />

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Landed cost per item — entered manually in PKR
        </h3>
        <div className="overflow-auto p-4">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-medium">Item</th>
                <th className="px-2 py-1.5 text-right font-medium">Qty</th>
                <th className="px-2 py-1.5 text-right font-medium">Estimated LC (PKR)</th>
                <th className="px-2 py-1.5 text-right font-medium">Actual LC (PKR)</th>
                <th className="px-2 py-1.5 text-right font-medium">ALC / unit</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-2 py-2">
                    <div>{it.itemName || `Item ${i + 1}`}</div>
                    <div className="text-[11px] text-muted">{it.itemCode}</div>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{it.quantity ?? '—'}</td>
                  <td className="px-2 py-2">
                    <Input type="number" min="0" step="any" className="text-right tabular-nums" {...register(`items.${i}.elcPkr`)} placeholder="0" />
                  </td>
                  <td className="px-2 py-2">
                    <Input type="number" min="0" step="any" className="text-right tabular-nums" {...register(`items.${i}.alcPkr`)} placeholder="0" />
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{pkr(alcPerUnit(it))}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={5} className="px-2 py-6 text-center text-muted">Add items in step 1 first.</td></tr>
              )}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-line font-semibold">
                <td className="px-2 py-2" colSpan={2}>Totals</td>
                <td className="px-2 py-2 text-right tabular-nums">{pkr(elc || undefined)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{pkr(alc || undefined)}</td>
                <td className="px-2 py-2" />
              </tr>
              {variance && (
                <tr className={variance.absolute > 0 ? 'text-risk' : 'text-[var(--color-success,#1F7A5A)]'}>
                  <td className="px-2 py-1" colSpan={2}>Variance (actual vs estimated)</td>
                  <td className="px-2 py-1 text-right tabular-nums" colSpan={2}>
                    {pkr(Math.abs(variance.absolute))} ({variance.percent > 0 ? '+' : ''}{variance.percent.toFixed(1)}%)
                  </td>
                  <td />
                </tr>
              )}
            </tfoot>
          </table>
        </div>
      </section>

      {/* reference figures the system CAN see */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Reference figures — for comparison only, not the landed cost
        </h3>
        <div className="grid grid-cols-2 gap-px bg-line sm:grid-cols-4">
          <Readout label="Goods value (PKR)" value={pkr(goodsPkr)} />
          <Readout label="Bank charges" value={pkr(charges || undefined)} />
          <Readout label="Demurrage" value={pkr(demurrage)} />
          <Readout label="Reference total" value={pkr(reference)} strong />
        </div>
      </section>

      <PendingBanner
        items={pendingAlc ? ['Actual landed cost on one or more items'] : []}
        note="Entered once accounts finalise duty, freight and agent fees. Until then this consignment is left out of supplier-comparison reports."
      />

      <Callout>
        The system deliberately doesn't compute landed cost — accounts carry duty and charges it can't see.
        The reference total above (goods + bank charges + demurrage) is only a sanity check for whoever keys
        the actual figure. Per-unit ALC is what supplier comparisons are built on, because two shipments of
        the same item rarely have the same quantity.
      </Callout>
    </div>
  )
}

function Readout({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="bg-surface px-3.5 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 tabular-nums ${strong ? 'text-[14px] font-semibold' : 'text-[13px]'}`}>{value}</div>
    </div>
  )
}
