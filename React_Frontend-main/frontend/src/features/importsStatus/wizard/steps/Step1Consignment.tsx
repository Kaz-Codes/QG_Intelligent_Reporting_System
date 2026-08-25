import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, type ConsignmentItem,
  REQUISITION_TYPES, REQUISITION_FIELDS, CONSIGNMENT_TYPES, UNITS_OF_MEASURE, INCOTERMS,
  emptyItem, itemPendingFields, requiredVsEtaDelay,
} from '../../schema'
import { Field, Input, Select } from './fields'
import { useMasters } from '../MastersContext'
import { Disclosure } from '@/components/Disclosure'

const CURRENCIES = ['USD', 'EUR', 'CNY', 'JPY', 'GBP', 'AED']
const ORIGINS = ['China', 'Germany', 'Italy', 'Japan', 'Korea, Republic of', 'Sweden', 'Türkiye', 'United States']

const REQ_LABEL: Record<string, string> = { store: 'Store', engineering: 'Engineering', others: 'Others' }
const FIELD_LABEL: Record<string, string> = {
  referenceNo: 'Reference number', jobNo: 'Job number', moNo: 'MO number', othersDescription: 'What is this item for?',
}
const REQ_LEAD: Record<string, string> = {
  store: 'Store item — reference number can be added later',
  engineering: 'Engineering item — reference, job and MO numbers can be added later',
  others: 'Describe what this item is for',
}

/**
 * Item code, required for every item except "Others" — those aren't drawn
 * from the item master, so there's often no code to give. Its own component
 * so `useWatch` can scope to this one item's requisitionType without
 * re-rendering the whole item list on every keystroke (the pattern used for
 * per-row reactive reads elsewhere, e.g. trucking's PackageAllocation).
 *
 * MIRRORED ON THE BACKEND: app/imports/helpers.py (submission_errors,
 * ITEM_CODE_NOT_REQUIRED_FOR) makes the same field optional, keyed off the
 * capitalised requisition type. Keep both in sync.
 */
function ItemCodeField({ index, error }: { index: number; error?: string }) {
  const { register, control } = useFormContext<ConsignmentDraft>()
  const requisitionType = useWatch({ control, name: `items.${index}.requisitionType` })
  const optional = requisitionType === 'others'

  return (
    <Field label="Item code" required={!optional} error={error}>
      <Input
        {...register(`items.${index}.itemCode`)}
        placeholder={optional ? 'Optional for Others' : undefined}
        autoComplete="off"
      />
    </Field>
  )
}

/**
 * Step 1 — Consignment.
 *
 * Header fields apply to the whole shipment; requisition details, item and
 * pricing fields belong to each item. Requisition type sits on the item because
 * one consignment can carry Store and Engineering items together.
 */
export function Step1Consignment() {
  const { register, control, watch, formState: { errors } } = useFormContext<ConsignmentDraft>()
  const { fields, append, remove } = useFieldArray({ control, name: 'items' })
  const items = watch('items')
  const requiredDelay = requiredVsEtaDelay({ requiredDate: watch('requiredDate'), eta: watch('eta') })
  const { branches, suppliers, loading: mastersLoading } = useMasters()

  return (
    <div className="space-y-5">
      {/* header */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Consignment details — applies to the whole shipment
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field
            label="Branch" htmlFor="branch" required error={errors.branch?.message}
            hint={mastersLoading ? 'Loading branches…' : undefined}
          >
            <Select id="branch" {...register('branch')} disabled={mastersLoading}>
              <option value="">Select…</option>
              {branches.map((b) => <option key={b.id}>{b.name}</option>)}
            </Select>
          </Field>

          <Field
            label="Supplier" htmlFor="supplier" required error={errors.supplier?.message}
            hint={mastersLoading ? 'Loading suppliers…' : 'From supplier master — a name that doesn’t match yet is kept, but won’t link until it’s added there'}
          >
            <Input id="supplier" list="dl-suppliers" {...register('supplier')} placeholder="Start typing…" autoComplete="off" />
            <datalist id="dl-suppliers">
              {suppliers.map((s) => <option key={s.id} value={s.name} />)}
            </datalist>
          </Field>

          <Field label="Country of origin" htmlFor="origin" required error={errors.origin?.message}>
            <Select id="origin" {...register('origin')}>
              <option value="">Select…</option>
              {ORIGINS.map((o) => <option key={o}>{o}</option>)}
            </Select>
          </Field>

          <Field label="Currency" htmlFor="currency" required error={errors.currency?.message}>
            <Select id="currency" {...register('currency')}>
              <option value="">Select…</option>
              {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>

          <Field label="Consignment type" htmlFor="consignmentType" hint="Can be filled later">
            <Select id="consignmentType" {...register('consignmentType')}>
              <option value="">Add later</option>
              {CONSIGNMENT_TYPES.map((t) => <option key={t} value={t}>{t === 'efs' ? 'EFS' : 'Regular import'}</option>)}
            </Select>
          </Field>

          <Field label="Incoterm" htmlFor="incoterm" hint="FOB shipments can be routed through Trucking Status">
            <Select id="incoterm" {...register('incoterm')}>
              <option value="">Add later</option>
              {INCOTERMS.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
          </Field>

          <Field label="PO date" htmlFor="poDate">
            <Input id="poDate" type="date" {...register('poDate')} />
          </Field>

          <Field label="Requisition date" htmlFor="requisitionDate" hint="When the need was first raised">
            <Input id="requisitionDate" type="date" {...register('requisitionDate')} />
          </Field>

          <Field label="Required date" htmlFor="requiredDate" hint="When the business actually needs it">
            <Input id="requiredDate" type="date" {...register('requiredDate')} />
          </Field>

          <Field label="Required vs. ETA">
            <div className="flex h-10 items-center px-1 text-sm tabular-nums">
              {requiredDelay === undefined
                ? <span className="text-muted">Add both dates to see this</span>
                : requiredDelay <= 0
                  ? <span className="text-[var(--color-healthy)]">On time{requiredDelay < 0 ? ` · ${-requiredDelay}d ahead` : ''}</span>
                  : <span className="font-medium text-[var(--color-risk)]">{requiredDelay}d late</span>}
            </div>
          </Field>
        </div>
      </section>

      {/* items */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Items — requisition details belong to each item, not the consignment
        </h3>

        <div className="space-y-3 p-4">
          {fields.map((f, i) => {
            const item = items?.[i] as ConsignmentItem | undefined
            const reqType = item?.requisitionType
            const pending = item ? itemPendingFields(item) : []
            const hasWeightData = !!(
              item?.netWeight || item?.grossWeight || item?.length || item?.width || item?.height
            )
            return (
              <div key={f.id} className="rounded-lg border border-line bg-canvas-alt/40">
                <div className="flex items-center gap-2 border-b border-line/60 px-3 py-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Item {i + 1}</span>
                  <span className="truncate text-[13px] font-medium">{item?.itemName || 'Not named yet'}</span>
                  <span className="ml-auto" />
                  {pending.length > 0
                    ? <span className="cursor-help rounded border border-[var(--color-warning,#B4531A)]/30 bg-[var(--color-warning-soft,#FBEDE2)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-warning,#B4531A)]" title={`Still to add: ${pending.join(', ')}`}>{pending.length} pending</span>
                    : <span className="rounded border border-[var(--color-success,#1F7A5A)]/30 bg-[var(--color-success-soft,#E4F1EC)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-success,#1F7A5A)]">Complete</span>}
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    disabled={fields.length === 1}
                    className="ml-1 h-6 w-6 rounded border border-line text-muted hover:border-risk hover:text-risk disabled:opacity-35"
                    title="Remove item"
                  >×</button>
                </div>

                <div className="p-3">
                  <p className="mb-2.5 text-[10.5px] font-semibold uppercase tracking-wide text-muted">Item</p>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Field label="Item name" required span error={errors.items?.[i]?.itemName?.message}>
                      <Input list="dl-items" {...register(`items.${i}.itemName`)} placeholder="Search item master…" autoComplete="off" />
                    </Field>
                    <Field label="Placeholder name" hint="Optional nickname" span>
                      <Input {...register(`items.${i}.placeholderName`)} placeholder="e.g. “blue drum”" autoComplete="off" />
                    </Field>
                    <ItemCodeField index={i} error={errors.items?.[i]?.itemCode?.message} />
                    <Field label="H.S. code" hint="Optional now">
                      <Input {...register(`items.${i}.hsCode`)} placeholder="0000.00.00" className="tabular-nums" autoComplete="off" />
                    </Field>
                    <Field label="Specification" span>
                      <Input {...register(`items.${i}.specification`)} placeholder="Optional" autoComplete="off" />
                    </Field>
                    <Field label="Quantity" required error={errors.items?.[i]?.quantity?.message}>
                      <Input type="number" min="0" step="any" {...register(`items.${i}.quantity`)} />
                    </Field>
                    <Field label="Unit of measure" required error={errors.items?.[i]?.uom?.message}>
                      <Select {...register(`items.${i}.uom`)}>
                        <option value="">Select…</option>
                        {UNITS_OF_MEASURE.map((u) => <option key={u}>{u}</option>)}
                      </Select>
                    </Field>
                    <Field label="Batch number">
                      <Input {...register(`items.${i}.batchNo`)} placeholder="Add later" autoComplete="off" />
                    </Field>
                  </div>

                  <div className="mt-4">
                    <Disclosure
                      title={
                        <span className="flex items-center gap-2">
                          <span className="text-[10.5px] font-semibold uppercase tracking-wide text-muted">
                            Weight &amp; dimensions (required before sending to trucking)
                          </span>
                          {hasWeightData && (
                            <span className="rounded border border-brand/30 bg-brand/10 px-1.5 py-0.5 text-[10px] font-medium text-brand">
                              Has data
                            </span>
                          )}
                        </span>
                      }
                    >
                      <div className="grid gap-3 pb-3 sm:grid-cols-2 lg:grid-cols-5">
                        <Field label="Net weight (kg)">
                          <Input type="number" min="0" step="any" {...register(`items.${i}.netWeight`)} placeholder="Optional" />
                        </Field>
                        <Field label="Gross weight (kg)">
                          <Input type="number" min="0" step="any" {...register(`items.${i}.grossWeight`)} placeholder="Optional" />
                        </Field>
                        <Field label="Length (cm)">
                          <Input type="number" min="0" step="any" {...register(`items.${i}.length`)} placeholder="Optional" />
                        </Field>
                        <Field label="Width (cm)">
                          <Input type="number" min="0" step="any" {...register(`items.${i}.width`)} placeholder="Optional" />
                        </Field>
                        <Field label="Height (cm)">
                          <Input type="number" min="0" step="any" {...register(`items.${i}.height`)} placeholder="Optional" />
                        </Field>
                      </div>
                    </Disclosure>
                  </div>

                  <p className="mb-2.5 mt-4 text-[10.5px] font-semibold uppercase tracking-wide text-muted">Requisition</p>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <Field label="Requisition type" required error={errors.items?.[i]?.requisitionType?.message}>
                      <Select {...register(`items.${i}.requisitionType`)}>
                        <option value="">Select…</option>
                        {REQUISITION_TYPES.map((t) => <option key={t} value={t}>{REQ_LABEL[t]}</option>)}
                      </Select>
                    </Field>

                    {reqType && (
                      <div className="rounded-r border-l-[3px] border-brand bg-brand/5 p-3 sm:col-span-2 lg:col-span-4">
                        <div className="mb-2 text-[11px] text-brand/80">{REQ_LEAD[reqType]}</div>
                        <div className="grid gap-3 sm:grid-cols-3">
                          {REQUISITION_FIELDS[reqType].map((fk) => (
                            <Field key={fk} label={FIELD_LABEL[fk]} span={fk === 'othersDescription'}>
                              <Input {...register(`items.${i}.${fk}` as const)} autoComplete="off" />
                            </Field>
                          ))}
                        </div>
                      </div>
                    )}
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

      <datalist id="dl-items">
        <option>Ball bearing 6205-2RS</option>
        <option>Oil seal TC 35x52x7</option>
        <option>PLC S7-1500 CPU</option>
      </datalist>
    </div>
  )
}
