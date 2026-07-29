import {
  MOVEMENT_TYPES,
  SHIFTING_TYPES,
  VEHICLE_TRACKING_STATUSES,
  emptyVehicle,
  trackingRollup,
  totalGrossWeight,
  type TruckingDraft,
  type TruckingSource,
  type Vehicle,
} from '@/features/truckingStatus/schema'
import { CONSIGNMENT_STATUSES } from '@/features/importsStatus/schema'
// Cross-module stores. Both getLogisticsOrders (lib/logisticsStatusData.ts)
// and getConsignments (lib/importsStatusData.ts) were confirmed to exist
// against the real files — see the comments on deriveFromLogistics/
// deriveFromImportsFob below for what was guessed vs. confirmed.
import * as logisticsData from '@/lib/logisticsStatusData'
import * as importsData from '@/lib/importsStatusData'

/**
 * Mock data layer for Trucking Status, mirroring lib/logisticsStatusData.ts.
 *
 * Two kinds of rows feed the Trucking list:
 *   1. MANUAL jobs — the static array below, fully owned by the trucking
 *      operator (including follow-up reminders they create themselves).
 *   2. LIVE-DERIVED requests — computed at read time from the logistics and
 *      imports-FOB stores. These are NEVER copied; they reflect their source
 *      and there is no "accept" step. See deriveOpenRequests().
 *
 * getTruckingJobs() returns the union so the list shows both.
 *
 * NOTE FOR CLAUDE CODE: the cross-module reads below are written against the
 * *expected* exports of logisticsStatusData / importsStatusData and the status
 * labels in their schemas. Confirm the real names and adjust — they are the
 * join key for the whole feature and must match exactly. Anything that can't be
 * confirmed is behind a guarded dynamic import so the module still loads.
 */

export interface TruckingRow {
  systemId: string
  source: TruckingSource
  movementType: TruckingDraft['movementType']
  executionDate?: string
  transporterName?: string
  shiftingType?: TruckingDraft['shiftingType']
  itemDetails?: string
  pickup?: string
  destination?: string
  referenceNo?: string
  vehicles: Vehicle[]
  quotedFreight?: number
  actualFreight?: number
  paymentStatus?: TruckingDraft['paymentStatus']
  paidAmount?: number
  dispatchNoteDate?: string
  etaWorks?: string
  remarks?: string
  // For derived rows: id of the source record so the list can read through.
  sourceRef?: string
  // Whether this request is still "open" / pending trucking action.
  open?: boolean
}

// --- deterministic PRNG so the mock set is stable across reloads -----------
function mulberry32(seed: number) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const rand = mulberry32(0x54_52_55_43) // "TRUC"

const TRANSPORTERS = ['Pak Cargo Movers', 'National Freight', 'Sitara Transport', 'Bismillah Goods', 'Al-Rehman Carriers']
const VEHICLE_TYPES = ['Flatbed', 'Container 20ft', 'Container 40ft', 'Mazda', 'Shehzore']
const ITEMS = ['Cast iron fittings', 'Steel valves', 'Machined housings', 'Pump assemblies', 'Pipe spools', 'Gearbox castings']
const CITIES = ['Karachi', 'Lahore', 'Faisalabad', 'Multan', 'Islamabad', 'Sialkot']

function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(rand() * arr.length)]
}
function isoDate(offsetDays: number): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}

function mockVehicle(movementType: string, allDelivered: boolean): Vehicle {
  const v = emptyVehicle()
  v.vehicleNumber = `${pick(['LEA', 'JW', 'TKB', 'LES'])}-${Math.floor(1000 + rand() * 8999)}`
  v.vehicleType = pick(VEHICLE_TYPES)
  v.noOfPackages = Math.floor(5 + rand() * 40)
  v.driverPhone = `03${Math.floor(10 + rand() * 89)}-${Math.floor(1000000 + rand() * 8999999)}`
  v.netWeight = Math.round((2000 + rand() * 18000) * 100) / 100
  v.grossWeight = Math.round((v.netWeight + 200 + rand() * 1500) * 100) / 100
  if (movementType === 'Inbound') {
    v.containerNo = `${pick(['MSCU', 'TCLU', 'GESU'])}${Math.floor(1000000 + rand() * 8999999)}`
    v.containerType = pick(['20ft', '40ft', '40ft HC'])
  }
  v.trackingStatus = allDelivered ? 'Delivered' : pick(VEHICLE_TRACKING_STATUSES)
  v.builtyStatus = rand() > 0.4 ? 'Yes' : 'NA'
  return v
}

function makeMockJob(i: number): TruckingRow {
  const movementType = pick(MOVEMENT_TYPES)
  const nVehicles = 1 + Math.floor(rand() * 4)
  const allDelivered = rand() > 0.6
  const vehicles = Array.from({ length: nVehicles }, () => mockVehicle(movementType, allDelivered))
  const quoted = Math.round((30000 + rand() * 170000) / 100) * 100
  const actual = Math.round((quoted * (0.85 + rand() * 0.25)) / 100) * 100
  const isIntra = movementType === 'Intrafactory'
  // Some records intentionally incomplete (drafts) so the pending pattern shows.
  const incomplete = rand() > 0.75

  return {
    systemId: `TR-2026-${String(i + 1).padStart(4, '0')}`,
    source: 'manual',
    movementType,
    executionDate: isoDate(-Math.floor(rand() * 30)),
    transporterName: incomplete ? undefined : pick(TRANSPORTERS),
    shiftingType: pick(SHIFTING_TYPES),
    itemDetails: pick(ITEMS),
    pickup: isIntra ? pick(['Qadcast', 'Qadri Engineering', 'Qadbros Engineering']) : pick(CITIES),
    destination: isIntra ? pick(['Qadri Brothers Unit 2', 'Qadbros Engineering Unit 2']) : pick(CITIES),
    referenceNo: isIntra ? undefined : `${movementType === 'Inbound' ? 'IMP' : 'IDM'}-${Math.floor(10000 + rand() * 89999)}`,
    vehicles,
    quotedFreight: quoted,
    actualFreight: incomplete ? undefined : actual,
    paymentStatus: rand() > 0.5 ? 'Customer to pay' : 'QG to pay',
    paidAmount: incomplete ? 0 : Math.round((actual * rand()) / 100) * 100,
    dispatchNoteDate: isoDate(-Math.floor(rand() * 20)),
    etaWorks: isoDate(Math.floor(rand() * 10)),
    open: !allDelivered,
  }
}

const MANUAL_JOBS: TruckingRow[] = Array.from({ length: 26 }, (_, i) => makeMockJob(i))

// Session cache of edits so updateTruckingJob persists within a session.
const EDITS = new Map<string, TruckingRow>()

// ---------------------------------------------------------------------------
// LIVE cross-module derived requests.
//
// These read the logistics + imports stores at call time. Both getter names
// and every row field used below have been confirmed against the real
// lib/logisticsStatusData.ts and lib/importsStatusData.ts (see the comments
// on each derive function). The try/catch is kept as a defensive backstop —
// harmless once the exports are confirmed correct, and cheap insurance if a
// future refactor of either store renames something out from under this file.
//
// Remaining known gap: Imports has no FOB/incoterm flag yet (see isFob()
// below) — the user will add one when Imports is next edited.
// ---------------------------------------------------------------------------

/**
 * CONFIRMED against the real lib/logisticsStatusData.ts: the getter is
 * `getLogisticsOrders`, and every field name read below (systemId, status,
 * gateOutDate, transporterName, itemDetail, originFactory, originCity,
 * destination, originCountry, idm, exportNo) matches `LogisticsOrder` exactly
 * — no guessed names needed fixing here. Only the "open to move" status set
 * was a guess; replaced with the real post-production, not-yet-delivered
 * stages read off EXPORT_STATUSES/LOCAL_STATUSES (logisticsStatus/schema.ts):
 * both pipelines share 'Under Production' → 'Under Packing' → 'Transportation'
 * as their production leg, and 'Transportation' is the first stage that's
 * actually trucking's to move; Local's pipeline ends there before 'Delivered',
 * Export's continues through the sea leg.
 */
function deriveFromLogistics(): TruckingRow[] {
  try {
    const rows = logisticsData.getLogisticsOrders() ?? []
    const OPEN_TO_MOVE = new Set(['Transportation', 'Under Shipping Arrangement', 'At QFL', 'At Port', 'On Water'])
    return rows
      .filter((r) => OPEN_TO_MOVE.has(r.status))
      .map((r): TruckingRow => ({
        systemId: `TR-LOG-${r.systemId}`,
        source: 'from-logistics',
        sourceRef: r.systemId,
        movementType: 'Outbound',
        executionDate: r.gateOutDate || r.dispatchNoteDate,
        transporterName: r.transporterName,
        itemDetails: r.itemDetail,
        pickup: r.originFactory || r.originCity,
        destination: r.destination || r.originCountry,
        referenceNo: r.idm || r.exportNo,
        vehicles: [],
        open: true,
      }))
  } catch {
    return []
  }
}

/**
 * CONFIRMED against the real lib/importsStatusData.ts: the getter is
 * `getConsignments`, and `ConsignmentRow` (its return shape) does NOT have
 * `transporterName`, `itemSummary`, `supplierOrigin`, `works`, or `reference`
 * — those guessed field names have been dropped/repointed below to the real
 * ones (`items[0].itemName`/`requisitionSummary`, `origin`, `branch`,
 * `systemId`). "Past Under Production" is now an index comparison against the
 * real ordered CONSIGNMENT_STATUSES (importsStatus/schema.ts) rather than a
 * hardcoded name set, per the instruction.
 */
function deriveFromImportsFob(): TruckingRow[] {
  try {
    const rows = importsData.getConsignments() ?? []
    const productionIdx = CONSIGNMENT_STATUSES.indexOf('Under Production')
    // TODO(claude-code / user): real FOB flag. ConsignmentRow has no incoterm
    // field yet — this heuristic is a deliberate placeholder that always
    // evaluates false against the real data until Imports gets one, per the
    // task's note that the user will add it later.
    const isFob = (r: unknown) => {
      const rec = r as Record<string, unknown>
      return rec.incoterm === 'FOB' || rec.isFob === true
    }
    return rows
      .filter((r) => CONSIGNMENT_STATUSES.indexOf(r.status) > productionIdx && isFob(r))
      .map((r): TruckingRow => ({
        systemId: `TR-IMP-${r.systemId}`,
        source: 'from-import-fob',
        sourceRef: r.systemId,
        movementType: 'Inbound',
        itemDetails: r.items[0]?.itemName ?? r.requisitionSummary,
        pickup: r.origin,
        destination: r.branch,
        referenceNo: r.systemId,
        vehicles: [],
        open: true,
      }))
  } catch {
    return []
  }
}

/** The live union of derived open requests (never copied). */
export function deriveOpenRequests(): TruckingRow[] {
  return [...deriveFromLogistics(), ...deriveFromImportsFob()]
}

// --- public API (mirrors logisticsStatusData) ------------------------------

export interface TruckingFilters {
  movementType?: string[]
  source?: string[]
  openOnly?: boolean
  search?: string
}

function applyEdits(row: TruckingRow): TruckingRow {
  return EDITS.get(row.systemId) ?? row
}

export function getTruckingJobs(filters: TruckingFilters = {}): TruckingRow[] {
  const manual = MANUAL_JOBS.map(applyEdits)
  const derived = deriveOpenRequests()
  // A brand-new job being created (id minted by the wizard, persisted via
  // updateTruckingJob so its data survives the /new → /:id/edit/:step
  // remount) lives only in EDITS until Submit — applyEdits only maps over
  // MANUAL_JOBS, so without this it would be invisible here even though
  // getTruckingJob() is expected to find it mid-creation.
  const knownIds = new Set([...manual, ...derived].map((r) => r.systemId))
  const inProgressDrafts = [...EDITS.values()].filter((r) => !knownIds.has(r.systemId))
  let all = [...derived, ...manual, ...inProgressDrafts]

  if (filters.movementType?.length) {
    all = all.filter((r) => filters.movementType!.includes(r.movementType))
  }
  if (filters.source?.length) {
    all = all.filter((r) => filters.source!.includes(r.source))
  }
  if (filters.openOnly) {
    all = all.filter((r) => r.open)
  }
  if (filters.search?.trim()) {
    const q = filters.search.toLowerCase()
    all = all.filter((r) =>
      [r.systemId, r.transporterName, r.itemDetails, r.pickup, r.destination, r.referenceNo]
        .filter(Boolean)
        .some((s) => String(s).toLowerCase().includes(q)),
    )
  }
  return all
}

export function getTruckingJob(id: string): TruckingDraft | undefined {
  const row = getTruckingJobs().find((r) => r.systemId === id)
  if (!row) return undefined
  return rowToDraft(row)
}

/**
 * True only for a job that's a "real" record — a manual job or a live
 * derived request — as opposed to an in-progress draft that exists solely
 * because the wizard persisted it mid-creation so its data would survive a
 * step's remount. The wizard uses this (not "does getTruckingJob find it")
 * to decide new-record-creation-mode vs. genuine-edit-mode: a mid-creation
 * draft must still behave like new mode (sequential Next-validation, no
 * free stepper jumps, no unsaved-changes guard) all the way to Submit.
 */
export function isKnownRecord(systemId: string): boolean {
  return MANUAL_JOBS.some((r) => r.systemId === systemId) || deriveOpenRequests().some((r) => r.systemId === systemId)
}

export function updateTruckingJob(systemId: string, data: TruckingDraft): void {
  const base = getTruckingJobs().find((r) => r.systemId === systemId)
  const merged: TruckingRow = {
    ...(base ?? { systemId, source: 'manual', movementType: data.movementType, vehicles: [] }),
    ...data,
    systemId,
  }
  EDITS.set(systemId, merged)
}

// --- derived helpers for list/detail ---------------------------------------

/** Bridge a stored row to the wizard's draft shape. */
export function rowToDraft(row: TruckingRow): TruckingDraft {
  return {
    movementType: row.movementType,
    source: row.source,
    executionDate: row.executionDate ?? '',
    transporterName: row.transporterName ?? '',
    shiftingType: row.shiftingType ?? 'Regular',
    itemDetails: row.itemDetails ?? '',
    pickup: row.pickup ?? '',
    destination: row.destination ?? '',
    referenceNo: row.referenceNo ?? '',
    vehicles: row.vehicles?.length ? row.vehicles : [emptyVehicle()],
    quotedFreight: row.quotedFreight ?? 0,
    actualFreight: row.actualFreight ?? 0,
    paymentStatus: row.paymentStatus ?? 'Customer to pay',
    paidAmount: row.paidAmount ?? 0,
    dispatchNoteDate: row.dispatchNoteDate ?? '',
    etaWorks: row.etaWorks ?? '',
    remarks: row.remarks ?? '',
  }
}

export function rollupLabel(row: TruckingRow): string {
  return trackingRollup(row.vehicles).label
}

export function rowGrossWeight(row: TruckingRow): number {
  return totalGrossWeight(row.vehicles)
}

/** Source provenance tag for the list. */
export function sourceLabel(source: TruckingSource): string {
  return source === 'from-logistics' ? 'Logistics' : source === 'from-import-fob' ? 'Import FOB' : 'Manual'
}
