import type {
  ApiLogisticsOrder, ApiLogisticsItem, ApiLogisticsPackage, ApiLogisticsContainer,
  LogisticsPayload, LogisticsItemPayload, LogisticsPackagePayload, LogisticsContainerPayload,
} from './logistics'
import type { LogisticsDraft } from '@/features/logisticsStatus/schema'
import type {
  Department, OrderType, PackingStatus, PackageAllocation, RfdChangeEvent, RemarkEntry,
  JobKind,
} from '@/features/logisticsStatus/schema'

/**
 * Backend logistics order -> the shape the list AND detail screens draw.
 *
 * Field names stay camelCase and match the wizard's zod types on purpose: the
 * derived-value helpers in features/logisticsStatus/schema.ts (totalNetWeight,
 * arrivalDelayDays, jobNumbers, latestPlannedRfd, …) take structural types, so
 * a row shaped like this works with them unchanged. That keeps the list screen
 * a wiring change rather than a rewrite.
 *
 * Two things this deliberately does NOT do:
 *
 *  - It does not fabricate `shipmentMode`. The column now exists server-side,
 *    but it is NULL on every loaded order (the workbooks have no such field),
 *    so it maps through as null and the UI shows "—". Defaulting to "Regular"
 *    would make an unrecorded value look recorded.
 *  - It does not RESOLVE package `allocations` (cross-batch item references)
 *    or item `rfd_history`. Both are carried through as stored, because the
 *    schema helpers type them as required and the wizard will need them — but
 *    turning an allocation's `sourceOrderId` into a real sibling order is a
 *    wizard concern, not the list's.
 */

export interface LogisticsListItem {
  id: string
  backendId: number
  jobNo: string
  itemDetail: string
  quantity?: number
  unitWeight?: number
  grossWeight?: number
  plannedRfdDate?: string
  actualRfdDate?: string
  /** Stored whole as JSON in the FE's own shape (see CLAUDE.md) — passed
   *  through untouched. Empty for rows that came from the Excel loader. */
  rfdHistory: RfdChangeEvent[]
}

export interface LogisticsListPackage {
  id: string
  backendId: number
  colourCode?: string
  packingWorks?: string
  packingReadyDate?: string
  packingDate?: string
  quotedPackingCost?: number
  actualPackingCost?: number
  grossWeight?: number
  status: PackingStatus
  /** As above — cross-batch allocations, stored whole as JSON. */
  allocations: PackageAllocation[]
}

export interface LogisticsListContainer {
  id: string
  backendId: number
  containerNo?: string
  containerType: string
}

export interface LogisticsListRow {
  /** Real database id — what every route navigates on. */
  id: number
  /** Display id. The backend has no system-id column, so the MO number is the
   *  identifier users actually recognise. Rows without one (707 of the loaded
   *  1,424) show a dash rather than a synthesised LOG-{id}, which would look
   *  like a real reference nobody could search for. Navigation always uses
   *  `id`, never this. */
  systemId: string
  orderType: OrderType
  department: Department
  /** 'standard' (an export/local order) or 'rework' (a customer-rework
   *  service job). Immutable after creation. */
  jobKind: JobKind
  /** Front-end-only today — see the note above. */
  shipmentMode: string | null
  customerName: string
  moNo: string
  batchNo: number
  batchLabel?: string
  incoterm: string
  /** Server-reported submission gaps — drives the Submit button's tooltip. */
  missingFields: string[]
  createdBy?: string
  createdById?: number
  createdAt?: string
  originCountry?: string
  originCity?: string
  originProvince?: string
  // --- shipping (step 3) ---
  pol?: string
  pod?: string
  shippingLine?: string
  clearingAgent?: string
  bookingNo?: string
  portInDate?: string
  etdSailingDate?: string
  croArrivalDate?: string
  actualArrivalDate?: string

  // --- expenditures (step 4). Names match the wizard's zod field names so the
  //     detail page's EXPORT_COSTS / LOCAL_COSTS lookup tables keep working. ---
  packingCost?: number
  transportationCharges?: number
  containerDetention?: number
  insurance?: number
  truckingLhrToKhi?: number
  fumigationCost?: number
  lashing?: number
  qflCharges?: number
  qflContainerMovement?: number
  customClearanceCharges?: number
  portCharges?: number
  dhlCharges?: number
  seaAirFreight?: number

  // --- status (step 5) ---
  gateOutDate?: string
  effectiveDate?: string
  status: string
  sentToTrucking: boolean
  /** Header remarks feed, stored whole as JSON. */
  remarksLog: RemarkEntry[]
  /** 'draft' | 'submitted' — drives the Submitted column. */
  recordState: string
  /** Closed lock: set once the order reaches "Delivered". Drives the Closed
   *  column. Unlike imports, a closed order is NOT hidden from the list. */
  isLocked: boolean
  items: LogisticsListItem[]
  packages: LogisticsListPackage[]
  containers: LogisticsListContainer[]
  /** Soft-deleted. Only ever present for an admin, who is the only
   *  one the list fetches deleted rows for. */
  isDeleted: boolean
}

/** Numerics cross the wire as STRINGS (the engine's json_serializer uses
 *  default=str), so "1200.000" has to become 1200 before any arithmetic. */
function num(v: string | number | null | undefined): number | undefined {
  if (v === null || v === undefined || v === '') return undefined
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : undefined
}

/** '' and null collapse to undefined so `??` fallbacks behave. */
function str(v: string | null | undefined): string | undefined {
  const t = v?.trim()
  return t ? t : undefined
}

/** A JSON column that should hold an array. Loaded (Excel) rows have null
 *  here, and a malformed value should degrade to empty rather than throw
 *  inside a table render. */
function jsonArray<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : []
}

function itemToRow(it: ApiLogisticsItem): LogisticsListItem {
  return {
    id: `item-${it.id}`,
    backendId: it.id,
    jobNo: it.job_no ?? '',
    itemDetail: it.item_detail ?? '',
    quantity: num(it.quantity),
    unitWeight: num(it.unit_weight),
    grossWeight: num(it.gross_weight),
    plannedRfdDate: str(it.planned_rfd_date),
    actualRfdDate: str(it.actual_rfd_date),
    rfdHistory: jsonArray<RfdChangeEvent>(it.rfd_history),
  }
}

function packageToRow(p: ApiLogisticsPackage): LogisticsListPackage {
  return {
    id: `pkg-${p.id}`,
    backendId: p.id,
    colourCode: str(p.colour_code),
    packingWorks: str(p.packing_works),
    packingReadyDate: str(p.packing_ready_date),
    packingDate: str(p.packing_date),
    quotedPackingCost: num(p.quoted_packing_cost),
    actualPackingCost: num(p.actual_packing_cost),
    grossWeight: num(p.gross_weight),
    // The loader normalises onto PackingStatus and defaults anything unmapped,
    // so this is safe to take at face value; the cast is only because the
    // column is a plain String server-side.
    status: (p.status ?? 'Packing under manufacturing') as PackingStatus,
    allocations: jsonArray<PackageAllocation>(p.allocations),
  }
}

function containerToRow(c: ApiLogisticsContainer): LogisticsListContainer {
  return {
    id: `container-${c.id}`,
    backendId: c.id,
    containerNo: str(c.container_no),
    containerType: c.container_type ?? '',
  }
}

export function apiToRow(o: ApiLogisticsOrder): LogisticsListRow {
  // Soft-deleted children are still serialized; the list should never count
  // or weigh them.
  const items = (o.items ?? []).filter((it) => !it.is_deleted).map(itemToRow)
  const packages = (o.packages ?? []).filter((p) => !p.is_deleted).map(packageToRow)
  const containers = (o.containers ?? []).filter((c) => !c.is_deleted).map(containerToRow)

  return {
    id: o.id,
    systemId: str(o.mo_no) ?? '—',
    // Cast rather than gate: the loader normalises both of these onto the
    // canonical enums, and the filter-options endpoint reports anything that
    // slipped through so it stays filterable.
    orderType: (o.order_type ?? 'Export') as OrderType,
    department: (o.department ?? 'General') as Department,
    jobKind: (o.job_kind ?? 'standard') as JobKind,
    shipmentMode: str(o.shipment_mode) ?? null,
    customerName: o.customer_name ?? '',
    missingFields: o.missing_fields ?? [],
    createdBy: str(o.created_by),
    createdById: o.created_by_id ?? undefined,
    createdAt: str(o.created_at),
    moNo: o.mo_no ?? '',
    batchNo: o.batch_no ?? 1,
    batchLabel: str(o.batch_label),
    incoterm: o.incoterm ?? '',
    originCountry: str(o.origin_country),
    originCity: str(o.origin_city),
    originProvince: str(o.origin_province),

    pol: str(o.pol),
    pod: str(o.pod),
    shippingLine: str(o.shipping_line),
    clearingAgent: str(o.clearing_agent),
    bookingNo: str(o.booking_no),
    portInDate: str(o.port_in_date),
    etdSailingDate: str(o.etd_sailing_date),
    croArrivalDate: str(o.cro_arrival_date),
    actualArrivalDate: str(o.actual_arrival_date),

    packingCost: num(o.packing_cost),
    transportationCharges: num(o.transportation_charges),
    containerDetention: num(o.container_detention),
    insurance: num(o.insurance),
    truckingLhrToKhi: num(o.trucking_lhr_to_khi),
    fumigationCost: num(o.fumigation_cost),
    lashing: num(o.lashing),
    qflCharges: num(o.qfl_charges),
    qflContainerMovement: num(o.qfl_container_movement),
    customClearanceCharges: num(o.custom_clearance_charges),
    portCharges: num(o.port_charges),
    dhlCharges: num(o.dhl_charges),
    seaAirFreight: num(o.sea_air_freight),

    gateOutDate: str(o.gate_out_date),
    effectiveDate: str(o.effective_date),
    status: o.current_status ?? '',
    sentToTrucking: !!o.sent_to_trucking,
    remarksLog: jsonArray<RemarkEntry>(o.remarks_log),
    recordState: o.record_state,
    isLocked: !!o.is_locked,
    // Soft-deleted rows are only ever FETCHED for an admin (includeDeleted on
    // the list query), but the flag has to reach the row either way — it is
    // what decides between the delete and the undo button.
    isDeleted: !!o.is_deleted,
    items,
    packages,
    containers,
  }
}

/* ======================================================================
 * WIZARD MAPPING — draft <-> payload
 *
 * CHILD-ROW IDENTITY. The wizard identifies items/packages/containers by a
 * STRING id, and a package's `allocations` reference items by that string.
 * The backend has no column for it — it stores allocations verbatim as JSON
 * and assigns its own integer ids. So the string id is DERIVED from the
 * backend id (`item-42`) and is therefore stable across reloads: an
 * allocation written today still resolves tomorrow.
 *
 * A row the user just added has no backend id yet, so it carries a uuid
 * (`item-<uuid>`) until the first save. `remapNewChildIds` rewrites those —
 * and any allocation pointing at them — to the derived form once the backend
 * has assigned real ids. Without that step, an allocation made against a
 * brand-new item would dangle the moment the page reloaded.
 * ====================================================================== */

/** `item-42` -> 42; `item-<uuid>` -> undefined (a row that isn't saved yet). */
function backendIdOf(clientId: string | undefined): number | undefined {
  const m = /^(?:item|pkg|container)-(\d+)$/.exec(clientId ?? '')
  return m ? Number(m[1]) : undefined
}

/** Optional numeric field: '' / undefined / NaN all mean "not entered".
 *  getValues() hands back RAW form state, so an untouched number input is the
 *  empty STRING, not undefined — the same trap the imports mapper documents. */
function outNum(v: unknown): number | undefined {
  if (v === '' || v === null || v === undefined) return undefined
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : undefined
}

/** '' -> undefined, so the key is omitted rather than sent as an empty string
 *  the backend would reject (dates) or store literally. */
function outStr(v: unknown): string | undefined {
  if (typeof v !== 'string') return undefined
  const t = v.trim()
  return t ? t : undefined
}

export function draftToPayload(draft: LogisticsDraft): LogisticsPayload {
  const items: LogisticsItemPayload[] = (draft.items ?? []).map((it) => ({
    id: backendIdOf(it.id) ?? null,
    job_no: outStr(it.jobNo),
    item_detail: outStr(it.itemDetail),
    quantity: outNum(it.quantity),
    unit_weight: outNum(it.unitWeight),
    // No gross_weight here: the wizard tracks item NET weight (quantity ×
    // unit weight, derived) and gross weight only per PACKAGE. The column
    // exists server-side but the order form never captures it.
    planned_rfd_date: outStr(it.plannedRfdDate),
    actual_rfd_date: outStr(it.actualRfdDate),
    rfd_history: it.rfdHistory ?? [],
  }))

  const packages: LogisticsPackagePayload[] = (draft.packages ?? []).map((p) => ({
    id: backendIdOf(p.id) ?? null,
    colour_code: outStr(p.colourCode),
    packing_works: outStr(p.packingWorks),
    packing_ready_date: outStr(p.packingReadyDate),
    packing_date: outStr(p.packingDate),
    quoted_packing_cost: outNum(p.quotedPackingCost),
    actual_packing_cost: outNum(p.actualPackingCost),
    gross_weight: outNum(p.grossWeight),
    status: outStr(p.status),
    allocations: p.allocations ?? [],
  }))

  const containers: LogisticsContainerPayload[] = (draft.containers ?? []).map((c) => ({
    id: backendIdOf(c.id) ?? null,
    container_no: outStr(c.containerNo),
    container_type: outStr(c.containerType),
  }))

  return {
    order_type: outStr(draft.orderType),
    department: outStr(draft.department),
    // Only meaningful on create — the update route ignores it. Sent on every
    // save anyway because the wizard always posts the whole draft.
    job_kind: outStr(draft.jobKind),
    shipment_mode: outStr(draft.shipmentMode),
    origin_country: outStr(draft.originCountry),
    origin_city: outStr(draft.originCity),
    origin_province: outStr(draft.originProvince),
    customer_name: outStr(draft.customerName),
    mo_no: outStr(draft.moNo),
    batch_no: outNum(draft.batchNo),
    batch_label: outStr(draft.batchLabel),
    incoterm: outStr(draft.incoterm),

    pol: outStr(draft.pol),
    pod: outStr(draft.pod),
    shipping_line: outStr(draft.shippingLine),
    clearing_agent: outStr(draft.clearingAgent),
    booking_no: outStr(draft.bookingNo),
    port_in_date: outStr(draft.portInDate),
    etd_sailing_date: outStr(draft.etdSailingDate),
    cro_arrival_date: outStr(draft.croArrivalDate),
    actual_arrival_date: outStr(draft.actualArrivalDate),

    packing_cost: outNum(draft.packingCost),
    transportation_charges: outNum(draft.transportationCharges),
    container_detention: outNum(draft.containerDetention),
    insurance: outNum(draft.insurance),
    trucking_lhr_to_khi: outNum(draft.truckingLhrToKhi),
    fumigation_cost: outNum(draft.fumigationCost),
    lashing: outNum(draft.lashing),
    qfl_charges: outNum(draft.qflCharges),
    qfl_container_movement: outNum(draft.qflContainerMovement),
    custom_clearance_charges: outNum(draft.customClearanceCharges),
    port_charges: outNum(draft.portCharges),
    dhl_charges: outNum(draft.dhlCharges),
    sea_air_freight: outNum(draft.seaAirFreight),

    current_status: outStr(draft.status),
    gate_out_date: outStr(draft.gateOutDate),
    sent_to_trucking: !!draft.sentToTrucking,
    remarks_log: draft.remarksLog ?? [],

    items,
    packages,
    containers,
  }
}

/** A saved order -> the wizard's draft shape. Child ids are derived from the
 *  backend ids, which is what makes allocations stable across reloads. */
export function apiToDraft(o: ApiLogisticsOrder): LogisticsDraft {
  const row = apiToRow(o)
  return {
    orderType: row.orderType,
    department: row.department,
    shipmentMode: (row.shipmentMode ?? 'Regular') as LogisticsDraft['shipmentMode'],
    jobKind: row.jobKind,
    originCountry: row.originCountry ?? '',
    originCity: row.originCity ?? '',
    originProvince: row.originProvince ?? '',
    customerName: row.customerName,
    moNo: row.moNo,
    batchNo: row.batchNo,
    batchLabel: row.batchLabel ?? '',
    incoterm: row.incoterm as LogisticsDraft['incoterm'],

    items: row.items.map((it) => ({
      id: it.id,
      jobNo: it.jobNo,
      itemDetail: it.itemDetail,
      quantity: it.quantity,
      unitWeight: it.unitWeight,
      grossWeight: it.grossWeight,
      plannedRfdDate: it.plannedRfdDate ?? '',
      actualRfdDate: it.actualRfdDate ?? '',
      rfdHistory: it.rfdHistory,
    })),
    packages: row.packages.map((p) => ({
      id: p.id,
      colourCode: p.colourCode ?? '',
      packingWorks: p.packingWorks ?? '',
      packingReadyDate: p.packingReadyDate ?? '',
      packingDate: p.packingDate ?? '',
      quotedPackingCost: p.quotedPackingCost,
      actualPackingCost: p.actualPackingCost,
      grossWeight: p.grossWeight,
      status: p.status,
      allocations: p.allocations,
    })),
    containers: row.containers.map((c) => ({
      id: c.id,
      containerNo: c.containerNo ?? '',
      containerType: c.containerType,
    })),

    pol: row.pol ?? '',
    pod: row.pod ?? '',
    shippingLine: row.shippingLine ?? '',
    clearingAgent: row.clearingAgent ?? '',
    bookingNo: row.bookingNo ?? '',
    portInDate: row.portInDate ?? '',
    etdSailingDate: row.etdSailingDate ?? '',
    croArrivalDate: row.croArrivalDate ?? '',
    actualArrivalDate: row.actualArrivalDate ?? '',

    packingCost: row.packingCost,
    transportationCharges: row.transportationCharges,
    containerDetention: row.containerDetention,
    insurance: row.insurance,
    truckingLhrToKhi: row.truckingLhrToKhi,
    fumigationCost: row.fumigationCost,
    lashing: row.lashing,
    qflCharges: row.qflCharges,
    qflContainerMovement: row.qflContainerMovement,
    customClearanceCharges: row.customClearanceCharges,
    portCharges: row.portCharges,
    dhlCharges: row.dhlCharges,
    seaAirFreight: row.seaAirFreight,

    status: row.status,
    remarksLog: row.remarksLog,
    gateOutDate: row.gateOutDate ?? '',
    sentToTrucking: row.sentToTrucking,
  } as LogisticsDraft
}

/**
 * After a save, rewrite the ids of rows that were brand-new so they use the
 * derived `item-<backendId>` form — and repoint any allocation that referenced
 * their temporary uuid.
 *
 * Rows keep their relative order through create/update (the backend appends in
 * payload order), so the nth still-unsaved row in the draft corresponds to the
 * nth response row whose id the draft doesn't already know.
 */
export function remapNewChildIds(draft: LogisticsDraft, saved: ApiLogisticsOrder): LogisticsDraft {
  const remap = new Map<string, string>()

  function pair(
    drafted: { id: string }[] | undefined,
    responded: { id: number }[] | undefined,
    prefix: 'item' | 'pkg' | 'container',
  ) {
    const rows = drafted ?? []
    const known = new Set(rows.map((r) => backendIdOf(r.id)).filter((n): n is number => n != null))
    const spare = (responded ?? []).filter((r) => !known.has(r.id))
    let i = 0
    for (const r of rows) {
      if (backendIdOf(r.id) != null) continue
      const match = spare[i++]
      if (match) remap.set(r.id, `${prefix}-${match.id}`)
    }
  }

  pair(draft.items, saved.items?.filter((r) => !r.is_deleted), 'item')
  pair(draft.packages, saved.packages?.filter((r) => !r.is_deleted), 'pkg')
  pair(draft.containers, saved.containers?.filter((r) => !r.is_deleted), 'container')

  if (remap.size === 0) return draft

  return {
    ...draft,
    items: (draft.items ?? []).map((it) => ({ ...it, id: remap.get(it.id) ?? it.id })),
    containers: (draft.containers ?? []).map((c) => ({ ...c, id: remap.get(c.id) ?? c.id })),
    packages: (draft.packages ?? []).map((p) => ({
      ...p,
      id: remap.get(p.id) ?? p.id,
      // The whole point: an allocation made against a not-yet-saved item must
      // follow that item to its real id, or it dangles on the next reload.
      allocations: (p.allocations ?? []).map((a) => ({
        ...a,
        itemId: remap.get(a.itemId) ?? a.itemId,
      })),
    })),
  }
}
