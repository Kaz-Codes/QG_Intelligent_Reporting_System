import { z } from 'zod'

/**
 * Logistics Status schema — step layout (5 steps):
 *   1. Order Details — header (department, order type, origin, customer, MO no.,
 *      batch no., incoterm) + item lines (simplified: no IDM/exportNo/batchNo)
 *   2. Packing       — multi-package with item-quantity allocation (including
 *                      cross-batch references within the same MO group)
 *   3. Shipping      — ports, containers, sailing dates
 *   4. Expenditures  — cost lines including container detention
 *   5. Status        — pipeline status, marketing delay, remarks feed, trucking handoff
 *
 * KEY CONCEPTS:
 *
 * DEPARTMENT (Cement / Sugar / General) is on the header and drives the merged
 * "Order Type" display in the list (e.g. "Cement Export", "General Local").
 *
 * BATCH SYSTEM: MO number is a grouping key, not a unique order ID. When
 * someone enters an MO that already exists, the system auto-creates it as
 * Batch 2 (etc.). Each batch has its own shipping/packing/expenditures/status.
 * batchNo is auto-generated but user-renameable. Batches within the same MO
 * can cross-reference each other's items in their package allocations — items
 * are SHARED (pull/reference), never copied.
 *
 * ITEM LINES are simplified: no IDM, export number, or batch number (those
 * belonged to the old design). Items carry Job#, item detail, quantity, unit
 * weight (input), gross weight (input), and RFD dates with audit trail.
 * Net weight = quantity × unitWeight, always derived.
 *
 * TRANSPORTATION is not a Logistics step. Orders hand off to Trucking via
 * "Send to Trucking" on Step 5; Logistics shows a read-through of trucking
 * progress afterward.
 */

export const ORDER_TYPES = ['Export', 'Local'] as const
export type OrderType = (typeof ORDER_TYPES)[number]

export const DEPARTMENTS = ['Cement', 'Sugar', 'General'] as const
export type Department = (typeof DEPARTMENTS)[number]

export const INCOTERMS = ['FOB', 'CIF', 'CFR', 'EXW', 'DAP'] as const
export type Incoterm = (typeof INCOTERMS)[number]

/** Number inputs hand back '' when cleared — treat that as absent, not 0. */
const optionalNumber = z.preprocess(
  (v) => (v === '' || v === null || Number.isNaN(v) ? undefined : v),
  z.coerce.number().nonnegative().optional(),
)

// --- Per-item RFD change audit ---------------------------------------------

export const rfdChangeEventSchema = z.object({
  id: z.string(),
  field: z.enum(['plannedRfdDate', 'actualRfdDate']),
  previousValue: z.string().optional(),
  newValue: z.string(),
  changedBy: z.string(),
  changedAt: z.string(),
  remark: z.string().optional(),
})
export type RfdChangeEvent = z.infer<typeof rfdChangeEventSchema>

// --- Step 1: Order item lines (simplified) ---------------------------------

/**
 * One line per item. Simplified from the previous version: IDM, export number,
 * and batch number are removed. Net weight is DERIVED (quantity × unitWeight),
 * never a direct input. Gross weight is not tracked per item — it belongs to
 * packages (see totalPackageGrossWeight), since a package's gross weight
 * includes packaging materials, not just the raw item weight.
 */
export const logisticsItemSchema = z.object({
  id: z.string(),
  jobNo: z.string().default(''),
  itemDetail: z.string().default(''),
  quantity: optionalNumber,
  unitWeight: optionalNumber,
  plannedRfdDate: z.string().optional(),
  actualRfdDate: z.string().optional(),
  rfdHistory: z.array(rfdChangeEventSchema).default([]),
})
export type LogisticsItem = z.infer<typeof logisticsItemSchema>

export const emptyItem = (id: string): LogisticsItem => ({
  id, jobNo: '', itemDetail: '', quantity: undefined, unitWeight: undefined,
  plannedRfdDate: '', actualRfdDate: '', rfdHistory: [],
})

// --- Step 1: Order details --------------------------------------------------
export const consignmentSchema = z
  .object({
    orderType: z.enum(ORDER_TYPES),
    department: z.enum(DEPARTMENTS),
    originCountry: z.string().optional(),
    originCity: z.string().optional(),
    originProvince: z.string().optional(),
    customerName: z.string().min(1, 'Customer name is required'),
    moNo: z.string().optional(),
    /** Auto-generated when the same MO number already exists in the system —
     *  first order with an MO = Batch 1, second = Batch 2, etc. User can
     *  rename the label but not the underlying sequence. */
    batchNo: z.number().int().min(1).default(1),
    batchLabel: z.string().optional(), // user-renameable display label, defaults to "Batch {batchNo}"
    incoterm: z.enum(INCOTERMS).optional().or(z.literal('')),
    items: z.array(logisticsItemSchema).default([]),
  })
  .superRefine((val, ctx) => {
    if (val.orderType === 'Export') {
      if (!val.originCountry?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['originCountry'], message: 'Country of origin is required for exports' })
      }
    } else {
      if (!val.originCity?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['originCity'], message: 'City is required for local orders' })
      }
      if (!val.originProvince?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['originProvince'], message: 'Province is required for local orders' })
      }
    }
    if (val.items.length === 0) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['items'], message: 'Add at least one item' })
    }
    val.items.forEach((item, i) => {
      if (!item.itemDetail) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['items', i, 'itemDetail'], message: 'Item detail is required' })
      }
      if (item.quantity === undefined || item.quantity <= 0) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['items', i, 'quantity'], message: 'Quantity must be greater than 0' })
      }
    })
  })

// --- Step 2: Packing --------------------------------------------------------

export const PACKING_STATUSES = [
  'Packing under manufacturing',
  'Under Packing',
  'Under Paint',
  'Under Final Packing',
  'Packed',
] as const
export type PackingStatus = (typeof PACKING_STATUSES)[number]

/**
 * One allocation of an item's quantity into a package. Supports CROSS-BATCH
 * references: a package in Batch 2 can allocate items that belong to Batch 1
 * within the same MO group — the items are shared, not copied.
 *
 * When sourceOrderId equals the current order's own systemId, the item is
 * local. When it differs, it's a cross-batch reference to a sibling batch's
 * item under the same MO.
 */
export const packageAllocationSchema = z.object({
  id: z.string(),
  itemId: z.string(),
  /** The order (batch) that owns this item. Same as this order's id for local
   *  items; a different order's id for cross-batch references. */
  sourceOrderId: z.string(),
  quantity: optionalNumber,
})
export type PackageAllocation = z.infer<typeof packageAllocationSchema>

export const logisticsPackageSchema = z.object({
  id: z.string(),
  colourCode: z.string().optional(),
  packingWorks: z.string().optional(),
  packingReadyDate: z.string().optional(),
  packingDate: z.string().optional(),
  quotedPackingCost: optionalNumber,
  actualPackingCost: optionalNumber,
  grossWeight: optionalNumber,
  status: z.enum(PACKING_STATUSES).default('Packing under manufacturing'),
  allocations: z.array(packageAllocationSchema).default([]),
})
export type LogisticsPackage = z.infer<typeof logisticsPackageSchema>

export const emptyPackage = (id: string): LogisticsPackage => ({
  id, colourCode: '', packingWorks: '', packingReadyDate: '', packingDate: '',
  quotedPackingCost: undefined, actualPackingCost: undefined, grossWeight: undefined,
  status: 'Packing under manufacturing', allocations: [],
})

export const packingSchema = z.object({
  packages: z.array(logisticsPackageSchema).default([]),
})

// --- Step 3: Shipping --------------------------------------------------------

export const logisticsContainerSchema = z.object({
  id: z.string(),
  containerNo: z.string().optional(),
  containerType: z.string().default(''),
})
export type LogisticsContainer = z.infer<typeof logisticsContainerSchema>

export const emptyContainer = (id: string): LogisticsContainer => ({ id, containerNo: '', containerType: '' })

export const shippingSchema = z.object({
  containers: z.array(logisticsContainerSchema).default([]),
  pol: z.string().optional(),
  pod: z.string().optional(),
  shippingLine: z.string().optional(),
  clearingAgent: z.string().optional(),
  bookingNo: z.string().optional(),
  portInDate: z.string().optional(),
  etdSailingDate: z.string().optional(),
  croArrivalDate: z.string().optional(),
  actualArrivalDate: z.string().optional(),
})

// --- Step 4: Expenditures ----------------------------------------------------

export const expendituresSchema = z.object({
  // Shared
  packingCost: z.number().min(0).optional(),
  transportationCharges: z.number().min(0).optional(),
  /** Container detention cost — applies to any order with containers. */
  containerDetention: z.number().min(0).optional(),
  // Export-only
  insurance: z.number().min(0).optional(),
  truckingLhrToKhi: z.number().min(0).optional(),
  fumigationCost: z.number().min(0).optional(),
  lashing: z.number().min(0).optional(),
  qflCharges: z.number().min(0).optional(),
  qflContainerMovement: z.number().min(0).optional(),
  customClearanceCharges: z.number().min(0).optional(),
  portCharges: z.number().min(0).optional(),
  dhlCharges: z.number().min(0).optional(),
  seaAirFreight: z.number().min(0).optional(),
})

// --- Step 5: Status ----------------------------------------------------------

export const remarkEntrySchema = z.object({
  id: z.string(),
  text: z.string(),
  authoredBy: z.string(),
  authoredAt: z.string(),
  system: z.boolean().default(false),
})
export type RemarkEntry = z.infer<typeof remarkEntrySchema>

export const statusSchema = z.object({
  status: z.string().min(1, 'Status is required'),
  remarksLog: z.array(remarkEntrySchema).default([]),
  gateOutDate: z.string().optional(),
  sentToTrucking: z.boolean().default(false),
})

export interface TruckingReadthrough {
  truckingJobId: string
  transporterName?: string
  vehicleCount: number
  trackingRollupLabel: string
  taken: boolean
}

// --- Draft schema (flat for react-hook-form) ---------------------------------

export const consignmentDraftSchema = z
  .object({
    orderType: z.enum(ORDER_TYPES),
    department: z.enum(DEPARTMENTS),
    originCountry: z.string().optional(),
    originCity: z.string().optional(),
    originProvince: z.string().optional(),
    customerName: z.string().min(1, 'Customer name is required'),
    moNo: z.string().optional(),
    batchNo: z.number().int().min(1).default(1),
    batchLabel: z.string().optional(),
    incoterm: z.enum(INCOTERMS).optional().or(z.literal('')),
    items: z.array(logisticsItemSchema).default([]),
  })
  .merge(packingSchema)
  .merge(shippingSchema)
  .merge(expendituresSchema)
  .merge(statusSchema)

export type LogisticsDraft = z.infer<typeof consignmentDraftSchema>

export const DRAFT_DEFAULT_VALUES: LogisticsDraft = {
  orderType: 'Export',
  department: 'General',
  originCountry: '',
  originCity: '',
  originProvince: '',
  customerName: '',
  moNo: '',
  batchNo: 1,
  batchLabel: '',
  incoterm: undefined,
  items: [emptyItem('item-1')],
  packages: [],
  containers: [],
  pol: '',
  pod: '',
  shippingLine: '',
  clearingAgent: '',
  bookingNo: '',
  portInDate: '',
  etdSailingDate: '',
  croArrivalDate: '',
  actualArrivalDate: '',
  packingCost: 0,
  transportationCharges: 0,
  containerDetention: 0,
  insurance: 0,
  truckingLhrToKhi: 0,
  fumigationCost: 0,
  lashing: 0,
  qflCharges: 0,
  qflContainerMovement: 0,
  customClearanceCharges: 0,
  portCharges: 0,
  dhlCharges: 0,
  seaAirFreight: 0,
  status: '',
  remarksLog: [],
  gateOutDate: '',
  sentToTrucking: false,
}

export interface WizardStepDef {
  step: number
  key: string
  label: string
  fields: (keyof LogisticsDraft)[]
}

export const WIZARD_STEPS: WizardStepDef[] = [
  {
    step: 1,
    key: 'order',
    label: 'Order Details',
    fields: ['orderType', 'department', 'originCountry', 'originCity', 'originProvince',
      'customerName', 'moNo', 'batchNo', 'batchLabel', 'incoterm', 'items'],
  },
  { step: 2, key: 'packing', label: 'Packing', fields: ['packages'] },
  {
    step: 3,
    key: 'shipping',
    label: 'Shipping',
    fields: ['containers', 'pol', 'pod', 'shippingLine', 'clearingAgent',
      'bookingNo', 'portInDate', 'etdSailingDate', 'croArrivalDate', 'actualArrivalDate'],
  },
  {
    step: 4,
    key: 'expenditures',
    label: 'Expenditures',
    fields: ['packingCost', 'transportationCharges', 'containerDetention', 'insurance',
      'truckingLhrToKhi', 'fumigationCost', 'lashing', 'qflCharges', 'qflContainerMovement',
      'customClearanceCharges', 'portCharges', 'dhlCharges', 'seaAirFreight'],
  },
  { step: 5, key: 'status', label: 'Status', fields: ['status', 'remarksLog', 'gateOutDate', 'sentToTrucking'] },
]

// --- Status choices ----------------------------------------------------------

export const EXPORT_STATUSES = [
  'Under Production',
  'Under Packing',
  'Transportation',
  'Under Shipping Arrangement',
  'At QFL',
  'At Port',
  'On Water',
  'Delivered',
] as const

export const LOCAL_STATUSES = [
  'Under Production',
  'Under Packing',
  'Transportation',
  'Delivered',
] as const

export function statusesFor(orderType: OrderType): readonly string[] {
  return orderType === 'Export' ? EXPORT_STATUSES : LOCAL_STATUSES
}

// --- Derived-value helpers ---------------------------------------------------

export function daysBetween(fromISO?: string, toISO?: string): number | null {
  if (!fromISO || !toISO) return null
  const a = new Date(fromISO).getTime()
  const b = new Date(toISO).getTime()
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  return Math.round((b - a) / 86_400_000)
}

/**
 * Arrival delay in days: how late the goods actually arrived versus the CRO
 * (planned) arrival. Positive = late, negative = early, null when either date
 * is missing so "no data" and "on time" stay visually distinct. Uses actual
 * arrival where known; falls back to today for an in-flight estimate so a
 * shipment already past its planned date shows as slipping, not blank.
 */
export function arrivalDelayDays(o: { croArrivalDate?: string; actualArrivalDate?: string }): number | null {
  if (!o.croArrivalDate) return null
  const end = o.actualArrivalDate || new Date().toISOString().slice(0, 10)
  return daysBetween(o.croArrivalDate, end)
}

/** Net weight for one item — DERIVED, quantity × unitWeight. */
export function itemNetWeight(item: Pick<LogisticsItem, 'quantity' | 'unitWeight'>): number {
  return (item.quantity ?? 0) * (item.unitWeight ?? 0)
}

export const totalQuantity = (items: LogisticsItem[]) =>
  items.reduce((s, it) => s + (it.quantity ?? 0), 0)

export const totalNetWeight = (items: LogisticsItem[]) =>
  items.reduce((s, it) => s + itemNetWeight(it), 0)

/** Merged order type label for the list: "Cement Export", "General Local", etc. */
export function orderTypeLabel(department: Department, orderType: OrderType): string {
  return `${department} ${orderType}`
}

/** All job numbers across items, used for the "visible on hover" list column. */
export const jobNumbers = (items: LogisticsItem[]) =>
  items.map((it) => it.jobNo).filter((j) => !!j)

/** Latest planned RFD across an order's items (max date). Null if none set. */
export const latestPlannedRfd = (items: LogisticsItem[]): string | null => {
  const ds = items.map((it) => it.plannedRfdDate).filter((d): d is string => !!d)
  return ds.length ? ds.reduce((a, b) => (a > b ? a : b)) : null
}

/** Latest ACTUAL RFD across an order's items — the real ready-for-dispatch
 *  date, as distinct from the planned one. Null until at least one item has
 *  actually been readied. */
export const latestActualRfd = (items: LogisticsItem[]): string | null => {
  const ds = items.map((it) => it.actualRfdDate).filter((d): d is string => !!d)
  return ds.length ? ds.reduce((a, b) => (a > b ? a : b)) : null
}

export function itemPendingFields(item: LogisticsItem): string[] {
  const out: string[] = []
  if (!item.itemDetail) out.push('Item detail')
  if (item.quantity === undefined) out.push('Quantity')
  return out
}

/** Display label for a batch, falling back to "Batch N". */
export function batchDisplayLabel(batchNo: number, batchLabel?: string): string {
  return batchLabel?.trim() || `Batch ${batchNo}`
}

/**
 * Given an MO number and the full list of orders in the system, returns the
 * next batch number for a new order under that MO. Returns 1 if the MO
 * doesn't exist yet. Used at creation time to auto-assign batchNo.
 */
export function nextBatchNo(moNo: string, existingOrders: { moNo?: string; batchNo: number }[]): number {
  if (!moNo) return 1
  const siblings = existingOrders.filter((o) => o.moNo === moNo)
  if (siblings.length === 0) return 1
  return Math.max(...siblings.map((o) => o.batchNo)) + 1
}

/**
 * Returns all items available for cross-batch allocation within the same MO
 * group — items from sibling batches that share this order's MO number.
 * Each item is returned with its source order id so the allocation can
 * correctly reference the owner.
 */
export interface CrossBatchItem {
  sourceOrderId: string
  sourceBatchLabel: string
  item: LogisticsItem
}
// The implementation of getCrossBatchItems lives in the data layer
// (logisticsStatusData.ts) since it requires scanning the order store;
// this interface defines the shape it returns so the Packing step can
// type its props without importing the data module.

export function marketingDelay(packages: LogisticsPackage[], gateOutDate?: string): number | null {
  const packingDates = packages.map((p) => p.packingDate).filter((d): d is string => !!d)
  if (packingDates.length === 0) return null
  const latest = packingDates.reduce((a, b) => (a > b ? a : b))
  const reference = gateOutDate || new Date().toISOString().slice(0, 10)
  return daysBetween(reference, latest)
}

export function packingDelay(pkg: LogisticsPackage, items: LogisticsItem[]): number | null {
  if (!pkg.packingDate || pkg.allocations.length === 0) return null
  const firstItem = items.find((it) => it.id === pkg.allocations[0].itemId)
  const rfd = firstItem?.plannedRfdDate || firstItem?.actualRfdDate
  if (!rfd) return null
  return daysBetween(pkg.packingDate, rfd)
}

export function packingSavings(pkg: LogisticsPackage): number | null {
  if (pkg.quotedPackingCost == null || pkg.actualPackingCost == null) return null
  return pkg.quotedPackingCost - pkg.actualPackingCost
}

/** Quantity of one item allocated across ALL packages (local and cross-batch). */
export function allocatedQuantity(itemId: string, packages: LogisticsPackage[]): number {
  return packages.reduce(
    (sum, pkg) => sum + pkg.allocations
      .filter((a) => a.itemId === itemId)
      .reduce((s, a) => s + (a.quantity ?? 0), 0),
    0,
  )
}

export function outstandingQuantity(item: LogisticsItem, packages: LogisticsPackage[]): number {
  return (item.quantity ?? 0) - allocatedQuantity(item.id, packages)
}

export function outstandingByItem(items: LogisticsItem[], packages: LogisticsPackage[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const item of items) out[item.id] = outstandingQuantity(item, packages)
  return out
}

/** Total gross weight across all packages (for the Packing step footer). */
export function totalPackageGrossWeight(packages: LogisticsPackage[]): number {
  return packages.reduce((s, p) => s + (p.grossWeight ?? 0), 0)
}

/** Total net weight across all packages, computed from allocated item quantities × unit weights.
 *  Requires resolving cross-batch items too; the allItems param should include both
 *  local and cross-batch items to get the right unit weight. */
export function totalPackageNetWeight(packages: LogisticsPackage[], allItems: LogisticsItem[]): number {
  let total = 0
  for (const pkg of packages) {
    for (const alloc of pkg.allocations) {
      const item = allItems.find((it) => it.id === alloc.itemId)
      if (item) total += (alloc.quantity ?? 0) * (item.unitWeight ?? 0)
    }
  }
  return total
}

// --- RFD audit helpers -------------------------------------------------------

export function recordRfdChange(
  item: LogisticsItem,
  field: 'plannedRfdDate' | 'actualRfdDate',
  newValue: string,
  changedBy: string,
): LogisticsItem {
  const previousValue = item[field]
  if (previousValue === newValue) return item
  const event: RfdChangeEvent = {
    id: `rfd-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    field,
    previousValue,
    newValue,
    changedBy,
    changedAt: new Date().toISOString(),
  }
  return { ...item, [field]: newValue, rfdHistory: [...item.rfdHistory, event] }
}

export function formatRfdEvent(event: RfdChangeEvent, itemLabel: string): string {
  const fieldLabel = event.field === 'plannedRfdDate' ? 'Planned RFD' : 'Actual RFD'
  const from = event.previousValue || 'not set'
  const when = new Date(event.changedAt).toLocaleString()
  return `${itemLabel}: ${fieldLabel} changed from ${from} to ${event.newValue} by ${event.changedBy} on ${when}`
}

export function buildRemarksFeed(items: LogisticsItem[], remarksLog: RemarkEntry[]): RemarkEntry[] {
  const systemEntries: RemarkEntry[] = items.flatMap((item, i) =>
    item.rfdHistory.map((event) => ({
      id: event.id,
      text: formatRfdEvent(event, item.itemDetail || `Item ${i + 1}`),
      authoredBy: event.changedBy,
      authoredAt: event.changedAt,
      system: true,
    })),
  )
  return [...remarksLog, ...systemEntries].sort((a, b) => a.authoredAt.localeCompare(b.authoredAt))
}

export function canEditRemark(userRole: string): boolean {
  return userRole === 'admin'
}
