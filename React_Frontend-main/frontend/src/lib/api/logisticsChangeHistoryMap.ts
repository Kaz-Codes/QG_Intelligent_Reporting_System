import type {
  ApiLogisticsHistoryEntry, ApiChildChange, ApiFieldChange,
} from './logistics'
import type {
  ChangeHistoryEntry, ChildCollectionDiff, ChildDiffRow, ChildSummaryRow,
  FieldDiff, HistorySection,
} from '@/lib/changeHistory'

/**
 * Backend logistics change-history row -> the shape ChangeHistoryCard draws.
 *
 * Same three jobs as the imports mapper (lib/api/importsChangeHistoryMap.ts):
 * NAME each raw column and file it under the wizard step a correction would be
 * made on, FORMAT the values (dates, decimal strings, money, booleans), and
 * DROP anything unmapped.
 *
 * Dropping matters here too: the update route diffs every column it is handed,
 * including server-managed ones (record_state, is_locked, effective_date) that
 * are noise in a user-facing history. Adding a field to the wizard means adding
 * it here as well.
 *
 * Unlike imports there are no foreign keys to resolve — logistics stores
 * customer, works, ports and clearing agent as free text — so this needs no
 * master lookups.
 */

type Kind = 'text' | 'date' | 'number' | 'money' | 'bool'

interface FieldMeta {
  section: string
  label: string
  kind: Kind
}

const SECTION_LABELS: Record<string, string> = {
  order: 'Order',
  packing: 'Packing',
  shipping: 'Shipping',
  expenditures: 'Expenditures',
  status: 'Status & Remarks',
}

/** Section order = wizard step order, so a card reads the way the form does. */
const SECTION_ORDER = Object.keys(SECTION_LABELS)

const FIELD_META: Record<string, FieldMeta> = {
  // --- 1. order ---
  order_type: { section: 'order', label: 'Order type', kind: 'text' },
  department: { section: 'order', label: 'Department', kind: 'text' },
  shipment_mode: { section: 'order', label: 'Shipment mode', kind: 'text' },
  origin_country: { section: 'order', label: 'Country of origin', kind: 'text' },
  origin_city: { section: 'order', label: 'City', kind: 'text' },
  origin_province: { section: 'order', label: 'Province', kind: 'text' },
  customer_name: { section: 'order', label: 'Customer', kind: 'text' },
  mo_no: { section: 'order', label: 'MO no.', kind: 'text' },
  batch_no: { section: 'order', label: 'Batch no.', kind: 'number' },
  batch_label: { section: 'order', label: 'Batch label', kind: 'text' },
  incoterm: { section: 'order', label: 'Incoterm', kind: 'text' },

  // --- 3. shipping ---
  pol: { section: 'shipping', label: 'Port of loading', kind: 'text' },
  pod: { section: 'shipping', label: 'Port of discharge', kind: 'text' },
  shipping_line: { section: 'shipping', label: 'Shipping line', kind: 'text' },
  clearing_agent: { section: 'shipping', label: 'Clearing agent', kind: 'text' },
  booking_no: { section: 'shipping', label: 'Booking no.', kind: 'text' },
  port_in_date: { section: 'shipping', label: 'Port-in date', kind: 'date' },
  etd_sailing_date: { section: 'shipping', label: 'ETD / sailing date', kind: 'date' },
  cro_arrival_date: { section: 'shipping', label: 'CRO arrival date', kind: 'date' },
  actual_arrival_date: { section: 'shipping', label: 'Actual arrival date', kind: 'date' },

  // --- 4. expenditures ---
  packing_cost: { section: 'expenditures', label: 'Packing cost', kind: 'money' },
  transportation_charges: { section: 'expenditures', label: 'Transportation charges', kind: 'money' },
  container_detention: { section: 'expenditures', label: 'Container detention', kind: 'money' },
  insurance: { section: 'expenditures', label: 'Insurance', kind: 'money' },
  trucking_lhr_to_khi: { section: 'expenditures', label: 'Trucking LHR→KHI', kind: 'money' },
  fumigation_cost: { section: 'expenditures', label: 'Fumigation cost', kind: 'money' },
  lashing: { section: 'expenditures', label: 'Lashing', kind: 'money' },
  qfl_charges: { section: 'expenditures', label: 'QFL charges', kind: 'money' },
  qfl_container_movement: { section: 'expenditures', label: 'QFL container movement', kind: 'money' },
  custom_clearance_charges: { section: 'expenditures', label: 'Custom clearance charges', kind: 'money' },
  port_charges: { section: 'expenditures', label: 'Port charges', kind: 'money' },
  dhl_charges: { section: 'expenditures', label: 'DHL charges', kind: 'money' },
  sea_air_freight: { section: 'expenditures', label: 'Sea / air freight', kind: 'money' },

  // --- 5. status ---
  current_status: { section: 'status', label: 'Status', kind: 'text' },
  gate_out_date: { section: 'status', label: 'Gate out', kind: 'date' },
  sent_to_trucking: { section: 'status', label: 'Sent to trucking', kind: 'bool' },
}

const ITEM_META: Record<string, { label: string; kind: Kind }> = {
  job_no: { label: 'Job no.', kind: 'text' },
  item_detail: { label: 'Item detail', kind: 'text' },
  quantity: { label: 'Quantity', kind: 'number' },
  unit_weight: { label: 'Unit weight', kind: 'number' },
  gross_weight: { label: 'Gross weight', kind: 'number' },
  planned_rfd_date: { label: 'Planned RFD', kind: 'date' },
  actual_rfd_date: { label: 'Actual RFD', kind: 'date' },
}

const PACKAGE_META: Record<string, { label: string; kind: Kind }> = {
  colour_code: { label: 'Colour code', kind: 'text' },
  packing_works: { label: 'Packing works', kind: 'text' },
  packing_ready_date: { label: 'Packing ready date', kind: 'date' },
  packing_date: { label: 'Packing date', kind: 'date' },
  quoted_packing_cost: { label: 'Quoted packing cost', kind: 'money' },
  actual_packing_cost: { label: 'Actual packing cost', kind: 'money' },
  gross_weight: { label: 'Gross weight', kind: 'number' },
  status: { label: 'Packing status', kind: 'text' },
}

const CONTAINER_META: Record<string, { label: string; kind: Kind }> = {
  container_no: { label: 'Container no.', kind: 'text' },
  container_type: { label: 'Container type', kind: 'text' },
}

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric' })

function formatDate(value: unknown): string {
  if (value == null || value === '') return ''
  // Dates arrive as 'YYYY-MM-DD'; parse as UTC so a timezone behind Greenwich
  // can't shift the day backwards.
  const iso = String(value).slice(0, 10)
  const d = new Date(`${iso}T00:00:00Z`)
  return Number.isNaN(+d) ? String(value) : DATE_FMT.format(d)
}

/** Decimals cross the wire as STRINGS (json_serializer uses default=str), so
 *  trailing zeros come with them — "1200.000" reads as noise next to "1200". */
function formatNumber(value: unknown): string {
  if (value == null || value === '') return ''
  const n = Number(value)
  return Number.isFinite(n) ? String(n) : String(value)
}

const MONEY_FMT = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

function formatMoney(value: unknown): string {
  if (value == null || value === '') return ''
  const n = Number(value)
  return Number.isFinite(n) ? MONEY_FMT.format(n) : String(value)
}

function formatValue(value: unknown, kind: Kind): string {
  if (value == null || value === '') return ''
  switch (kind) {
    case 'date': return formatDate(value)
    case 'number': return formatNumber(value)
    case 'money': return formatMoney(value)
    case 'bool': return value ? 'Yes' : 'No'
    default: return typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)
  }
}

/** A {old_value,new_value} object — as opposed to the bare numeric `id` the
 *  backend also parks in a child-change dict (see helpers.apply_updates). */
function isFieldChange(value: unknown): value is ApiFieldChange {
  return !!value && typeof value === 'object' && 'new_value' in (value as object)
}

function buildSections(fields: Record<string, ApiFieldChange> | undefined): HistorySection[] {
  const bySection = new Map<string, FieldDiff[]>()

  for (const [column, change] of Object.entries(fields ?? {})) {
    const meta = FIELD_META[column]
    if (!meta || !isFieldChange(change)) continue

    const diffs = bySection.get(meta.section) ?? []
    diffs.push({
      field: column,
      label: meta.label,
      oldValue: formatValue(change.old_value, meta.kind),
      newValue: formatValue(change.new_value, meta.kind),
    })
    bySection.set(meta.section, diffs)
  }

  return SECTION_ORDER
    .filter((key) => bySection.has(key))
    .map((key) => ({ key, label: SECTION_LABELS[key], fields: bySection.get(key)! }))
}

function buildChildDiffs(
  rows: ApiChildChange[] | undefined,
  meta: Record<string, { label: string; kind: Kind }>,
  noun: string,
  labels: Map<number, string>,
): ChildDiffRow[] {
  const out: ChildDiffRow[] = []

  for (const row of rows ?? []) {
    const changes: FieldDiff[] = []

    for (const [column, change] of Object.entries(row)) {
      const fieldMeta = meta[column]
      if (!fieldMeta || !isFieldChange(change)) continue
      changes.push({
        field: column,
        label: fieldMeta.label,
        oldValue: formatValue(change.old_value, fieldMeta.kind),
        newValue: formatValue(change.new_value, fieldMeta.kind),
      })
    }

    if (!changes.length) continue

    const id = typeof row.id === 'number' ? row.id : undefined
    out.push({
      id: `${noun}-${id ?? out.length}`,
      label: (id != null && labels.get(id)) || `${noun} #${id ?? '?'}`,
      changes,
    })
  }

  return out
}

function buildChildSummaries(
  rows: Record<string, unknown>[] | undefined,
  noun: string,
  summarise: (row: Record<string, unknown>) => string,
  prefix: string,
): ChildSummaryRow[] {
  return (rows ?? []).map((row, i) => ({
    id: `${prefix}-${row.id ?? i}`,
    label: `${noun} ${row.id != null ? `#${row.id}` : i + 1}`,
    summary: summarise(row) || '(no details recorded)',
  }))
}

function itemSummary(row: Record<string, unknown>): string {
  const detail = row.item_detail ? String(row.item_detail) : ''
  const job = row.job_no ? `job ${row.job_no}` : ''
  const qty = row.quantity != null ? `×${formatNumber(row.quantity)}` : ''
  return [detail, qty, job].filter(Boolean).join(' · ')
}

function packageSummary(row: Record<string, unknown>): string {
  const works = row.packing_works ? String(row.packing_works) : ''
  const colour = row.colour_code ? String(row.colour_code) : ''
  const status = row.status ? String(row.status) : ''
  return [works, colour, status].filter(Boolean).join(' · ')
}

function containerSummary(row: Record<string, unknown>): string {
  const no = row.container_no ? String(row.container_no) : ''
  const type = row.container_type ? String(row.container_type) : ''
  return [no, type].filter(Boolean).join(' · ')
}

/** Per-row labels so a child diff can say "FINAL BLADE" rather than "Item #778". */
export interface LogisticsHistoryLookups {
  itemLabels: Map<number, string>
  packageLabels: Map<number, string>
  containerLabels: Map<number, string>
}

export const EMPTY_LOOKUPS: LogisticsHistoryLookups = {
  itemLabels: new Map(), packageLabels: new Map(), containerLabels: new Map(),
}

function buildCollections(
  history: ApiLogisticsHistoryEntry['history'],
  lookups: LogisticsHistoryLookups,
): ChildCollectionDiff[] {
  const collections: ChildCollectionDiff[] = [
    {
      key: 'items',
      label: 'Items',
      updated: buildChildDiffs(history.items, ITEM_META, 'Item', lookups.itemLabels),
      added: buildChildSummaries(history.new_items, 'Item', itemSummary, 'item-add'),
      removed: buildChildSummaries(history.deleted_items, 'Item', itemSummary, 'item-rm'),
    },
    {
      key: 'packages',
      label: 'Packages',
      updated: buildChildDiffs(history.packages, PACKAGE_META, 'Package', lookups.packageLabels),
      added: buildChildSummaries(history.new_packages, 'Package', packageSummary, 'pkg-add'),
      removed: buildChildSummaries(history.deleted_packages, 'Package', packageSummary, 'pkg-rm'),
    },
    {
      key: 'containers',
      label: 'Containers',
      updated: buildChildDiffs(history.containers, CONTAINER_META, 'Container', lookups.containerLabels),
      added: buildChildSummaries(history.new_containers, 'Container', containerSummary, 'cnt-add'),
      removed: buildChildSummaries(history.deleted_containers, 'Container', containerSummary, 'cnt-rm'),
    },
  ]

  // A collection nothing happened to is not worth a heading.
  return collections.filter((c) => c.updated.length || c.added.length || c.removed.length)
}

export function apiToChangeHistoryEntry(
  entry: ApiLogisticsHistoryEntry,
  lookups: LogisticsHistoryLookups = EMPTY_LOOKUPS,
): ChangeHistoryEntry {
  return {
    id: String(entry.id),
    recordId: String(entry.consignment_id),
    changeType: entry.change_type === 'update' ? 'Update' : 'Delete',
    changedBy: entry.changed_by ?? 'Unknown user',
    // The card's canRevert check compares this against the signed-in user's
    // id, so it must be the numeric user id — NOT the display name.
    changedById: entry.changed_by_id != null ? String(entry.changed_by_id) : '',
    changedAt: entry.changed_at ?? '',
    isReverted: entry.is_reverted,
    revertedBy: entry.reverted_by ?? undefined,
    revertedAt: entry.reverted_at ?? undefined,
    isRevert: entry.is_revert,
    sections: buildSections(entry.history?.fields),
    collections: buildCollections(entry.history ?? {}, lookups),
  }
}
