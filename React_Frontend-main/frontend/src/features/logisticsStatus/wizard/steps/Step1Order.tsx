import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  ORDER_TYPES, DEPARTMENTS, INCOTERMS, emptyItem, itemPendingFields, itemNetWeight, batchDisplayLabel,
  type LogisticsDraft, type LogisticsItem, type LogisticsPackage,
} from '../../schema'
import {
  isKnownLogisticsOrder, nextBatchNoForMo, getMoGroupSummary, getCrossBatchItems, outstandingByItemAcrossMo,
} from '@/lib/logisticsStatusData'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

/** Read-only derived output: greyed, with the derivation stated. Mirrors the
 * imports module's "calculated values are computed, never keyed in" rule. */
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
 * Step 1 — Order details.
 *
 * Order-level fields (department, type, origin, customer, MO no., batch,
 * incoterm) apply to the whole order. Job#, item detail, quantity, unit
 * weight, and the Planned/Actual RFD dates are per item — an order can
 * bundle several items, each running its own production timeline. Gross
 * weight is not tracked here — it's a package-level figure (see Step 2).
 *
 * Items are simplified from the previous design: no IDM, export number, or
 * batch number on the item line — those concepts moved to (or were replaced
 * by) the order-level MO/batch system.
 *
 * Batch No. is auto-assigned (Batch 1, 2, ... per MO number, see
 * lib/logisticsStatusData.ts's nextBatchNoForMo) and shown here read-only;
 * only its display label is user-editable.
 *
 * Net weight is DERIVED (quantity × unit weight, via itemNetWeight() in
 * schema.ts) — shown read-only, never typed in directly.
 *
 * RFD date changes are NOT logged here. The audit trail (recordRfdChange) is
 * wired into the save path in lib/logisticsStatusData.ts's
 * updateLogisticsOrder(), which is where the item's previous value is
 * actually known — see the comment there.
 */
export function Step1Order() {
  const { id } = useParams<{ id: string }>()
  const { register, control, watch, setValue, formState: { errors } } = useFormContext<LogisticsDraft>()
  // Single rules driver for the screen — origin shape keys off this.
  const orderType = useWatch({ control, name: 'orderType' })
  const isExport = orderType === 'Export'
  const batchNo = useWatch({ control, name: 'batchNo' })
  const batchLabel = useWatch({ control, name: 'batchLabel' })
  const moNo = useWatch({ control, name: 'moNo' }) ?? ''
  const packages = (useWatch({ control, name: 'packages' }) ?? []) as LogisticsPackage[]

  // isNew mirrors the wizard's own definition (a real record already exists
  // vs. still-in-progress creation) — only a new order's batchNo should be
  // auto-driven by the MO field; an existing order's batchNo was assigned
  // once at creation and must not silently shift just from revisiting Step 1.
  const isNew = !id || !isKnownLogisticsOrder(id)
  const excludeId = id ?? ''
  const moSummary = getMoGroupSummary(moNo, excludeId)
  const nextBatch = nextBatchNoForMo(moNo)

  // Auto-detect: as soon as the MO field resolves to an existing (or newly
  // empty) value, keep batchNo in sync — batch 1 for no MO / a brand-new MO,
  // one past the highest sibling batch for an MO that already exists. This
  // runs on every moNo change (not just onBlur) so the "Batch" display and
  // the cross-batch preview below update live as the user types, and it's
  // gated on isNew so editing an existing order never reassigns its batch.
  useEffect(() => {
    if (!isNew) return
    if (nextBatch !== batchNo) setValue('batchNo', nextBatch, { shouldDirty: false })
  }, [isNew, nextBatch, batchNo, setValue])

  const crossBatchItems = getCrossBatchItems(moNo, excludeId)
  const crossOutstanding = outstandingByItemAcrossMo(crossBatchItems.map((c) => c.item), packages, moNo, excludeId)

  const { fields, append, remove } = useFieldArray({ control, name: 'items' })
  const items = watch('items')

  return (
    <div className="space-y-5">
      {/* order-level fields */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Order details — applies to the whole order
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="orderType">Order Type</Label>
            <select id="orderType" className={selectClass} {...register('orderType')}>
              {ORDER_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            {errors.orderType && <p className="text-xs text-risk">{errors.orderType.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="department">Department</Label>
            <select id="department" className={selectClass} {...register('department')}>
              {DEPARTMENTS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            {errors.department && <p className="text-xs text-risk">{errors.department.message}</p>}
          </div>

          {/* Origin: country for exports; city + province for local. */}
          {isExport ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="originCountry">Customer Origin — Country</Label>
              <Input id="originCountry" placeholder="e.g. United Arab Emirates" {...register('originCountry')} />
              {errors.originCountry && <p className="text-xs text-risk">{errors.originCountry.message}</p>}
            </div>
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="originCity">Customer Origin — City</Label>
                <Input id="originCity" placeholder="e.g. Lahore" {...register('originCity')} />
                {errors.originCity && <p className="text-xs text-risk">{errors.originCity.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="originProvince">Customer Origin — Province</Label>
                <Input id="originProvince" placeholder="e.g. Punjab" {...register('originProvince')} />
                {errors.originProvince && <p className="text-xs text-risk">{errors.originProvince.message}</p>}
              </div>
            </>
          )}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="customerName">Customer Name</Label>
            <Input id="customerName" {...register('customerName')} />
            {errors.customerName && <p className="text-xs text-risk">{errors.customerName.message}</p>}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="moNo">MO No. <span className="font-normal text-muted">(optional)</span></Label>
            <Input id="moNo" placeholder="Marketing/Manufacturing Order no." {...register('moNo')} />
            {isNew && moSummary ? (
              <p className="text-xs text-brand">
                MO {moNo} already exists with {moSummary.itemCount} item{moSummary.itemCount === 1 ? '' : 's'} across{' '}
                {moSummary.batchCount} batch{moSummary.batchCount === 1 ? '' : 'es'} — creating Batch {nextBatch}.
              </p>
            ) : (
              <p className="text-xs text-muted">
                Entering an MO that already exists auto-creates this order as the next batch under it.
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Batch</Label>
            <div className="flex items-center gap-2">
              <div className="flex h-10 shrink-0 items-center rounded-lg border border-line bg-canvas-alt px-3 text-sm tabular-nums text-muted">
                {batchDisplayLabel(batchNo ?? 1)}
              </div>
              <Input
                placeholder={`Batch ${batchNo ?? 1}`}
                {...register('batchLabel')}
              />
            </div>
            <p className="text-xs text-muted">
              Batch number is auto-assigned per MO; the label {batchLabel ? '(shown above)' : ''} is renameable.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="incoterm">Incoterm <span className="font-normal text-muted">(optional)</span></Label>
            <select id="incoterm" className={selectClass} {...register('incoterm')}>
              <option value="">Select…</option>
              {INCOTERMS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {/* items */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Items — quantity and weight are per item
        </h3>

        <div className="space-y-3 p-4">
          {fields.map((f, i) => {
            const item = items?.[i] as LogisticsItem | undefined
            const pending = item ? itemPendingFields(item) : []
            const netWeight = item ? itemNetWeight(item) : 0
            return (
              <div key={f.id} className="rounded-lg border border-line bg-canvas-alt/40">
                <div className="flex items-center gap-2 border-b border-line/60 px-3 py-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Item {i + 1}</span>
                  <span className="truncate text-[13px] font-medium">{item?.itemDetail || 'Not named yet'}</span>
                  <span className="ml-auto" />
                  {pending.length > 0
                    ? <span className="cursor-help rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-watch)]" title={`Still to add: ${pending.join(', ')}`}>{pending.length} pending</span>
                    : <span className="rounded border border-[var(--color-healthy)]/30 bg-[var(--color-healthy-bg)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-healthy)]">Complete</span>}
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    disabled={fields.length === 1}
                    className="ml-1 h-6 w-6 rounded border border-line text-muted hover:border-risk hover:text-risk disabled:opacity-35"
                    title="Remove item"
                  >×</button>
                </div>

                <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`items.${i}.jobNo`}>Job #</Label>
                    <Input id={`items.${i}.jobNo`} {...register(`items.${i}.jobNo`)} />
                  </div>

                  <div className="flex flex-col gap-1.5 sm:col-span-1 lg:col-span-3">
                    <Label htmlFor={`items.${i}.itemDetail`}>Item Detail</Label>
                    <Input id={`items.${i}.itemDetail`} {...register(`items.${i}.itemDetail`)} />
                    {errors.items?.[i]?.itemDetail && <p className="text-xs text-risk">{errors.items[i]?.itemDetail?.message}</p>}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`items.${i}.quantity`}>Quantity</Label>
                    <Input id={`items.${i}.quantity`} type="number" step="1" {...register(`items.${i}.quantity`)} />
                    {errors.items?.[i]?.quantity && <p className="text-xs text-risk">{errors.items[i]?.quantity?.message}</p>}
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`items.${i}.unitWeight`}>Unit Weight (kg)</Label>
                    <Input id={`items.${i}.unitWeight`} type="number" step="0.01" {...register(`items.${i}.unitWeight`)} />
                  </div>

                  <DerivedField
                    label="Net Weight (kg)"
                    value={netWeight ? netWeight.toLocaleString() : '—'}
                    derivation="Quantity × unit weight"
                  />

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`items.${i}.plannedRfdDate`}>Planned RFD Date</Label>
                    <Input id={`items.${i}.plannedRfdDate`} type="date" {...register(`items.${i}.plannedRfdDate`)} />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor={`items.${i}.actualRfdDate`}>Actual RFD Date</Label>
                    <Input id={`items.${i}.actualRfdDate`} type="date" {...register(`items.${i}.actualRfdDate`)} />
                  </div>
                </div>
              </div>
            )
          })}

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => append(emptyItem(`item-${Date.now()}`))}
              className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-muted"
            >
              + Add item
            </button>
            <span className="text-xs text-muted">{fields.length} item{fields.length === 1 ? '' : 's'}</span>
          </div>
        </div>
      </section>

      {/* read-only preview of sibling batches' items — context for the
          cross-batch allocation the user will do in Step 2 (Packing) */}
      {crossBatchItems.length > 0 && (
        <section className="rounded-xl border border-line bg-canvas-alt/30">
          <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
            Items from previous batches — read-only, shared under MO {moNo}
          </h3>
          <div className="overflow-x-auto p-4">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="pb-1 pr-3">Batch</th>
                  <th className="pb-1 pr-3">Job #</th>
                  <th className="pb-1 pr-3">Item</th>
                  <th className="pb-1 pr-3">Quantity</th>
                  <th className="pb-1">Outstanding</th>
                </tr>
              </thead>
              <tbody>
                {crossBatchItems.map((c) => {
                  const rest = crossOutstanding[c.item.id] ?? c.item.quantity ?? 0
                  return (
                    <tr key={`${c.sourceOrderId}-${c.item.id}`} className="border-t border-line">
                      <td className="py-1.5 pr-3 text-muted">{c.sourceBatchLabel}</td>
                      <td className="py-1.5 pr-3 tabular-nums text-muted">{c.item.jobNo || '—'}</td>
                      <td className="py-1.5 pr-3">{c.item.itemDetail || <span className="italic text-muted">Not named</span>}</td>
                      <td className="py-1.5 pr-3 tabular-nums text-muted">{c.item.quantity ?? '—'}</td>
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
          <p className="px-4 pb-3 text-xs text-muted">
            Not editable here — allocate against these in Packing (Step 2). You can still add new items to this batch above.
          </p>
        </section>
      )}
    </div>
  )
}
