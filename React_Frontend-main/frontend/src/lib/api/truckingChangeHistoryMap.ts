import type {
  ApiTruckingHistoryEntry, ApiChildChange, ApiFieldChange,
} from './trucking'
import type {
  ChangeHistoryEntry, ChildCollectionDiff, ChildDiffRow, ChildSummaryRow,
  FieldDiff, HistorySection,
} from '@/lib/changeHistory'

/**
 * Backend trucking change-history row -> the shape ChangeHistoryCard draws.
 *
 * Same three jobs as the imports and logistics mappers: NAME each raw column
 * and file it under the wizard step a correction would be made on, FORMAT the
 * values, and DROP anything unmapped — the update route diffs every column it
 * is handed, including server-managed ones (record_state, is_locked, taken_at)
 * that are noise in a user-facing history.
 *
 * Trucking has ONE child collection (vehicles), against imports' two and
 * logistics' three.
 */

type Kind = 'text' | 'date' | 'number' | 'money'

interface FieldMeta {
  section: string
  label: string
  kind: Kind
}

const SECTION_LABELS: Record<string, string> = {
  movement: 'Movement',
  freight: 'Freight & Payment',
  tracking: 'Tracking',
}

/** Section order = wizard step order, so a card reads the way the form does. */
const SECTION_ORDER = Object.keys(SECTION_LABELS)

const FIELD_META: Record<string, FieldMeta> = {
  // --- 1. movement ---
  movement_type: { section: 'movement', label: 'Movement type', kind: 'text' },
  shifting_type: { section: 'movement', label: 'Shifting type', kind: 'text' },
  execution_date: { section: 'movement', label: 'Execution date', kind: 'date' },
  transporter_name: { section: 'movement', label: 'Transporter', kind: 'text' },
  item_details: { section: 'movement', label: 'Item details', kind: 'text' },
  pickup: { section: 'movement', label: 'Pickup', kind: 'text' },
  destination: { section: 'movement', label: 'Destination', kind: 'text' },
  reference_no: { section: 'movement', label: 'Shipment reference / IDM', kind: 'text' },

  // --- 3. freight ---
  quoted_freight: { section: 'freight', label: 'Quoted freight', kind: 'money' },
  actual_freight: { section: 'freight', label: 'Actual freight', kind: 'money' },
  payment_status: { section: 'freight', label: 'Payment status', kind: 'text' },
  paid_amount: { section: 'freight', label: 'Paid amount', kind: 'money' },
  detention: { section: 'freight', label: 'Detention', kind: 'money' },

  // --- 4. tracking ---
  dispatch_note_date: { section: 'tracking', label: 'Dispatch note date', kind: 'date' },
  eta_works: { section: 'tracking', label: 'ETA to works', kind: 'date' },
  remarks: { section: 'tracking', label: 'Remarks', kind: 'text' },
}

const VEHICLE_META: Record<string, { label: string; kind: Kind }> = {
  vehicle_number: { label: 'Vehicle no.', kind: 'text' },
  vehicle_type: { label: 'Vehicle type', kind: 'text' },
  no_of_packages: { label: 'No. of packages', kind: 'number' },
  driver_phone: { label: 'Driver phone', kind: 'text' },
  net_weight: { label: 'Net weight', kind: 'number' },
  gross_weight: { label: 'Gross weight', kind: 'number' },
  container_no: { label: 'Container no.', kind: 'text' },
  container_type: { label: 'Container type', kind: 'text' },
  tracking_status: { label: 'Tracking status', kind: 'text' },
}

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: 'numeric' })

function formatDate(value: unknown): string {
  if (value == null || value === '') return ''
  // Parse as UTC so a timezone behind Greenwich can't shift the day back.
  const iso = String(value).slice(0, 10)
  const d = new Date(`${iso}T00:00:00Z`)
  return Number.isNaN(+d) ? String(value) : DATE_FMT.format(d)
}

/** Decimals cross the wire as STRINGS (json_serializer uses default=str). */
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

function buildVehicleDiffs(
  rows: ApiChildChange[] | undefined,
  labels: Map<number, string>,
): ChildDiffRow[] {
  const out: ChildDiffRow[] = []

  for (const row of rows ?? []) {
    const changes: FieldDiff[] = []

    for (const [column, change] of Object.entries(row)) {
      const meta = VEHICLE_META[column]
      if (!meta || !isFieldChange(change)) continue
      changes.push({
        field: column,
        label: meta.label,
        oldValue: formatValue(change.old_value, meta.kind),
        newValue: formatValue(change.new_value, meta.kind),
      })
    }

    if (!changes.length) continue

    const id = typeof row.id === 'number' ? row.id : undefined
    out.push({
      id: `vehicle-${id ?? out.length}`,
      label: (id != null && labels.get(id)) || `Vehicle #${id ?? '?'}`,
      changes,
    })
  }

  return out
}

function vehicleSummary(row: Record<string, unknown>): string {
  const no = row.vehicle_number ? String(row.vehicle_number) : ''
  const type = row.vehicle_type ? String(row.vehicle_type) : ''
  const status = row.tracking_status ? String(row.tracking_status) : ''
  return [no, type, status].filter(Boolean).join(' · ')
}

function buildSummaries(
  rows: Record<string, unknown>[] | undefined,
  prefix: string,
): ChildSummaryRow[] {
  return (rows ?? []).map((row, i) => ({
    id: `${prefix}-${row.id ?? i}`,
    label: `Vehicle ${row.id != null ? `#${row.id}` : i + 1}`,
    summary: vehicleSummary(row) || '(no details recorded)',
  }))
}

/** Per-row labels so a vehicle diff can say "LEA-1234" rather than "#77". */
export interface TruckingHistoryLookups {
  vehicleLabels: Map<number, string>
}

export const EMPTY_LOOKUPS: TruckingHistoryLookups = { vehicleLabels: new Map() }

function buildCollections(
  history: ApiTruckingHistoryEntry['history'],
  lookups: TruckingHistoryLookups,
): ChildCollectionDiff[] {
  const collection: ChildCollectionDiff = {
    key: 'vehicles',
    label: 'Vehicles',
    updated: buildVehicleDiffs(history.vehicles, lookups.vehicleLabels),
    added: buildSummaries(history.new_vehicles, 'vehicle-add'),
    removed: buildSummaries(history.deleted_vehicles, 'vehicle-rm'),
  }

  // A collection nothing happened to is not worth a heading.
  return (collection.updated.length || collection.added.length || collection.removed.length)
    ? [collection]
    : []
}

export function apiToChangeHistoryEntry(
  entry: ApiTruckingHistoryEntry,
  lookups: TruckingHistoryLookups = EMPTY_LOOKUPS,
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
