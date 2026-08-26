import { useEffect, useState } from 'react'
import { useFormContext, useFieldArray, useWatch, Controller } from 'react-hook-form'
import {
  type ConsignmentDraft, type ConsignmentItem,
  REQUISITION_TYPES, REQUISITION_FIELDS, CONSIGNMENT_TYPES, UNITS_OF_MEASURE, INCOTERMS,
  emptyItem, itemPendingFields, requiredVsEtaDelay,
} from '../../schema'
import { Field, Input, Select } from './fields'
import { useMasters } from '../MastersContext'
import { Disclosure } from '@/components/Disclosure'
import { SearchableSelect, NotInMasterNote, type SearchableOption } from '@/components/ui/SearchableSelect'
import { searchItems, exactCodeMatch, type ItemSearchResult } from '@/lib/api/masters'
import { toOptions, isKnownMasterValue } from '@/lib/api/useMasterOptions'

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

const FROM_MASTER_HINT = 'From item master — locked'
const LOCKED_INPUT_CLASS = 'bg-canvas-alt text-muted'

/** Module scope so the identity is stable — SearchableSelect restarts its
 *  debounced search whenever `loadOptions` changes. Searches name OR code
 *  (see masters/helpers.py::search_items), so typing either finds the row. */
async function loadItemOptions(query: string): Promise<SearchableOption<ItemSearchResult>[]> {
  const rows = await searchItems(query)
  return rows.map((row) => ({
    value: row.item_code,
    label: row.item_code,
    hint: row.name,
    data: row,
  }))
}

/**
 * One item row's identity, quantity and unit fields.
 *
 * Extracted from the row `.map()` because the three identity fields are now
 * interdependent — the code decides whether the name and specification are
 * editable — and a hook cannot be called inside a loop. The grid order is
 * unchanged from when these were written inline.
 *
 * ITEM CODE IS THE AUTHORITY. Enter a code that matches an ACTIVE master item
 * and the name and specification are filled from that master and locked: one
 * code cannot describe two different things, or item-wise reporting stops
 * agreeing with itself. Locking is a convenience for the person typing — the
 * SERVER re-applies the same values on every write, so a payload that skips
 * the form cannot get past it (see imports/helpers.py::apply_item_master_values).
 *
 * A code that matches NOTHING locks nothing. That covers two real cases and
 * both must keep working: the "Others" requisition type, where item_code is
 * optional entirely (ITEM_CODE_NOT_REQUIRED_FOR on the backend), and legacy
 * lines carrying a generated `IMP-<hash>` code the catalogue never had
 * (loading/imports/item_codes.py). Hence allowFreeText on the code field.
 *
 * SPECIFICATION LOCKS ONLY IF THE MASTER HAS ONE. Forcing an empty value over
 * a specification the operator typed, to agree with a master that does not
 * state one, would destroy information to enforce nothing.
 *
 * MIRRORED ON THE BACKEND: app/imports/helpers.py (submission_errors,
 * ITEM_CODE_NOT_REQUIRED_FOR) makes the code optional for "Others", keyed off
 * the capitalised requisition type. Keep both in sync.
 */
function ItemDetailFields({ index }: { index: number }) {
  const {
    register, control, setValue, getValues, formState: { errors },
  } = useFormContext<ConsignmentDraft>()

  const itemCode = useWatch({ control, name: `items.${index}.itemCode` })
  const requisitionType = useWatch({ control, name: `items.${index}.requisitionType` })
  const codeOptional = requisitionType === 'others'

  const [master, setMaster] = useState<ItemSearchResult | null>(null)

  // No code means no lookup and no lock — the Others / non-master path stays
  // exactly as free-text as it was.
  useEffect(() => {
    const code = (itemCode ?? '').trim()
    if (!code) { setMaster(null); return }

    let cancelled = false
    const timer = setTimeout(() => {
      searchItems(code)
        .then((rows) => { if (!cancelled) setMaster(exactCodeMatch(rows, code)) })
        .catch(() => { if (!cancelled) setMaster(null) })
    }, 250)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [itemCode])

  const lockName = master !== null
  const lockSpec = !!master?.default_specification

  // Write the master's values onto the row. Guarded on a real difference: the
  // lookup re-runs as the code is typed and would otherwise mark the form
  // dirty on every pass, which the stepper's unsaved-changes prompt reads.
  useEffect(() => {
    if (!master) return

    if (getValues(`items.${index}.itemName`) !== (master.name ?? '')) {
      setValue(`items.${index}.itemName`, master.name ?? '', { shouldDirty: true })
    }

    const spec = master.default_specification
    if (spec && getValues(`items.${index}.specification`) !== spec) {
      setValue(`items.${index}.specification`, spec, { shouldDirty: true })
    }
  }, [master, index, setValue, getValues])

  const typedCode = (itemCode ?? '').trim()

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Field
        label="Item name" required span
        error={errors.items?.[index]?.itemName?.message}
        hint={lockName ? FROM_MASTER_HINT : undefined}
      >
        <Input
          list={lockName ? undefined : 'dl-items'}
          {...register(`items.${index}.itemName`)}
          readOnly={lockName}
          className={lockName ? LOCKED_INPUT_CLASS : undefined}
          placeholder="Search item master…"
          autoComplete="off"
        />
      </Field>

      <Field label="Placeholder name" hint="Optional nickname" span>
        <Input {...register(`items.${index}.placeholderName`)} placeholder="e.g. “blue drum”" autoComplete="off" />
      </Field>

      <Field
        label="Item code" required={!codeOptional}
        error={errors.items?.[index]?.itemCode?.message}
        hint={typedCode && !lockName ? 'Not in item master — name stays free text' : undefined}
      >
        <Controller
          control={control}
          name={`items.${index}.itemCode`}
          render={({ field }) => (
            <SearchableSelect<ItemSearchResult>
              value={field.value ?? ''}
              onChange={field.onChange}
              loadOptions={loadItemOptions}
              // The picked row is already the full master record, so the
              // fields fill immediately instead of waiting on the debounce.
              onSelectOption={(option) => { if (option.data) setMaster(option.data) }}
              allowFreeText
              placeholder={codeOptional ? 'Optional for Others' : 'Type a code or name…'}
              emptyMessage="No matching item — the code will be kept as typed"
            />
          )}
        />
      </Field>

      <Field label="H.S. code" hint="Optional now">
        <Input {...register(`items.${index}.hsCode`)} placeholder="0000.00.00" className="tabular-nums" autoComplete="off" />
      </Field>

      <Field
        label="Specification" span
        hint={lockSpec ? FROM_MASTER_HINT : undefined}
      >
        <Input
          {...register(`items.${index}.specification`)}
          readOnly={lockSpec}
          className={lockSpec ? LOCKED_INPUT_CLASS : undefined}
          placeholder="Optional"
          autoComplete="off"
        />
      </Field>

      <Field label="Quantity" required error={errors.items?.[index]?.quantity?.message}>
        <Input type="number" min="0" step="any" {...register(`items.${index}.quantity`)} />
      </Field>

      <Field label="Unit of measure" required error={errors.items?.[index]?.uom?.message}>
        <Select {...register(`items.${index}.uom`)}>
          <option value="">Select…</option>
          {UNITS_OF_MEASURE.map((u) => <option key={u}>{u}</option>)}
        </Select>
      </Field>

      <Field label="Batch number">
        <Input {...register(`items.${index}.batchNo`)} placeholder="Add later" autoComplete="off" />
      </Field>
    </div>
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
  const supplierName = watch('supplier')

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

          {/* Supplier master. FREE TEXT IS STILL ACCEPTED so an in-progress
              draft is never blocked mid-typing — but unlike logistics'
              customer or trucking's transporter, a consignment stores
              supplier_ID ONLY (imports/models.py) with no name column beside
              it. There is physically nowhere to keep an unmatched name, so
              one cannot survive the save; NotInMasterNote says exactly that
              rather than letting the field look accepted and come back empty.
              The old hint here claimed such a name "is kept", which was not
              true of any save. */}
          <Field
            label="Supplier" htmlFor="supplier" required error={errors.supplier?.message}
            hint={mastersLoading ? 'Loading suppliers…' : undefined}
          >
            <Controller
              control={control}
              name="supplier"
              render={({ field }) => (
                <SearchableSelect
                  id="supplier"
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  options={toOptions(suppliers)}
                  allowFreeText
                  disabled={mastersLoading}
                  placeholder="Search suppliers…"
                  emptyMessage="No matching supplier"
                />
              )}
            />
            {!mastersLoading && !isKnownMasterValue(suppliers, supplierName) && (
              <NotInMasterNote master="supplier master" stored="none" />
            )}
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
                  <ItemDetailFields index={i} />

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
