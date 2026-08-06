import {
  MOVEMENT_TYPES,
  SHIFTING_TYPES,
  VEHICLE_TRACKING_STATUSES,
  DRAFT_DEFAULT_VALUES,
  emptyVehicle,
  trackingRollup,
  totalGrossWeight,
  type TruckingDraft,
  type TruckingSource,
  type Vehicle,
  type TakenSourceSnapshot,
} from '@/features/truckingStatus/schema'
import { CONSIGNMENT_STATUSES } from '@/features/importsStatus/schema'
// Cross-module stores. Both getLogisticsOrders (lib/logisticsStatusData.ts)
// and getConsignments (lib/importsStatusData.ts) were confirmed to exist
// against the real files — see the comments on deriveFromLogistics/
// deriveFromImportsFob below for what was guessed vs. confirmed.
import * as logisticsData from '@/lib/logisticsStatusData'
import * as importsData from '@/lib/importsStatusData'
// Type-only — erased at compile time, so importing it here does NOT create a
// runtime circular dependency with lib/logisticsStatusData.ts (which does not
// import this file). getTruckingReadthrough lives here rather than there
// because this module already owns the established "read the other store"
// direction (Trucking → Logistics/Imports); mirroring that keeps the import
// graph one-directional.
import type { TruckingReadthrough } from '@/features/logisticsStatus/schema'
import { itemNetWeight } from '@/features/logisticsStatus/schema'

/**
 * Mock data layer for Trucking Status, mirroring lib/logisticsStatusData.ts.
 *
 * Two kinds of rows feed the Trucking list:
 *   1. MANUAL jobs — the static array below, fully owned by the trucking
 *      operator (including follow-up reminders they create themselves).
 *   2. LIVE-DERIVED requests — computed at read time from the logistics and
 *      imports-FOB stores. These are NEVER copied; they reflect their source
 *      and there is no "accept" step — UNTIL an operator clicks Take Action
 *      (see takeAction() below), at which point that specific source record
 *      converts into an independent, persisted job and permanently stops
 *      being re-derived (see findTakenJobBySourceRef and the exclusion
 *      filters in deriveFromLogistics/deriveFromImportsFob).
 *
 * getTruckingJobs() returns the union so the list shows both.
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
  detention?: number
  dispatchNoteDate?: string
  etaWorks?: string
  remarks?: string
  // For derived rows: id of the source record so the list can read through.
  sourceRef?: string
  // Set once this row was created via Take Action — see takeAction() below.
  takenAt?: string
  takenSnapshot?: TakenSourceSnapshot[]
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
    detention: rand() > 0.7 ? Math.round((5000 + rand() * 25000) / 100) * 100 : 0,
    dispatchNoteDate: isoDate(-Math.floor(rand() * 20)),
    etaWorks: isoDate(Math.floor(rand() * 10)),
    open: !allDelivered,
  }
}

const MANUAL_JOBS: TruckingRow[] = Array.from({ length: 26 }, (_, i) => makeMockJob(i))

// Session cache of edits so updateTruckingJob persists within a session. Also
// the durable store for taken jobs — see takeAction()/findTakenJobBySourceRef.
const EDITS = new Map<string, TruckingRow>()

/**
 * A source record (Logistics order or FOB import) that already has an
 * independent, persisted job here — found by scanning EDITS, since that is
 * the only place a taken job lives (not-yet-taken derived rows are computed
 * fresh on every call and never stored). This is the single source of truth
 * both for "has this already been taken" (used to exclude it from further
 * live derivation below) and for Logistics' read-through panel.
 */
export function findTakenJobBySourceRef(sourceRef: string): TruckingRow | undefined {
  return [...EDITS.values()].find((r) => r.sourceRef === sourceRef)
}

// ---------------------------------------------------------------------------
// LIVE cross-module derived requests.
//
// These read the logistics + imports stores at call time. Both getter names
// and every row field used below have been confirmed against the real
// lib/logisticsStatusData.ts and lib/importsStatusData.ts. The try/catch is
// kept as a defensive backstop — harmless once the exports are confirmed
// correct, and cheap insurance if a future refactor of either store renames
// something out from under this file.
//
// TRANSPORTATION REMOVED FROM LOGISTICS: Logistics no longer tracks
// transporter/gate-out-leg fields at all — that whole leg is now Trucking's
// job, handed off explicitly via the order's `sentToTrucking` checkbox
// (Logistics Status Step 5) rather than inferred from order status. So
// deriveFromLogistics below is now gated on `sentToTrucking`, not a status
// set, and excludes any order that already has a taken job (see
// findTakenJobBySourceRef) so a taken request never shows twice.
// ---------------------------------------------------------------------------

function deriveFromLogistics(): TruckingRow[] {
  try {
    const rows = logisticsData.getLogisticsOrders() ?? []
    return rows
      .filter((r) => r.sentToTrucking && !findTakenJobBySourceRef(r.systemId))
      .map((r): TruckingRow => {
        const first = r.items[0]
        const more = r.items.length - 1
        const itemSummary = first ? `${first.itemDetail}${more > 0 ? ` +${more} more` : ''}` : 'No items'
        const ref = first?.jobNo || r.systemId
        const packingWorks = r.packages.find((p) => p.packingWorks)?.packingWorks
        return {
          systemId: `TR-LOG-${r.systemId}`,
          source: 'from-logistics',
          sourceRef: r.systemId,
          movementType: 'Outbound',
          executionDate: r.gateOutDate,
          itemDetails: itemSummary,
          pickup: packingWorks || (r.orderType === 'Local' ? r.originCity : undefined),
          destination: r.orderType === 'Export' ? r.pol : undefined,
          referenceNo: ref,
          vehicles: [],
          open: true,
        }
      })
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
 * `systemId`). "Past Under Production" is an index comparison against the
 * real ordered CONSIGNMENT_STATUSES (importsStatus/schema.ts).
 *
 * Excludes any consignment that already has a taken job — same
 * never-shows-twice guarantee as deriveFromLogistics above. Imports has no
 * explicit "sent to trucking" flag of its own; the taken-job lookup alone is
 * enough to prevent a duplicate, so nothing was added to importsStatus.
 */
function deriveFromImportsFob(): TruckingRow[] {
  try {
    const rows = importsData.getConsignments() ?? []
    const productionIdx = CONSIGNMENT_STATUSES.indexOf('Under Production')
    return rows
      .filter((r) =>
        CONSIGNMENT_STATUSES.indexOf(r.status) > productionIdx &&
        r.incoterm === 'FOB' &&
        !findTakenJobBySourceRef(r.systemId),
      )
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

/**
 * Export orders needing outbound trucking to the port. An export shipment has
 * to be trucked from the factory/QFL to the port of loading before it can
 * sail — that inland leg is Trucking's job, the mirror of the inbound leg it
 * does for FOB imports. Sourced from Logistics export orders that have reached
 * a stage where the goods are ready to move but not yet on the water. Distinct
 * from the sentToTrucking-gated delivery leg above: this is the port leg, not
 * the customer-delivery leg, and (per the confirmed scope) does not get a
 * Take Action button — it stays always-live, no accept step.
 */
function deriveFromExports(): TruckingRow[] {
  try {
    const rows = logisticsData.getLogisticsOrders() ?? []
    // Export orders that are packed/ready and heading for the port, but not
    // yet sailed — those are the ones needing the truck to the port.
    const READY_TO_PORT = new Set(['Under Packing', 'Transportation', 'Under Shipping Arrangement', 'At QFL'])
    return rows
      .filter((r) => r.orderType === 'Export' && READY_TO_PORT.has(r.status))
      .map((r): TruckingRow => {
        const first = r.items[0]
        const more = r.items.length - 1
        const itemSummary = first ? `${first.itemDetail}${more > 0 ? ` +${more} more` : ''}` : 'No items'
        const packingWorks = r.packages.find((p) => p.packingWorks)?.packingWorks
        return {
          systemId: `TR-EXP-${r.systemId}`,
          source: 'from-export',
          sourceRef: r.systemId,
          movementType: 'Outbound',
          itemDetails: itemSummary,
          pickup: packingWorks || 'Factory',
          destination: r.pol || 'Port of loading',
          referenceNo: first?.jobNo || r.systemId,
          vehicles: [],
          open: true,
        }
      })
  } catch {
    return []
  }
}

/** The live union of derived open requests (never copied). */
export function deriveOpenRequests(): TruckingRow[] {
  return [...deriveFromLogistics(), ...deriveFromImportsFob(), ...deriveFromExports()]
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
  // getTruckingJob() is expected to find it mid-creation. Taken jobs (see
  // takeAction()) live here too, for the same reason.
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
 * free stepper jumps, no unsaved-changes guard) all the way to Submit —
 * which is also the correct behaviour for a freshly-taken job's first save,
 * since it hasn't been through Submit yet either.
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

/**
 * TAKE ACTION: converts a still-open, live-derived request into an
 * independent, persisted TruckingDraft. Builds a takenSnapshot from the
 * source record's current items/packages (package-wise for a Logistics
 * order that has packages, item-wise otherwise), mints a new id, and stores
 * the resulting draft directly into EDITS via updateTruckingJob — which is
 * exactly what makes findTakenJobBySourceRef() start finding it, and
 * therefore what makes deriveFromLogistics/deriveFromImportsFob stop
 * re-deriving the source as a duplicate open row from this point on.
 *
 * Returns the new job's systemId so the caller can navigate straight into
 * the wizard, pre-filled.
 */
export function takeAction(sourceType: 'from-logistics' | 'from-import-fob', sourceId: string): string {
  const newId = crypto.randomUUID()
  let snapshot: TakenSourceSnapshot[] = []
  let itemDetails = 'No items'
  let referenceNo = sourceId
  const movementType: TruckingDraft['movementType'] = sourceType === 'from-import-fob' ? 'Inbound' : 'Outbound'

  if (sourceType === 'from-logistics') {
    const order = logisticsData.getLogisticsOrder(sourceId)
    if (order) {
      snapshot = order.packages.length
        ? order.packages.map((pkg, i) => ({
            sourcePackageId: pkg.id,
            label: `Package ${i + 1}${pkg.colourCode ? ` — ${pkg.colourCode}` : ''}`,
            itemDetails: pkg.allocations
              .map((a) => order.items.find((it) => it.id === a.itemId)?.itemDetail)
              .filter(Boolean)
              .join(', '),
            quantity: pkg.allocations.reduce((s, a) => s + (a.quantity ?? 0), 0),
            weight: pkg.grossWeight,
          }))
        // No packages yet — fall back to net weight (quantity × unit weight),
        // since items don't carry their own gross weight (that's a
        // package-level figure once the order reaches Packing).
        : order.items.map((it) => ({
            label: it.itemDetail || 'Item',
            itemDetails: it.itemDetail,
            quantity: it.quantity,
            weight: itemNetWeight(it),
          }))
      const first = order.items[0]
      const more = order.items.length - 1
      itemDetails = first ? `${first.itemDetail}${more > 0 ? ` +${more} more` : ''}` : 'No items'
      referenceNo = first?.jobNo || sourceId
    }
  } else {
    const consignment = importsData.getConsignment(sourceId)
    if (consignment) {
      snapshot = consignment.items.map((it) => ({
        label: it.itemName || 'Item',
        itemDetails: it.itemName,
        quantity: it.quantity,
        weight: it.grossWeight ?? undefined,
      }))
      const first = consignment.items[0]
      const more = consignment.items.length - 1
      itemDetails = first ? `${first.itemName}${more > 0 ? ` +${more} more` : ''}` : 'No items'
      referenceNo = sourceId
    }
  }

  const draft: TruckingDraft = {
    ...DRAFT_DEFAULT_VALUES,
    movementType,
    source: sourceType,
    sourceRef: sourceId,
    takenAt: new Date().toISOString(),
    takenSnapshot: snapshot,
    itemDetails,
    referenceNo,
    vehicles: [emptyVehicle()],
  }
  updateTruckingJob(newId, draft)
  return newId
}

/**
 * Read-through summary for Logistics Status's Step 5 "Trucking progress"
 * panel — the mirror direction of deriveFromLogistics above (Logistics
 * reading Trucking, instead of the other way round), owned here so the
 * import graph between the two stores stays one-directional.
 */
export function getTruckingReadthrough(logisticsOrderId: string): TruckingReadthrough | null {
  const taken = findTakenJobBySourceRef(logisticsOrderId)
  if (taken) {
    return {
      truckingJobId: taken.systemId,
      transporterName: taken.transporterName,
      vehicleCount: taken.vehicles.length,
      trackingRollupLabel: rollupLabel(taken),
      taken: true,
    }
  }
  const stillOpen = deriveFromLogistics().some((r) => r.sourceRef === logisticsOrderId)
  if (!stillOpen) return null
  return { truckingJobId: '', vehicleCount: 0, trackingRollupLabel: 'No vehicles', taken: false }
}

// --- derived helpers for list/detail ---------------------------------------

/** Bridge a stored row to the wizard's draft shape. */
export function rowToDraft(row: TruckingRow): TruckingDraft {
  return {
    movementType: row.movementType,
    source: row.source,
    sourceRef: row.sourceRef,
    takenAt: row.takenAt,
    takenSnapshot: row.takenSnapshot ?? [],
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
    detention: row.detention ?? 0,
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
  return source === 'from-logistics' ? 'Logistics' : source === 'from-import-fob' ? 'Import FOB' : source === 'from-export' ? 'Export' : 'Manual'
}

/**
 * Import consignments available to check off against a vehicle on an Inbound
 * job — two or more import shipments can legitimately ride the same truck,
 * so the Vehicles step needs the full candidate list, not just the one
 * consignment (if any) this specific job was taken from.
 */
export function getImportConsignmentOptions(): { systemId: string; label: string; grossWeight: number | null; netWeight: number | null }[] {
  try {
    const rows = importsData.getConsignments() ?? []
    return rows.map((r) => {
      const gross = importsData.consignmentGrossWeight(r)
      const net = importsData.consignmentNetWeight(r)
      const wt = gross != null ? ` · ${gross.toLocaleString()} kg` : ' · weight pending'
      return {
        systemId: r.systemId,
        label: `${r.systemId} — ${r.items[0]?.itemName ?? r.requisitionSummary}${wt}`,
        grossWeight: gross,
        netWeight: net,
      }
    })
  } catch {
    return []
  }
}
