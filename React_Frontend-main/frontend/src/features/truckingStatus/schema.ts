import { z } from 'zod'
import type { SubmitRequirement } from '@/lib/submitRequirements'

/**
 * Trucking Status — the third status module, sibling to importsStatus and
 * logisticsStatus. It follows the same conventions as those two:
 *   - one zod object per wizard step, merged into a permissive draft schema;
 *   - a single conditional driver per screen (here: movementType), read from
 *     form context in every step rather than scattered `if`s in JSX;
 *   - derived values are functions, never stored fields, and are shown
 *     read-only with their formula stated.
 *
 * The one structural feature that sets Trucking apart is the header + repeating
 * vehicle array: one consignment can move on several trucks, and a number of
 * fields (vehicle no., packages, container, driver phone, weights, per-vehicle
 * tracking) vary per vehicle. This mirrors the header + item-lines
 * pattern in importsStatus (useFieldArray).
 */

// --- Enums / conditional driver -------------------------------------------
export const MOVEMENT_TYPES = ['Intrafactory', 'Outbound', 'Inbound'] as const
export type MovementType = (typeof MOVEMENT_TYPES)[number]

// Provenance of a trucking job. Derived rows reflect a live source record in
// logistics / imports-FOB and are never copied; manual rows are fully owned by
// the trucking operator (follow-up reminders they create themselves).
export const TRUCKING_SOURCES = ['manual', 'from-logistics', 'from-import-fob', 'from-export'] as const
export type TruckingSource = (typeof TRUCKING_SOURCES)[number]

export const SHIFTING_TYPES = ['Regular', 'Special', 'Emergency', 'Others'] as const

// Fixed fleet vehicle types for the Step-2 dropdown.
export const VEHICLE_TYPES = [
  'Mazda', 'Shehzore', 'Rickshaw',
  "20' Flat Bed", "40' Flat Bed",
  "20' Container Carrier", "40' Container Carrier",
] as const

// The 5 Qadri Group factories — used as pickup/destination dropdowns for
// intrafactory movements (free text for outbound/inbound).
export const QG_FACTORIES = [
  'Qadcast',
  'Qadbros Engineering',
  'Qadri Engineering',
  'Qadri Brothers Unit 2',
  'Qadbros Engineering Unit 2',
] as const

export const CONTAINER_TYPES = ['20ft', '40ft', '40ft HC', 'Other'] as const

export const PAYMENT_STATUSES = ['Customer to pay', 'QG to pay'] as const

// Per-vehicle tracking pipeline, ordered. Each truck advances independently;
// the consignment-level status is a derived rollup over the vehicles.
export const VEHICLE_TRACKING_STATUSES = ['Going to load', 'Loading', 'On road', 'Delivered'] as const
export type VehicleTrackingStatus = (typeof VEHICLE_TRACKING_STATUSES)[number]

// BUILTY_STATUSES removed per confirmed design.

// --- Per-vehicle line ------------------------------------------------------

/**
 * Which Logistics packages (by id, from the source order's packages[]) are
 * riding on this vehicle. A package might fill a whole vehicle on its own, or
 * several small packages might share one truck — many-to-many.
 */
export const vehiclePackageRefSchema = z.object({
  packageId: z.string(),
})
export type VehiclePackageRef = z.infer<typeof vehiclePackageRefSchema>

/**
 * Which import consignments (by systemId from importsStatus) are riding on
 * this vehicle. Confirmed: two or more import shipments CAN be moved on one
 * vehicle, and one or more items can be moved on the same vehicle too — so
 * this is an array, not a single ref.
 */
export const vehicleImportRefSchema = z.object({
  consignmentId: z.string(), // importsStatus ConsignmentRow.systemId
  /** Pre-filled from the consignment's gross weight when checked on, but the
   *  trucking user can override per vehicle (the goods may split across trucks). */
  grossWeight: z.number().optional(),
  label: z.string().optional(),
})
export type VehicleImportRef = z.infer<typeof vehicleImportRefSchema>

/**
 * A quantity of one Step-1 item loaded onto a specific vehicle. This is what
 * lets the user split an item across trucks — e.g. 30 of item A on vehicle 1
 * and 20 on vehicle 2. `itemId` points at truckingItemSchema.id.
 */
export const vehicleItemAllocationSchema = z.object({
  itemId: z.string(),
  quantity: z.number().min(0).optional(),
})
export type VehicleItemAllocation = z.infer<typeof vehicleItemAllocationSchema>

export const vehicleSchema = z.object({
  /**
   * Row identity, needed so a save can say "update THIS vehicle" rather than
   * "replace them all". Derived from the backend id once saved
   * (`vehicle-42`) and therefore stable across reloads; a row added in the
   * browser carries a uuid until its first save, which lib/api/truckingMap's
   * remapNewVehicleIds then swaps for the real one.
   *
   * Without it the update route's diff sees no matching ids and treats every
   * save as delete-all + insert-all, losing the vehicles' ids and their
   * change history.
   */
  id: z.string().default(() => `vehicle-${crypto.randomUUID()}`),
  vehicleNumber: z.string().optional(),
  vehicleType: z.string().optional(),
  noOfPackages: z.number().int().min(0).optional(),
  driverPhone: z.string().optional(),
  netWeight: z.number().min(0).optional(),
  grossWeight: z.number().min(0).optional(),
  containerNo: z.string().optional(),
  containerType: z.string().optional(),
  trackingStatus: z.enum(VEHICLE_TRACKING_STATUSES).optional(),
  // builtyStatus removed per confirmed design.
  /** Package refs for logistics-sourced jobs. */
  packageRefs: z.array(vehiclePackageRefSchema).default([]),
  /** Import consignment refs — multiple imports can ride one vehicle. */
  importConsignmentRefs: z.array(vehicleImportRefSchema).default([]),
  /** How much of each Step-1 item is loaded on THIS vehicle. */
  itemAllocations: z.array(vehicleItemAllocationSchema).default([]),
})
export type Vehicle = z.infer<typeof vehicleSchema>

export function emptyVehicle(): Vehicle {
  return {
    // Unique per row so two brand-new vehicles never collide before the
    // backend gives them real ids.
    id: `vehicle-${crypto.randomUUID()}`,
    vehicleNumber: '',
    vehicleType: '',
    noOfPackages: 0,
    driverPhone: '',
    netWeight: 0,
    grossWeight: 0,
    containerNo: '',
    containerType: '',
    trackingStatus: 'Going to load',
    packageRefs: [],
    importConsignmentRefs: [],
    itemAllocations: [],
  }
}

/**
 * One item/package snapshot taken from the source record at the moment
 * "Take Action" is pressed. Confirmed design: Take Action is a REAL accept
 * step — the resulting job becomes an independent, editable TruckingDraft,
 * disconnected from further live updates to its source (this reverses the
 * earlier "always live-linked, no accept" answer for the specific case of a
 * job someone has actively taken on; jobs nobody has taken yet remain the
 * live, never-copied open-request rows exactly as before). This snapshot is
 * what pre-fills the "New Trucking Job" form so the operator only has to
 * fill in the trucking-specific remainder, never re-key what's already known.
 */
export const takenSourceSnapshotSchema = z.object({
  sourcePackageId: z.string().optional(), // LogisticsPackage.id, if package-wise
  label: z.string(), // human-readable summary shown while filling the form
  itemDetails: z.string().optional(),
  quantity: z.number().optional(),
  weight: z.number().optional(),
})
export type TakenSourceSnapshot = z.infer<typeof takenSourceSnapshotSchema>

// --- Per-item line (Step 1) -------------------------------------------------

/**
 * A trucking job can carry several distinct items, each with its own
 * pickup/destination/quantity/UoM/IDM (e.g. one truck run picking up from two
 * factories, or one shipment mixing items bound for different destinations).
 * Weight lives on the vehicle (Step 2), not here — one item's quantity can
 * split across trucks, so weight has to be per-vehicle too.
 * Mirrors the header + item-lines pattern used by importsStatus/logisticsStatus.
 *
 * Not yet backed by its own backend column — see draftToPayload/apiToDraft in
 * lib/api/truckingMap.ts for how item[0] mirrors onto the legacy singular
 * fields (itemDetails/pickup/destination/referenceNo) until a real `items`
 * JSON column exists server-side.
 */
export const TRUCK_UNITS = [
  'Pcs', 'Set', 'Pair', 'Roll', 'Box', 'Carton', 'Drum', 'Pallet',
  'Kg', 'Ton', 'Bag', 'Bundle', 'Coil', 'Sheet',
] as const

export const truckingItemSchema = z.object({
  id: z.string(),
  itemDetails: z.string().optional(),
  // Quantity + unit of measurement live on the item (weight moved to the
  // vehicle — it's captured per vehicle in Step 2, since one item's quantity
  // can split across trucks).
  quantity: z.number().min(0).optional(),
  uom: z.string().optional(),
  pickup: z.string().optional(),
  destination: z.string().optional(),
  // Shipment reference / IDM — outbound + inbound only, same rule as the header.
  referenceNo: z.string().optional(),
})
export type TruckingItem = z.infer<typeof truckingItemSchema>

// Monotonic per-tab counter so two items added in the same render never
// collide before the first save gives them a stable identity.
let truckItemSeq = 0
export function emptyTruckItem(): TruckingItem {
  truckItemSeq += 1
  return {
    id: `item-${Date.now()}-${truckItemSeq}`,
    itemDetails: '',
    quantity: undefined,
    uom: '',
    pickup: '',
    destination: '',
    referenceNo: '',
  }
}

// --- Step 1: Movement + Item ----------------------------------------------
export const movementSchema = z.object({
  movementType: z.enum(MOVEMENT_TYPES),
  // No .default() here — DRAFT_DEFAULT_VALUES below always sets this
  // explicitly, and a zod-level default makes the input type (what
  // zodResolver validates) diverge from the output type (TruckingDraft,
  // via z.infer), which zodResolver<schema> vs useForm<TruckingDraft> then
  // reject as incompatible Resolver types.
  source: z.enum(TRUCKING_SOURCES),
  /** Set only when this job originated from a Take Action on an open
   *  request. Once set, the job is fully independent — later changes to the
   *  original Logistics/Imports record do NOT flow through; this is a point-
   *  in-time snapshot reference kept for traceability only ("taken from
   *  order X"), never a live pointer. */
  sourceRef: z.string().optional(),
  /** ISO datetime the operator clicked Take Action — undefined for jobs
   *  created directly via "New Trucking Job" (source: 'manual') and for
   *  still-open, not-yet-taken derived rows (which never reach the wizard
   *  at all — see truckingStatusData.ts). */
  takenAt: z.string().optional(),
  /** Snapshot of the source's items/packages at the moment of taking, used
   *  only to pre-fill the form — not re-read live afterward. */
  takenSnapshot: z.array(takenSourceSnapshotSchema).default([]),
  executionDate: z.string().optional(), // ISO yyyy-mm-dd
  transporterName: z.string().optional(),
  shiftingType: z.enum(SHIFTING_TYPES).optional(),
  /** Repeatable item lines — see truckingItemSchema. */
  items: z.array(truckingItemSchema).default([]),
  // Legacy singular fields, kept as a mirror of items[0] for backward
  // compatibility until the backend gets a real `items` JSON column.
  itemDetails: z.string().optional(),
  pickup: z.string().optional(),
  destination: z.string().optional(),
  // Shipment reference / IDM — outbound + inbound only.
  referenceNo: z.string().optional(),
})

// --- Step 2: Vehicles ------------------------------------------------------
export const vehiclesSchema = z.object({
  vehicles: z.array(vehicleSchema),
})

// --- Step 3: Freight + Payment --------------------------------------------
export const freightSchema = z.object({
  quotedFreight: z.number().min(0).optional(),
  actualFreight: z.number().min(0).optional(),
  // savings & ratePerKg are derived, never keyed in.
  paymentStatus: z.enum(PAYMENT_STATUSES).optional(),
  paidAmount: z.number().min(0).optional(),
  // outstanding is derived.
  /** Vehicle/container detention cost. */
  detention: z.number().min(0).optional(),
})

// --- Step 4: Tracking ------------------------------------------------------
// Per-vehicle tracking lives on the vehicle rows (Step 2 schema); this
// step edits those same rows plus the derived consignment rollup. No new
// persisted fields, but a remarks field is handy.
export const trackingSchema = z.object({
  dispatchNoteDate: z.string().optional(),
  etaWorks: z.string().optional(),
  remarks: z.string().optional(),
  /** Generated server-side (app/trucking/serializers.py::build_system_remarks)
   *  from the taken-from hand-off and the vehicles' current tracking
   *  statuses. Read-only display only — never sent back, see draftToPayload. */
  systemRemarks: z.string().default(''),
})

/**
 * Permissive draft schema for react-hook-form. Composed from the raw shapes so
 * the wizard has one flat object; per-step validation uses the step schemas
 * above. `.extend()` is used (not the deprecated `.merge()`) for zod v4.
 */
export const truckingDraftSchema = movementSchema
  .extend(vehiclesSchema.shape)
  .extend(freightSchema.shape)
  .extend(trackingSchema.shape)

export type TruckingDraft = z.infer<typeof truckingDraftSchema>

/**
 * Stricter checks applied only at submit time (mirrors importsStatus's
 * consignmentSubmitSchema via superRefine). Draft never blocks; submit enforces
 * the conditional requirements that depend on movementType.
 */
export const truckingSubmitSchema = truckingDraftSchema.superRefine((val, ctx) => {
  if (!val.vehicles?.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['vehicles'], message: 'At least one vehicle is required' })
  }
  // Shipment reference / IDM is OPTIONAL (confirmed) — no required validation.
  if (val.movementType === 'Inbound') {
    val.vehicles?.forEach((v, i) => {
      if (!v.containerNo?.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['vehicles', i, 'containerNo'],
          message: 'Container no. is required for import FOB',
        })
      }
    })
  }
})

export const DRAFT_DEFAULT_VALUES: TruckingDraft = {
  movementType: 'Outbound',
  source: 'manual',
  sourceRef: undefined,
  takenAt: undefined,
  takenSnapshot: [],
  executionDate: '',
  transporterName: '',
  shiftingType: 'Regular',
  items: [emptyTruckItem()],
  itemDetails: '',
  pickup: '',
  destination: '',
  referenceNo: '',
  vehicles: [emptyVehicle()],
  quotedFreight: 0,
  actualFreight: 0,
  paymentStatus: 'Customer to pay',
  paidAmount: 0,
  detention: 0,
  dispatchNoteDate: '',
  etaWorks: '',
  remarks: '',
  systemRemarks: '',
}

export interface WizardStepDef {
  step: number
  key: string
  label: string
  fields: (keyof TruckingDraft)[]
}

// Four steps: Movement+Item, Vehicles, Freight/Payment, Tracking.
export const WIZARD_STEPS: WizardStepDef[] = [
  {
    step: 1,
    key: 'movement',
    label: 'Movement & Item',
    fields: [
      'movementType', 'executionDate', 'transporterName', 'shiftingType',
      'items', 'itemDetails', 'pickup', 'destination', 'referenceNo',
    ],
  },
  { step: 2, key: 'vehicles', label: 'Vehicles', fields: ['vehicles'] },
  {
    step: 3,
    key: 'freight',
    label: 'Freight & Payment',
    fields: ['quotedFreight', 'actualFreight', 'paymentStatus', 'paidAmount', 'detention'],
  },
  { step: 4, key: 'tracking', label: 'Tracking', fields: ['dispatchNoteDate', 'etaWorks', 'remarks'] },
]

// --- Derived-value helpers (calculated, never keyed in) --------------------

/** Quoted − actual. Null if either is missing. */
export function freightSavings(quoted?: number, actual?: number): number | null {
  if (quoted == null || actual == null) return null
  return quoted - actual
}

/** Actual freight per kg of total gross weight. Null if either is missing/zero. */
export function ratePerKg(actualFreight?: number, totalGrossWeight?: number): number | null {
  if (!actualFreight || !totalGrossWeight) return null
  return actualFreight / totalGrossWeight
}

export function totalGrossWeight(vehicles?: Vehicle[]): number {
  return (vehicles ?? []).reduce((s, v) => s + (Number(v.grossWeight) || 0), 0)
}

export function totalNetWeight(vehicles?: Vehicle[]): number {
  return (vehicles ?? []).reduce((s, v) => s + (Number(v.netWeight) || 0), 0)
}

export function vehicleCount(vehicles?: Vehicle[]): number {
  return (vehicles ?? []).length
}

/** Outstanding = (total freight to collect) − paid. Uses actual freight as the billable base. */
export function outstanding(actualFreight?: number, paidAmount?: number): number | null {
  if (actualFreight == null) return null
  return actualFreight - (paidAmount ?? 0)
}

/** Which vehicle (index) a given package id is riding on, if any — package→
 *  vehicle is intentionally not required to be 1:1 (a package may fill a
 *  whole vehicle, or ride alongside others), but each package should only be
 *  assigned once; this reports the first match. */
export function vehicleIndexForPackage(vehicles: Vehicle[], packageId: string): number | null {
  const idx = vehicles.findIndex((v) => v.packageRefs?.some((r) => r.packageId === packageId))
  return idx === -1 ? null : idx
}

/** Every package id already assigned to some vehicle, across the whole job —
 *  used to compute which of the taken snapshot's packages are still
 *  unassigned to any vehicle. */
export function assignedPackageIds(vehicles: Vehicle[]): Set<string> {
  const out = new Set<string>()
  for (const v of vehicles) for (const r of v.packageRefs ?? []) out.add(r.packageId)
  return out
}

/**
 * Consignment-level tracking rollup over the vehicles: BOTH the delivered
 * fraction and the slowest (least-advanced) stage present, e.g.
 * "3/5 delivered · Loading". Returns structured parts plus a ready label.
 */
export interface TrackingRollup {
  total: number
  delivered: number
  slowestStage: VehicleTrackingStatus | null
  label: string
}

export function trackingRollup(vehicles?: Vehicle[]): TrackingRollup {
  const list = vehicles ?? []
  const total = list.length
  const delivered = list.filter((v) => v.trackingStatus === 'Delivered').length
  let slowest: VehicleTrackingStatus | null = null
  if (total > 0) {
    // Lowest index in the ordered pipeline = least advanced.
    const idx = Math.min(
      ...list.map((v) =>
        v.trackingStatus ? VEHICLE_TRACKING_STATUSES.indexOf(v.trackingStatus) : 0,
      ),
    )
    slowest = VEHICLE_TRACKING_STATUSES[idx] ?? null
  }
  const label =
    total === 0
      ? 'No vehicles'
      : `${delivered}/${total} delivered${slowest && delivered < total ? ` · ${slowest}` : ''}`
  return { total, delivered, slowestStage: slowest, label }
}

/** Pickup/destination are factory dropdowns only for intrafactory movements. */
export function usesFactoryDropdowns(movementType: MovementType): boolean {
  return movementType === 'Intrafactory'
}

/** Shipment reference / IDM applies to outbound + inbound only. */
export function usesReferenceNo(movementType: MovementType): boolean {
  return movementType !== 'Intrafactory'
}

/** Container fields apply to inbound (import FOB) only. */
export function usesContainers(movementType: MovementType): boolean {
  return movementType === 'Inbound'
}

/* ------------------------------------------------------------------ */
/* What still blocks Submit                                            */
/* ------------------------------------------------------------------ */

/**
 * Outstanding submission requirements, attributed to the step that owns each
 * field — drives the wizard's requirements banner and the disabled Submit.
 *
 * MIRRORS app/trucking/helpers.py::submission_errors.
 *
 *
 * !! THE FRONTEND AND BACKEND DISAGREE ABOUT ONE FIELD, AND IT IS FLAGGED
 * !! RATHER THAN QUIETLY SETTLED HERE.
 *
 * truckingSubmitSchema above says, in as many words:
 *
 *     // Shipment reference / IDM is OPTIONAL (confirmed) — no required validation.
 *
 * The backend says the opposite:
 *
 *     if movement_type and movement_type != "Intrafactory":
 *         if not reference_no: "Shipment reference / IDM is required for
 *                               outbound and inbound movements"
 *
 * Verified against the real function: Outbound and Inbound both return that
 * error with reference_no empty; Intrafactory and a NULL movement type do
 * not. The wizard DEFAULTS to Outbound, so this is not a corner case — it is
 * the ordinary path, and today it ends in a 422 after the user hits Submit.
 *
 * This list follows the BACKEND, because its purpose is to predict what will
 * actually be refused: naming the requirement up front is strictly better
 * than a 422 after the fact, whichever side eventually turns out to be right.
 * Neither rule has been changed. If the field really is optional, the fix
 * belongs in submission_errors() and is a per-field decision, not something
 * to settle in a banner.
 */
export function submitRequirements(
  d: z.input<typeof truckingDraftSchema>,
): SubmitRequirement[] {
  const out: SubmitRequirement[] = []

  const at = (step: number) => {
    const def = WIZARD_STEPS.find((s) => s.step === step)
    return { step, stepLabel: def?.label ?? `Step ${step}` }
  }

  const need = (step: number, message: string) => out.push({ message, ...at(step) })

  // --- Step 1: Movement & Item --- (see the disagreement noted above)
  if (d.movementType && d.movementType !== 'Intrafactory' && !d.referenceNo?.trim()) {
    need(1, 'Shipment reference / IDM is required for outbound and inbound movements')
  }

  // --- Step 2: Vehicles ---
  const vehicles = (d.vehicles ?? []).filter(Boolean)
  if (vehicles.length === 0) need(2, 'At least one vehicle is required')

  if (d.movementType === 'Inbound') {
    vehicles.forEach((v, i) => {
      if (!v.containerNo?.trim()) {
        need(2, `Vehicle ${i + 1}: container no. is required for import FOB`)
      }
    })
  }

  return out
}
