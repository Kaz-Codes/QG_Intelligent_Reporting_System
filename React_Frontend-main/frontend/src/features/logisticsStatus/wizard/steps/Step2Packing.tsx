import { useParams } from 'react-router-dom'
import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { QG_FACTORIES } from '@/features/truckingStatus/schema'
import { getCrossBatchItems, outstandingByItemAcrossMo } from '@/lib/logisticsStatusData'
import {
  PACKING_STATUSES, emptyPackage, packingDelay, packingSavings,
  totalPackageGrossWeight, totalPackageNetWeight,
  type LogisticsDraft, type LogisticsPackage, type LogisticsItem, type PackageAllocation, type CrossBatchItem,
} from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

function DerivedField({ label, value, derivation }: { label: string; value: string; derivation: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      <div className="flex h-10 w-full items-center rounded-lg border border-line bg-canvas-alt px-3 text-sm tabular-nums text-muted">
        {value}
      </div>
      <p className="text-xs text-muted">{derivation}</p>
    </div>
  )
}

/**
 * One row in a package's allocation sub-table: "how much of this item is in
 * this package". Reads/writes `packages.{pkgIndex}.allocations` directly via
 * setValue rather than a nested useFieldArray, since the set of rows is
 * driven by the order's fixed item list (plus any cross-batch items), not
 * independently added/removed. Matched by (itemId, sourceOrderId) so a
 * cross-batch item never collides with a same-id local one.
 */
function AllocationRow({
  pkgIndex, item, sourceOrderId, sourceBatchLabel, qty, allocations, onChange,
}: {
  pkgIndex: number
  item: LogisticsItem
  sourceOrderId: string
  sourceBatchLabel?: string
  /** The quantity shown in the second column — the item's own order quantity
   *  for local items, or its outstanding quantity (across the whole MO
   *  group) for cross-batch items — see the two call sites below. */
  qty: number | undefined
  allocations: PackageAllocation[]
  onChange: (next: PackageAllocation[]) => void
}) {
  const existing = allocations.find((a) => a.itemId === item.id && a.sourceOrderId === sourceOrderId)
  const value = existing?.quantity ?? ''

  function handleChange(raw: string) {
    const qty = raw === '' ? undefined : Number(raw)
    const next = allocations.filter((a) => !(a.itemId === item.id && a.sourceOrderId === sourceOrderId))
    next.push({ id: existing?.id ?? `alloc-${pkgIndex}-${sourceOrderId}-${item.id}`, itemId: item.id, sourceOrderId, quantity: qty })
    onChange(next)
  }

  return (
    <tr className="border-t border-line">
      <td className="py-1.5 pr-3">
        <span className="inline-flex items-center gap-1.5">
          {item.jobNo
            ? <span className="rounded bg-canvas-alt px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted" title="Job number">{item.jobNo}</span>
            : <span className="rounded bg-canvas-alt px-1.5 py-0.5 text-[11px] text-muted" title="No job number yet">No job #</span>}
          <span>{item.itemDetail || <span className="italic text-muted">Not named</span>}</span>
        </span>
        {sourceBatchLabel && <span className="ml-1.5 text-[11px] text-muted">({sourceBatchLabel})</span>}
      </td>
      <td className="py-1.5 pr-3 text-muted">{qty ?? '—'}</td>
      <td className="py-1.5">
        <input
          type="number"
          step="1"
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          className="h-8 w-28 rounded border border-line bg-surface px-2 text-sm tabular-nums"
        />
      </td>
    </tr>
  )
}

/**
 * Step 2 — Packing (replaces Transportation).
 *
 * One panel per physical package: cost/status/weight fields, a derived
 * packing delay and savings, and a per-item allocation sub-table (a package
 * routinely holds partial quantities from more than one item). When this
 * order's MO number is shared with sibling batches, each package also gets
 * an "Items from other batches" section — items are SHARED across batches
 * under the same MO (pull/reference, never copied), so a package in Batch 2
 * can allocate quantity from an item that physically belongs to Batch 1.
 *
 * Below every package panel, one summary shows each item's outstanding
 * (unallocated) quantity across ALL packages combined, and the whole step
 * ends with a footer totalling net/gross weight across every package.
 */
export function Step2Packing() {
  const { id } = useParams<{ id: string }>()
  const { control, register, setValue } = useFormContext<LogisticsDraft>()
  const { fields, append, remove } = useFieldArray({ control, name: 'packages' })
  const items = (useWatch({ control, name: 'items' }) ?? []) as LogisticsItem[]
  const packages = (useWatch({ control, name: 'packages' }) ?? []) as LogisticsPackage[]
  const moNo = useWatch({ control, name: 'moNo' })

  const crossBatchItems: CrossBatchItem[] = id && moNo ? getCrossBatchItems(moNo, id) : []
  const allItems = [...items, ...crossBatchItems.map((c) => c.item)]

  // MO-aware: accounts for allocations across every sibling batch's
  // packages too, not just this order's own — a sibling package can draw
  // against this order's items, and vice versa.
  const outstanding = outstandingByItemAcrossMo(items, packages, moNo, id ?? '')
  const crossOutstanding = outstandingByItemAcrossMo(crossBatchItems.map((c) => c.item), packages, moNo, id ?? '')
  const totalNet = totalPackageNetWeight(packages, allItems)
  const totalGross = totalPackageGrossWeight(packages)

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        {fields.map((f, i) => {
          const pkg = packages[i] as LogisticsPackage | undefined
          const delay = pkg ? packingDelay(pkg, items) : null
          const savings = pkg ? packingSavings(pkg) : null
          const allocations = pkg?.allocations ?? []

          return (
            <section key={f.id} className="rounded-xl border border-line bg-surface">
              <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Package {i + 1}</h3>
                <span className="ml-auto" />
                <button
                  type="button"
                  onClick={() => remove(i)}
                  disabled={fields.length === 1}
                  className="h-6 w-6 rounded border border-line text-muted hover:border-risk hover:text-risk disabled:opacity-35"
                  title="Remove package"
                >×</button>
              </div>

              <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.colourCode`}>Colour Code</Label>
                  <Input id={`packages.${i}.colourCode`} {...register(`packages.${i}.colourCode`)} />
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.packingWorks`}>Packing Works</Label>
                  <select id={`packages.${i}.packingWorks`} className={selectClass} {...register(`packages.${i}.packingWorks`)}>
                    <option value="">Select a factory…</option>
                    {QG_FACTORIES.map((f2) => (
                      <option key={f2} value={f2}>{f2}</option>
                    ))}
                  </select>
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.packingReadyDate`}>Packing Ready Date</Label>
                  <Input id={`packages.${i}.packingReadyDate`} type="date" {...register(`packages.${i}.packingReadyDate`)} />
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.packingDate`}>Packing Date</Label>
                  <Input id={`packages.${i}.packingDate`} type="date" {...register(`packages.${i}.packingDate`)} />
                </div>

                <DerivedField
                  label="Packing Delay (days)"
                  value={delay === null ? '—' : String(delay)}
                  derivation="Earliest allocated item's planned (or actual) RFD − packing date"
                />

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.quotedPackingCost`}>Quoted Packing Cost (Rs.)</Label>
                  <Input id={`packages.${i}.quotedPackingCost`} type="number" step="0.01" {...register(`packages.${i}.quotedPackingCost`)} />
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.actualPackingCost`}>Actual Packing Cost (Rs.)</Label>
                  <Input id={`packages.${i}.actualPackingCost`} type="number" step="0.01" {...register(`packages.${i}.actualPackingCost`)} />
                </div>

                <DerivedField
                  label="Savings (Rs.)"
                  value={savings === null ? '—' : savings.toFixed(2)}
                  derivation="Quoted packing cost − actual packing cost"
                />

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.grossWeight`}>Gross Weight (kg)</Label>
                  <Input id={`packages.${i}.grossWeight`} type="number" step="0.01" {...register(`packages.${i}.grossWeight`)} />
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`packages.${i}.status`}>Status</Label>
                  <select id={`packages.${i}.status`} className={selectClass} {...register(`packages.${i}.status`)}>
                    {PACKING_STATUSES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* per-item allocation into this package */}
              <div className="border-t border-line px-4 py-3">
                <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  Item allocation — quantity of each item placed in this package
                </h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs text-muted">
                      <tr>
                        <th className="pb-1 pr-3">Item</th>
                        <th className="pb-1 pr-3">Order qty</th>
                        <th className="pb-1">In this package</th>
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((item) => (
                        <AllocationRow
                          key={item.id}
                          pkgIndex={i}
                          item={item}
                          sourceOrderId={id ?? ''}
                          qty={item.quantity}
                          allocations={allocations}
                          onChange={(next) => setValue(`packages.${i}.allocations`, next, { shouldDirty: true })}
                        />
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* cross-batch allocation — items owned by sibling batches under the same MO */}
              {crossBatchItems.length > 0 && (
                <div className="border-t border-line bg-canvas-alt/30 px-4 py-3">
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                    Items from other batches — shared under MO {moNo}
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-xs text-muted">
                        <tr>
                          <th className="pb-1 pr-3">Item</th>
                          <th className="pb-1 pr-3">Outstanding</th>
                          <th className="pb-1">In this package</th>
                        </tr>
                      </thead>
                      <tbody>
                        {crossBatchItems.map((c) => (
                          <AllocationRow
                            key={`${c.sourceOrderId}-${c.item.id}`}
                            pkgIndex={i}
                            item={c.item}
                            sourceOrderId={c.sourceOrderId}
                            sourceBatchLabel={c.sourceBatchLabel}
                            qty={crossOutstanding[c.item.id]}
                            allocations={allocations}
                            onChange={(next) => setValue(`packages.${i}.allocations`, next, { shouldDirty: true })}
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </section>
          )
        })}

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => append(emptyPackage(`package-${Date.now()}`))}
            className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-muted"
          >
            + Add package
          </button>
          <span className="text-xs text-muted">{fields.length} package{fields.length === 1 ? '' : 's'}</span>
        </div>
      </div>

      {/* outstanding-quantity summary across ALL packages */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Outstanding quantity — across all packages combined
        </h3>
        <div className="overflow-x-auto p-4">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="pb-1 pr-3">Item</th>
                <th className="pb-1 pr-3">Order qty</th>
                <th className="pb-1">Outstanding</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const rest = outstanding[item.id] ?? item.quantity ?? 0
                return (
                  <tr key={item.id} className="border-t border-line">
                    <td className="py-1.5 pr-3">{item.itemDetail || <span className="italic text-muted">Not named</span>}</td>
                    <td className="py-1.5 pr-3 tabular-nums text-muted">{item.quantity ?? '—'}</td>
                    <td className="py-1.5 tabular-nums">
                      {rest === 0
                        ? <span className="text-[var(--color-healthy)]">Fully allocated</span>
                        : <span className={rest < 0 ? 'text-[var(--color-risk)]' : 'text-[var(--color-watch)]'}>{rest}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* footer totals across all packages */}
      <div className="grid gap-4 sm:grid-cols-2">
        <DerivedField
          label="Total Package Net Weight (kg)"
          value={totalNet.toLocaleString()}
          derivation="Sum of every allocated quantity × its item's unit weight, across all packages"
        />
        <DerivedField
          label="Total Package Gross Weight (kg)"
          value={totalGross.toLocaleString()}
          derivation="Sum of each package's own gross weight"
        />
      </div>
    </div>
  )
}
