import type {
  ApiTruckingJob, ApiTruckingVehicle, ApiTruckingItem, TruckingPayload, TruckingVehiclePayload,
} from './trucking'
import type {
  VehicleTrackingStatus, VehiclePackageRef, VehicleImportRef, TruckingDraft, TruckingItem,
} from '@/features/truckingStatus/schema'
import { emptyTruckItem } from '@/features/truckingStatus/schema'

/**
 * Backend trucking job -> the shape the list and detail screens draw.
 *
 * Field names stay camelCase and match the wizard's zod types on purpose, so
 * the derived helpers in features/truckingStatus/schema.ts (trackingRollup,
 * freight variance, …) work on these rows unchanged.
 *
 * NO JOB-LEVEL STATUS. Trucking stores tracking per VEHICLE; the job-level
 * reading is a rollup computed by schema.trackingRollup. This mapper
 * deliberately does not invent one — a stored job status would immediately
 * drift from the vehicles it is supposed to summarise.
 */

export interface TruckingListVehicle {
  id: string
  backendId: number
  vehicleNumber?: string
  vehicleType?: string
  noOfPackages?: number
  driverPhone?: string
  netWeight?: number
  grossWeight?: number
  containerNo?: string
  containerType?: string
  trackingStatus?: VehicleTrackingStatus
  /** Stored whole as JSON, in the FE's own shape. */
  packageRefs: VehiclePackageRef[]
  importConsignmentRefs: VehicleImportRef[]
  itemAllocations: { itemId: string; quantity?: number }[]
}

export interface TruckingListRow {
  /** Real database id — what every route navigates on. */
  id: number
  /** Display id. Trucking has no system-id column, so the shipment reference
   *  is what people recognise; rows without one show a dash rather than a
   *  synthesised code that looks searchable but isn't. */
  systemId: string

  movementType: string
  /** 'from-logistics' | 'from-import-fob' | 'manual'. */
  source: string
  sourceRef?: string
  takenAt?: string

  executionDate?: string
  transporterName?: string
  shiftingType?: string
  /** Repeatable item lines. Empty when the record predates this feature and
   *  never had any items entered. */
  items: { itemRef?: string; itemDetails?: string; quantity?: number; uom?: string; pickup?: string; destination?: string; referenceNo?: string }[]
  itemDetails?: string
  pickup?: string
  destination?: string
  referenceNo?: string

  quotedFreight?: number
  actualFreight?: number
  paymentStatus?: string
  paidAmount?: number
  detention?: number

  dispatchNoteDate?: string
  etaWorks?: string
  remarks?: string

  recordState: string
  /** Closed lock: every vehicle Delivered AND the job submitted. */
  isLocked: boolean
  missingFields: string[]
  createdBy?: string
  createdById?: number
  createdAt?: string

  vehicles: TruckingListVehicle[]
}

/** Numerics cross the wire as STRINGS (json_serializer uses default=str). */
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

/** A JSON column that should hold an array; loaded rows have [] or null. */
function jsonArray<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : []
}

function vehicleToRow(v: ApiTruckingVehicle): TruckingListVehicle {
  return {
    // Derived from the backend id so it is stable across reloads — the same
    // reasoning as the logistics mapper's child ids.
    id: `vehicle-${v.id}`,
    backendId: v.id,
    vehicleNumber: str(v.vehicle_number),
    vehicleType: str(v.vehicle_type),
    noOfPackages: v.no_of_packages ?? undefined,
    driverPhone: str(v.driver_phone),
    netWeight: num(v.net_weight),
    grossWeight: num(v.gross_weight),
    containerNo: str(v.container_no),
    containerType: str(v.container_type),
    // The loader normalises onto VehicleTrackingStatus and defaults anything
    // unmapped, so this is safe at face value; the cast is only because the
    // column is a plain String server-side.
    trackingStatus: (str(v.tracking_status) as VehicleTrackingStatus) ?? undefined,
    packageRefs: jsonArray<VehiclePackageRef>(v.package_refs),
    importConsignmentRefs: jsonArray<VehicleImportRef>(v.import_consignment_refs),
    itemAllocations: jsonArray<{ item_id?: string; quantity?: number | null }>(v.item_allocations).map((a) => ({
      itemId: a.item_id ?? '',
      quantity: a.quantity ?? undefined,
    })),
  }
}

export function apiToRow(j: ApiTruckingJob): TruckingListRow {
  // Soft-deleted vehicles are still serialized; the rollup must never count
  // them, or a job with one removed truck would look permanently unfinished.
  const vehicles = (j.vehicles ?? []).filter((v) => !v.is_deleted).map(vehicleToRow)

  return {
    id: j.id,
    systemId: str(j.reference_no) ?? '—',

    movementType: j.movement_type ?? '',
    source: j.source ?? 'manual',
    sourceRef: str(j.source_ref),
    takenAt: str(j.taken_at),

    executionDate: str(j.execution_date),
    transporterName: str(j.transporter_name),
    shiftingType: str(j.shifting_type),
    items: jsonArray<ApiTruckingItem>(j.items).map((it) => ({
      itemRef: str(it.item_ref),
      itemDetails: str(it.item_details),
      quantity: num(it.quantity),
      uom: str(it.uom),
      pickup: str(it.pickup),
      destination: str(it.destination),
      referenceNo: str(it.reference_no),
    })),
    itemDetails: str(j.item_details),
    pickup: str(j.pickup),
    destination: str(j.destination),
    referenceNo: str(j.reference_no),

    quotedFreight: num(j.quoted_freight),
    actualFreight: num(j.actual_freight),
    paymentStatus: str(j.payment_status),
    paidAmount: num(j.paid_amount),
    detention: num(j.detention),

    dispatchNoteDate: str(j.dispatch_note_date),
    etaWorks: str(j.eta_works),
    remarks: str(j.remarks),

    recordState: j.record_state,
    isLocked: !!j.is_locked,
    missingFields: j.missing_fields ?? [],
    createdBy: str(j.created_by),
    createdById: j.created_by_id ?? undefined,
    createdAt: str(j.created_at),

    vehicles,
  }
}

/** Human label for where a job came from. */
export function sourceLabel(source: string): string {
  if (source === 'from-logistics') return 'Logistics'
  if (source === 'from-import-fob') return 'Import FOB'
  return 'Manual'
}

/* ======================================================================
 * WIZARD MAPPING — draft <-> payload
 *
 * Vehicle ids follow the same rule as logistics' child rows: DERIVED from the
 * backend id (`vehicle-42`), so they are stable across reloads. A vehicle the
 * user just added carries a uuid until the first save; `remapNewVehicleIds`
 * adopts the real id afterwards, so the NEXT save updates that row instead of
 * inserting a duplicate.
 * ====================================================================== */

/** `vehicle-42` -> 42; `vehicle-<uuid>` -> undefined (not saved yet). */
function backendIdOf(clientId: string | undefined): number | undefined {
  const m = /^vehicle-(\d+)$/.exec(clientId ?? '')
  return m ? Number(m[1]) : undefined
}

/** getValues() hands back RAW form state, so an untouched number input is the
 *  empty STRING, not undefined — the trap the imports mapper documents. */
function outNum(v: unknown): number | undefined {
  if (v === '' || v === null || v === undefined) return undefined
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : undefined
}

function outStr(v: unknown): string | undefined {
  if (typeof v !== 'string') return undefined
  const t = v.trim()
  return t ? t : undefined
}

export function draftToPayload(draft: TruckingDraft): TruckingPayload {
  const vehicles: TruckingVehiclePayload[] = (draft.vehicles ?? []).map((v) => ({
    id: backendIdOf(v.id) ?? null,
    vehicle_number: outStr(v.vehicleNumber),
    vehicle_type: outStr(v.vehicleType),
    no_of_packages: outNum(v.noOfPackages),
    driver_phone: outStr(v.driverPhone),
    net_weight: outNum(v.netWeight),
    gross_weight: outNum(v.grossWeight),
    container_no: outStr(v.containerNo),
    container_type: outStr(v.containerType),
    tracking_status: outStr(v.trackingStatus),
    package_refs: v.packageRefs ?? [],
    import_consignment_refs: v.importConsignmentRefs ?? [],
    item_allocations: (v.itemAllocations ?? []).map((a) => ({ item_id: a.itemId, quantity: a.quantity ?? null })),
  }))

  const items = (draft.items ?? []).map((it) => ({
    // stable id so per-vehicle allocations can reference the item across saves
    item_ref: it.id,
    item_details: outStr(it.itemDetails),
    quantity: outNum(it.quantity),
    uom: outStr(it.uom),
    pickup: outStr(it.pickup),
    destination: outStr(it.destination),
    reference_no: outStr(it.referenceNo),
  }))
  const firstItem = draft.items?.[0]

  return {
    movement_type: outStr(draft.movementType),
    source: outStr(draft.source),
    source_ref: outStr(draft.sourceRef),

    execution_date: outStr(draft.executionDate),
    transporter_name: outStr(draft.transporterName),
    shifting_type: outStr(draft.shiftingType),
    items,
    // Mirror item[0] onto the legacy singular columns so a backend without
    // the `items` JSON column still gets the first item's data.
    item_details: outStr(firstItem?.itemDetails ?? draft.itemDetails),
    pickup: outStr(firstItem?.pickup ?? draft.pickup),
    destination: outStr(firstItem?.destination ?? draft.destination),
    reference_no: outStr(firstItem?.referenceNo ?? draft.referenceNo),

    quoted_freight: outNum(draft.quotedFreight),
    actual_freight: outNum(draft.actualFreight),
    payment_status: outStr(draft.paymentStatus),
    paid_amount: outNum(draft.paidAmount),
    detention: outNum(draft.detention),

    dispatch_note_date: outStr(draft.dispatchNoteDate),
    eta_works: outStr(draft.etaWorks),
    remarks: outStr(draft.remarks),

    vehicles,
  }
}

/** A saved job -> the wizard's draft shape. */
export function apiToDraft(j: ApiTruckingJob): TruckingDraft {
  const row = apiToRow(j)
  return {
    movementType: row.movementType as TruckingDraft['movementType'],
    source: row.source as TruckingDraft['source'],
    sourceRef: row.sourceRef,
    takenAt: row.takenAt,
    takenSnapshot: Array.isArray(j.taken_snapshot) ? j.taken_snapshot : [],

    executionDate: row.executionDate ?? '',
    transporterName: row.transporterName ?? '',
    shiftingType: (row.shiftingType ?? 'Regular') as TruckingDraft['shiftingType'],
    // Rows saved before `items` existed have none — fall back to synthesizing
    // one item from the legacy row-level fields so the wizard always has at
    // least one item card to edit.
    items: row.items.length
      ? row.items.map((it): TruckingItem => ({
          ...emptyTruckItem(),
          // keep the stored id so per-vehicle allocations still resolve
          ...(it.itemRef ? { id: it.itemRef } : {}),
          itemDetails: it.itemDetails ?? '',
          quantity: it.quantity,
          uom: it.uom ?? '',
          pickup: it.pickup ?? '',
          destination: it.destination ?? '',
          referenceNo: it.referenceNo ?? '',
        }))
      : [{
          ...emptyTruckItem(),
          itemDetails: row.itemDetails ?? '',
          pickup: row.pickup ?? '',
          destination: row.destination ?? '',
          referenceNo: row.referenceNo ?? '',
        }],
    itemDetails: row.itemDetails ?? '',
    pickup: row.pickup ?? '',
    destination: row.destination ?? '',
    referenceNo: row.referenceNo ?? '',

    vehicles: row.vehicles.map((v) => ({
      id: v.id,
      vehicleNumber: v.vehicleNumber ?? '',
      vehicleType: v.vehicleType ?? '',
      noOfPackages: v.noOfPackages,
      driverPhone: v.driverPhone ?? '',
      netWeight: v.netWeight,
      grossWeight: v.grossWeight,
      containerNo: v.containerNo ?? '',
      containerType: v.containerType ?? '',
      trackingStatus: v.trackingStatus,
      packageRefs: v.packageRefs,
      importConsignmentRefs: v.importConsignmentRefs,
      itemAllocations: v.itemAllocations ?? [],
    })),

    quotedFreight: row.quotedFreight,
    actualFreight: row.actualFreight,
    paymentStatus: (row.paymentStatus ?? 'Customer to pay') as TruckingDraft['paymentStatus'],
    paidAmount: row.paidAmount,
    detention: row.detention,

    dispatchNoteDate: row.dispatchNoteDate ?? '',
    etaWorks: row.etaWorks ?? '',
    remarks: row.remarks ?? '',
  } as TruckingDraft
}

/**
 * After a save, give brand-new vehicles their derived ids so the NEXT save
 * updates them rather than inserting duplicates. Rows keep their relative
 * order through create/update (the backend appends in payload order), so the
 * nth still-unsaved row matches the nth response row the draft doesn't know.
 */
export function remapNewVehicleIds(draft: TruckingDraft, saved: ApiTruckingJob): TruckingDraft {
  const rows = draft.vehicles ?? []
  const known = new Set(rows.map((v) => backendIdOf(v.id)).filter((n): n is number => n != null))
  const spare = (saved.vehicles ?? []).filter((v) => !v.is_deleted && !known.has(v.id))

  let i = 0
  let changed = false
  const next = rows.map((v) => {
    if (backendIdOf(v.id) != null) return v
    const match = spare[i++]
    if (!match) return v
    changed = true
    return { ...v, id: `vehicle-${match.id}` }
  })

  return changed ? { ...draft, vehicles: next } : draft
}
