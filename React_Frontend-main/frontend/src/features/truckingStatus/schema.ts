import { z } from 'zod'

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

export const SHIFTING_TYPES = ['Regular', 'Special', 'Others'] as const

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

export const vehicleSchema = z.object({
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
})
export type Vehicle = z.infer<typeof vehicleSchema>

export function emptyVehicle(): Vehicle {
  return {
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
  if (val.movementType !== 'Intrafactory' && !val.referenceNo?.trim()) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['referenceNo'],
      message: 'Shipment reference / IDM is required for outbound and inbound movements',
    })
  }
  if (!val.vehicles?.length) {
    ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['vehicles'], message: 'At least one vehicle is required' })
  }
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
      'itemDetails', 'pickup', 'destination', 'referenceNo',
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
