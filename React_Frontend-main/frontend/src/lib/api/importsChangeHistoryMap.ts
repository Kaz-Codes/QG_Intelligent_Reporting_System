import type {
  ApiChangeHistoryEntry, ApiChildChange, ApiFieldChange,
} from './imports'
import type { MasterOption } from './masters'
import type {
  ChangeHistoryEntry, ChildCollectionDiff, ChildDiffRow, ChildSummaryRow,
  FieldDiff, HistorySection,
} from '@/lib/changeHistory'

/**
 * Backend change-history row -> the shape ChangeHistoryCard draws.
 *
 * The backend stores raw column names and raw values: `branch_id: {old: 3,
 * new: 7}`, `exchange_rate: "281.5000"`, `etd: "2026-03-04"`. None of that is
 * readable on its own, so this module does three jobs:
 *
 *  1. NAMES the column ("branch_id" -> "Branch") and files it under the wizard
 *     step a correction would actually be made on, so a card's sections line up
 *     with the form.
 *  2. RESOLVES foreign keys to master names — "Branch changed 3 -> 7" tells a
 *     user nothing.
 *  3. FORMATS values (dates, decimal strings, booleans, nulls).
 *
 * A column with no entry in FIELD_META is DROPPED rather than shown raw: the
 * update route diffs every column it is handed, including server-managed ones
 * (record_state, is_locked, the ELC/ALC audit stamps) that are noise in a
 * user-facing history. Adding a field to the wizard means adding it here too.
 */

type Kind = 'text' | 'date' | 'number' | 'money' | 'master'
type MasterKind = 'branch' | 'supplier' | 'port' | 'agent'

interface FieldMeta {
  section: string
  label: string
  kind: Kind
  /** Which master list resolves this id, for kind: 'master'. */
  master?: MasterKind
}

const SECTION_LABELS: Record<string, string> = {
  consignment: 'Consignment',
  finance: 'Finance',
  shipping: 'Shipping',
  payments: 'Payments',
  'status-remarks': 'Status & Remarks',
  clearance: 'Clearance',
}

/** Section order = wizard step order, so a card reads top-to-bottom the way
 *  the form does. */
const SECTION_ORDER = Object.keys(SECTION_LABELS)

const FIELD_META: Record<string, FieldMeta> = {
  // --- 1. consignment ---
  branch_id: { section: 'consignment', label: 'Branch', kind: 'master', master: 'branch' },
  supplier_id: { section: 'consignment', label: 'Supplier', kind: 'master', master: 'supplier' },
  origin: { section: 'consignment', label: 'Country of origin', kind: 'text' },
  currency: { section: 'consignment', label: 'Currency', kind: 'text' },
  consignment_type: { section: 'consignment', label: 'Consignment type', kind: 'text' },
  incoterm: { section: 'consignment', label: 'Incoterm', kind: 'text' },
  po_date: { section: 'consignment', label: 'PO date', kind: 'date' },
  requisition_date: { section: 'consignment', label: 'Requisition date', kind: 'date' },
  required_date: { section: 'consignment', label: 'Required date', kind: 'date' },

  // --- 2. finance ---
  payment_instrument: { section: 'finance', label: 'Payment instrument', kind: 'text' },
  instrument_number: { section: 'finance', label: 'Instrument number', kind: 'text' },
  opening_or_retirement_date: { section: 'finance', label: 'Opening / retirement date', kind: 'date' },
  works: { section: 'finance', label: 'Works', kind: 'text' },
  exchange_rate: { section: 'finance', label: 'Exchange rate', kind: 'number' },
  rate_booked_on: { section: 'finance', label: 'Rate booked on', kind: 'date' },
  rate_source: { section: 'finance', label: 'Rate source', kind: 'text' },

  // --- 3. shipping ---
  mode_of_shipment: { section: 'shipping', label: 'Mode of shipment', kind: 'text' },
  loading_port_id: { section: 'shipping', label: 'Port of loading', kind: 'master', master: 'port' },
  delivery_port_id: { section: 'shipping', label: 'Port of delivery', kind: 'master', master: 'port' },
  cargo_readiness_date: { section: 'shipping', label: 'Cargo readiness date', kind: 'date' },
  etd: { section: 'shipping', label: 'ETD', kind: 'date' },
  eta: { section: 'shipping', label: 'ETA', kind: 'date' },
  eta_works: { section: 'shipping', label: 'ETA works', kind: 'date' },

  // --- 5. status & remarks ---
  current_status: { section: 'status-remarks', label: 'Status', kind: 'text' },
  effective_date: { section: 'status-remarks', label: 'Status effective date', kind: 'date' },
  remarks: { section: 'status-remarks', label: 'Remarks', kind: 'text' },

  // --- 6. clearance ---
  clearing_agent_id: { section: 'clearance', label: 'Clearing agent', kind: 'master', master: 'agent' },
  gd_number: { section: 'clearance', label: 'GD number', kind: 'text' },
  gd_filing_date: { section: 'clearance', label: 'GD filing date', kind: 'date' },
  free_days_allowed: { section: 'clearance', label: 'Free days allowed', kind: 'number' },
  gate_out_date: { section: 'clearance', label: 'Gate out', kind: 'date' },
  demurrage_or_detention_paid: { section: 'clearance', label: 'Demurrage / detention (PKR)', kind: 'money' },
  container_detention: { section: 'clearance', label: 'Container detention (PKR)', kind: 'money' },
}

/** Item-line columns. Same drop-if-unmapped rule as the header. */
const ITEM_META: Record<string, { label: string; kind: Kind }> = {
  item_name: { label: 'Item name', kind: 'text' },
  item_code: { label: 'Item code', kind: 'text' },
  specification: { label: 'Specification', kind: 'text' },
  hs_code: { label: 'H.S. code', kind: 'text' },
  quantity: { label: 'Quantity', kind: 'number' },
  unit_of_measurement: { label: 'Unit of measure', kind: 'text' },
  unit_price: { label: 'Unit price', kind: 'money' },
  batch_no: { label: 'Batch no', kind: 'text' },
  requisition_type: { label: 'Requisition type', kind: 'text' },
  reference_number: { label: 'Reference no', kind: 'text' },
  job_number: { label: 'Job no', kind: 'text' },
  mo_number: { label: 'MO no', kind: 'text' },
  description: { label: 'Description', kind: 'text' },
  net_weight: { label: 'Net weight', kind: 'number' },
  gross_weight: { label: 'Gross weight', kind: 'number' },
  length: { label: 'Length', kind: 'number' },
  width: { label: 'Width', kind: 'number' },
  height: { label: 'Height', kind: 'number' },
  elc: { label: 'ELC', kind: 'money' },
  alc: { label: 'ALC', kind: 'money' },
}

const PAYMENT_META: Record<string, { label: string; kind: Kind }> = {
  retirement_date: { label: 'Date', kind: 'date' },
  value: { label: 'Value', kind: 'money' },
  payment_exchange_rate: { label: 'Exchange rate', kind: 'number' },
  bank_charges: { label: 'Bank charges', kind: 'money' },
  status: { label: 'Status', kind: 'text' },
  bank_reference: { label: 'Reference', kind: 'text' },
}

/** The master lists the FK fields resolve against, plus per-row labels for
 *  child collections (the diff itself carries only an id). */
export interface HistoryLookups {
  branches: MasterOption[]
  suppliers: MasterOption[]
  ports: MasterOption[]
  agents: MasterOption[]
  /** Consignment item id -> a human label ("Ball bearing 6205"), from the
   *  record's CURRENT lines. A line deleted long ago won't be here; the id
   *  is then shown instead, which is still better than nothing. */
  itemLabels: Map<number, string>
  paymentLabels: Map<number, string>
}

export const EMPTY_LOOKUPS: HistoryLookups = {
  branches: [], suppliers: [], ports: [], agents: [],
  itemLabels: new Map(), paymentLabels: new Map(),
}

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric' })

function formatDate(value: unknown): string {
  if (value == null || value === '') return ''
  // Dates arrive as 'YYYY-MM-DD'; parse as UTC so a local timezone behind
  // Greenwich can't shift the day backwards.
  const iso = String(value).slice(0, 10)
  const d = new Date(`${iso}T00:00:00Z`)
  return Number.isNaN(+d) ? String(value) : DATE_FMT.format(d)
}

/** Decimals cross the wire as STRINGS (the engine's json_serializer uses
 *  default=str), so trailing zeros come along too — "281.500000" reads as
 *  noise next to "281.5". */
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

function masterName(options: MasterOption[], id: unknown): string {
  if (id == null || id === '') return ''
  const found = options.find((o) => o.id === Number(id))
  // An id with no match (the master was deactivated, or the lists failed to
  // load) still says something honest rather than rendering blank.
  return found ? found.name : `#${id}`
}

function formatValue(value: unknown, kind: Kind, master: MasterKind | undefined, lookups: HistoryLookups): string {
  if (value == null || value === '') return ''
  switch (kind) {
    case 'date': return formatDate(value)
    case 'number': return formatNumber(value)
    case 'money': return formatMoney(value)
    case 'master':
      switch (master) {
        case 'branch': return masterName(lookups.branches, value)
        case 'supplier': return masterName(lookups.suppliers, value)
        case 'port': return masterName(lookups.ports, value)
        case 'agent': return masterName(lookups.agents, value)
        default: return String(value)
      }
    default:
      return typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)
  }
}

/** A {old_value,new_value} object — as opposed to the bare numeric `id` the
 *  backend also parks in a child-change dict (see helpers.apply_updates). */
function isFieldChange(value: unknown): value is ApiFieldChange {
  return !!value && typeof value === 'object' && 'new_value' in (value as object)
}

/** Header columns -> the card's sections, in wizard order, unmapped columns
 *  dropped. */
function buildSections(
  fields: Record<string, ApiFieldChange> | undefined,
  lookups: HistoryLookups,
): HistorySection[] {
  const bySection = new Map<string, FieldDiff[]>()

  for (const [column, change] of Object.entries(fields ?? {})) {
    const meta = FIELD_META[column]
    if (!meta || !isFieldChange(change)) continue

    const diffs = bySection.get(meta.section) ?? []
    diffs.push({
      field: column,
      label: meta.label,
      oldValue: formatValue(change.old_value, meta.kind, meta.master, lookups),
      newValue: formatValue(change.new_value, meta.kind, meta.master, lookups),
    })
    bySection.set(meta.section, diffs)
  }

  return SECTION_ORDER
    .filter((key) => bySection.has(key))
    .map((key) => ({ key, label: SECTION_LABELS[key], fields: bySection.get(key)! }))
}

/** One changed child row -> its field-by-field diff. */
function buildChildDiffs(
  rows: ApiChildChange[] | undefined,
  meta: Record<string, { label: string; kind: Kind }>,
  noun: string,
  labels: Map<number, string>,
  lookups: HistoryLookups,
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
        oldValue: formatValue(change.old_value, fieldMeta.kind, undefined, lookups),
        newValue: formatValue(change.new_value, fieldMeta.kind, undefined, lookups),
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

/** An added/removed child row -> a one-line summary. Unlike an update, the
 *  backend hands over the WHOLE serialized row here, so the summary can name
 *  it properly. */
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
  const name = row.item_name ? String(row.item_name) : ''
  const code = row.item_code ? String(row.item_code) : ''
  const qty = row.quantity != null ? formatNumber(row.quantity) : ''
  const uom = row.unit_of_measurement ? String(row.unit_of_measurement) : ''
  const head = [name, code && `(${code})`].filter(Boolean).join(' ')
  const tail = qty ? `${qty}${uom ? ` ${uom}` : ''}` : ''
  return [head, tail].filter(Boolean).join(' · ')
}

function paymentSummary(row: Record<string, unknown>): string {
  const value = row.value != null ? formatMoney(row.value) : ''
  const status = row.status ? String(row.status) : ''
  const ref = row.bank_reference ? String(row.bank_reference) : ''
  return [value, status, ref].filter(Boolean).join(' · ')
}

function buildCollections(
  history: ApiChangeHistoryEntry['history'],
  lookups: HistoryLookups,
): ChildCollectionDiff[] {
  const collections: ChildCollectionDiff[] = [
    {
      key: 'items',
      label: 'Items',
      updated: buildChildDiffs(history.items, ITEM_META, 'Item', lookups.itemLabels, lookups),
      added: buildChildSummaries(history.new_items, 'Item', itemSummary, 'item-add'),
      removed: buildChildSummaries(history.deleted_items, 'Item', itemSummary, 'item-rm'),
    },
    {
      key: 'payments',
      label: 'Payments',
      updated: buildChildDiffs(history.payments, PAYMENT_META, 'Payment', lookups.paymentLabels, lookups),
      added: buildChildSummaries(history.new_payments, 'Payment', paymentSummary, 'payment-add'),
      removed: buildChildSummaries(history.deleted_payments, 'Payment', paymentSummary, 'payment-rm'),
    },
  ]

  // A collection nothing happened to is not worth a heading.
  return collections.filter((c) => c.updated.length || c.added.length || c.removed.length)
}

export function apiToChangeHistoryEntry(
  entry: ApiChangeHistoryEntry,
  lookups: HistoryLookups = EMPTY_LOOKUPS,
): ChangeHistoryEntry {
  return {
    id: String(entry.id),
    recordId: String(entry.consignment_id),
    // The backend only ever writes "update" today; anything else is passed
    // through as a Delete rather than silently mislabelled as an edit.
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
    sections: buildSections(entry.history?.fields, lookups),
    collections: buildCollections(entry.history ?? {}, lookups),
  }
}
