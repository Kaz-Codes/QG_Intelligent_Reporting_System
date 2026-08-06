import {
  ORDER_TYPES,
  DEPARTMENTS,
  INCOTERMS,
  PACKING_STATUSES,
  statusesFor,
  recordRfdChange,
  nextBatchNo,
  batchDisplayLabel,
  outstandingByItem,
  type LogisticsDraft,
  type LogisticsItem,
  type LogisticsContainer,
  type LogisticsPackage,
  type RfdChangeEvent,
  type RemarkEntry,
  type OrderType,
  type Department,
  type CrossBatchItem,
} from '@/features/logisticsStatus/schema'
import { QG_FACTORIES } from '@/features/truckingStatus/schema'
// Cross-module: FOB imports need Logistics to arrange the sea freight and
// clearing agent, so they surface here as read-only open requests — the
// mirror of what Trucking does for the same consignments (see
// lib/truckingStatusData.ts deriveFromImportsFob).
import * as importsData from '@/lib/importsStatusData'
import { CONSIGNMENT_STATUSES } from '@/features/importsStatus/schema'

/**
 * Logistics Status mock data.
 *
 * Matches the house style of lib/importsStatusData.ts — a module-level array
 * built once with a seeded RNG for determinism, a *Filters interface, and a
 * get*() that filters it. Unlike Imports Status, `LogisticsDraft` (the
 * wizard's form schema) is already flat, so there's no separate "row" shape
 * to bridge: a mock order IS a `LogisticsDraft` plus its `systemId`, and it's
 * exactly what the wizard's `defaultValues` needs in edit mode.
 *
 * Replaced wholesale once the real API lands.
 */

function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const rng = mulberry32(77)
const randInt = (lo: number, hi: number) => lo + Math.floor(rng() * (hi - lo + 1))
const pick = <T>(arr: readonly T[]): T => arr[Math.floor(rng() * arr.length)]
const iso = (d: Date) => d.toISOString().slice(0, 10)
const addDays = (from: string, n: number) => iso(new Date(+new Date(from) + n * 86_400_000))

export const CUSTOMERS = [
  'Al Futtaim Trading LLC', 'Nordic Cargo Partners', 'Kansai Steel Traders',
  'Meridian Export House', 'Anatolia Machinery Import', 'Prime Freight Solutions',
  'Lahore Textile Mills', 'Karachi Engineering Works', 'Faisalabad Weaving Co.',
] as const
const CATALOGUE = [
  'Cotton yarn — 30s combed', 'Surgical instruments — assorted', 'Auto parts — brake assemblies',
  'Sports goods — footballs', 'Leather goods — finished hides', 'Cutlery — stainless steel sets',
  'Rice — Basmati 1121', 'Textile machinery spares', 'Cement bags — 50kg', 'Refined sugar — 50kg bags',
] as const
const COUNTRIES = ['United Arab Emirates', 'Germany', 'United Kingdom', 'Türkiye', 'Japan', 'United States'] as const
const CITIES: Record<string, string> = {
  Punjab: 'Lahore', Sindh: 'Karachi', 'Khyber Pakhtunkhwa': 'Peshawar',
}
const PROVINCES = ['Punjab', 'Sindh', 'Khyber Pakhtunkhwa'] as const
const SHIPPING_LINES = ['Maersk', 'MSC', 'CMA CGM', 'Hapag-Lloyd'] as const
const CONTAINER_TYPES = ["20' Dry", "40' Dry", "40' High Cube"] as const
const CLEARING_AGENTS = ['Prime Cargo Services', 'Indus Clearing Co.', 'Sea Link Logistics'] as const
const DESTINATIONS = ['Jebel Ali, UAE', 'Hamburg, Germany', 'Felixstowe, UK', 'Mersin, Türkiye', 'Yokohama, Japan'] as const
const STAFF = ['Usman Tariq', 'Ayesha Khan', 'Bilal Ahmed', 'Hina Farooq'] as const
const REMARK_TEXTS = [
  'Customer confirmed final artwork.',
  'Awaiting fabric dyeing lot approval.',
  'Packing schedule moved up a week.',
  'Container booking confirmed with shipping line.',
  'Buyer requested revised carton markings.',
] as const

export interface LogisticsOrder extends LogisticsDraft {
  systemId: string
}

/** ~40% of items get a seeded RFD change so the audit trail has something to
 *  show out of the box, without needing to edit a record first. */
function makeRfdHistory(itemKey: string): RfdChangeEvent[] {
  if (rng() > 0.4) return []
  const count = randInt(1, 2)
  const events: RfdChangeEvent[] = []
  let prev: string | undefined
  let cursor = addDays('2026-03-01', randInt(0, 60))
  for (let e = 0; e < count; e++) {
    const newValue = addDays(cursor, randInt(3, 15))
    events.push({
      id: `rfd-seed-${itemKey}-${e}`,
      field: 'plannedRfdDate',
      previousValue: prev,
      newValue,
      changedBy: pick(STAFF),
      changedAt: `${cursor}T09:00:00.000Z`,
      remark: rng() > 0.6 ? 'Adjusted per factory update.' : undefined,
    })
    prev = newValue
    cursor = newValue
  }
  return events
}

/** Items are simplified — no IDM, export number, or batch number (those
 *  concepts moved to the order-level MO/batch system). */
function makeItems(orderKey: string): LogisticsItem[] {
  const lineCount = randInt(1, 3)
  return Array.from({ length: lineCount }, (_, n) => {
    const unitWeight = randInt(2, 40)
    const itemKey = `${orderKey}-${n}`
    return {
      id: `item-${itemKey}`,
      jobNo: rng() > 0.2 ? `JOB-${randInt(1000, 9999)}` : '',
      itemDetail: pick(CATALOGUE),
      quantity: randInt(50, 5000),
      unitWeight,
      plannedRfdDate: rng() > 0.15 ? addDays('2026-04-01', randInt(0, 90)) : '',
      actualRfdDate: rng() > 0.5 ? addDays('2026-04-10', randInt(0, 95)) : '',
      rfdHistory: makeRfdHistory(itemKey),
    }
  })
}

/** 1-3 packages per order, each carrying a partial allocation of the order's
 *  OWN items (local — cross-batch allocations are something a user creates
 *  interactively via the Packing step's cross-batch section, not seeded).
 *  Roughly half of every item's quantity ends up fully allocated, half left
 *  with a real outstanding remainder, so the outstanding-quantity summary has
 *  genuine examples of both. */
function makePackages(orderKey: string, systemId: string, items: LogisticsItem[], stageIndex: number): LogisticsPackage[] {
  if (stageIndex < 1 && rng() > 0.3) return [] // early-stage orders often have none yet
  const count = randInt(1, 3)
  const packages: LogisticsPackage[] = Array.from({ length: count }, (_, p) => ({
    id: `package-${orderKey}-${p}`,
    colourCode: rng() > 0.4 ? pick(['Red', 'Blue', 'Grey', 'Natural']) : '',
    packingWorks: pick(QG_FACTORIES),
    packingReadyDate: addDays('2026-04-01', randInt(0, 60)),
    packingDate: stageIndex >= 1 && rng() > 0.3 ? addDays('2026-04-05', randInt(0, 65)) : '',
    quotedPackingCost: randInt(2_000, 9_000),
    actualPackingCost: stageIndex >= 1 && rng() > 0.3 ? randInt(1_800, 9_500) : undefined,
    grossWeight: randInt(500, 8_000),
    status: pick(PACKING_STATUSES),
    allocations: [],
  }))

  items.forEach((item) => {
    if (item.quantity === undefined || item.quantity <= 0) return
    const fullyAllocate = rng() > 0.5
    let remaining = item.quantity
    const nTargets = randInt(1, Math.min(2, packages.length))
    const targets = [...packages].sort(() => rng() - 0.5).slice(0, nTargets)
    targets.forEach((pkg, idx) => {
      if (remaining <= 0) return
      const isLast = idx === targets.length - 1
      const portion = Math.min(
        remaining,
        isLast && fullyAllocate ? remaining : Math.max(1, Math.floor(remaining * (0.3 + rng() * 0.3))),
      )
      pkg.allocations.push({ id: `alloc-${pkg.id}-${item.id}`, itemId: item.id, sourceOrderId: systemId, quantity: portion })
      remaining -= portion
    })
  })

  return packages
}

function makeRemarksLog(orderKey: string): RemarkEntry[] {
  if (rng() > 0.5) return []
  const count = randInt(1, 2)
  return Array.from({ length: count }, (_, r) => ({
    id: `remark-seed-${orderKey}-${r}`,
    text: pick(REMARK_TEXTS),
    authoredBy: pick(STAFF),
    authoredAt: `${addDays('2026-04-01', randInt(0, 90))}T10:30:00.000Z`,
    system: false,
  }))
}

/**
 * BATCH SYSTEM SEED DATA: a handful of MO numbers are pre-assigned 2-3
 * batches each, so the list's MO-group accent and the Packing step's
 * cross-batch allocation section both have real sibling batches to show
 * without the user first creating them by hand. Remaining orders get either
 * a unique MO (batch 1 only) or no MO at all.
 */
const MO_GROUPS = [
  { moNo: 'MO-2026-1001', batches: 3 },
  { moNo: 'MO-2026-1002', batches: 2 },
  { moNo: 'MO-2026-1003', batches: 2 },
  { moNo: 'MO-2026-1004', batches: 3 },
] as const

interface OrderPlan {
  moNo?: string
  batchNo: number
}

function buildOrderPlans(total: number): OrderPlan[] {
  const plans: OrderPlan[] = []
  for (const g of MO_GROUPS) {
    for (let b = 1; b <= g.batches; b++) plans.push({ moNo: g.moNo, batchNo: b })
  }
  while (plans.length < total) {
    plans.push({ moNo: rng() > 0.5 ? `MO-2026-${randInt(2000, 2999)}` : undefined, batchNo: 1 })
  }
  return plans
}

function makeOrder(i: number, plan: OrderPlan): LogisticsOrder {
  const orderKey = String(240 - i)
  // MO-based id (see moBasedSystemId below) when the order has an MO number;
  // otherwise a deterministic sequential fallback, never a UUID.
  const systemId = moBasedSystemId(plan.moNo, plan.batchNo) ?? `LOG-2026-${orderKey.padStart(4, '0')}`
  const orderType: OrderType = pick(ORDER_TYPES)
  const department: Department = pick(DEPARTMENTS)
  const isExport = orderType === 'Export'
  const statuses = statusesFor(orderType)
  const status = pick(statuses)
  const stageIndex = statuses.indexOf(status)

  const items = makeItems(orderKey)
  const packages = makePackages(orderKey, systemId, items, stageIndex)

  const hasProgressed = stageIndex >= 2
  const gateOutDate = hasProgressed ? addDays('2026-04-01', randInt(20, 100)) : ''

  const province = pick(PROVINCES)
  const hasContainers = isExport && stageIndex >= 3
  const containers: LogisticsContainer[] = hasContainers
    ? Array.from({ length: randInt(1, 4) }, (_, n) => ({
        id: `container-${orderKey}-${n}`,
        containerType: pick(CONTAINER_TYPES),
        containerNo: rng() > 0.3 ? `MSKU${randInt(1000000, 9999999)}` : '',
      }))
    : []

  return {
    systemId,
    orderType,
    department,
    originCountry: isExport ? pick(COUNTRIES) : '',
    originCity: isExport ? '' : CITIES[province],
    originProvince: isExport ? '' : province,
    customerName: pick(CUSTOMERS),
    moNo: plan.moNo ?? '',
    batchNo: plan.batchNo,
    batchLabel: rng() > 0.7 ? `${department} run ${plan.batchNo}` : '',
    incoterm: rng() > 0.4 ? pick(INCOTERMS) : undefined,
    items,

    packages,

    containers,
    pol: isExport && stageIndex >= 3 ? 'Port Qasim, Karachi' : '',
    pod: isExport && stageIndex >= 3 ? pick(DESTINATIONS) : '',
    shippingLine: isExport && stageIndex >= 3 ? pick(SHIPPING_LINES) : '',
    clearingAgent: isExport && stageIndex >= 3 ? pick(CLEARING_AGENTS) : '',
    bookingNo: isExport && stageIndex >= 3 ? `BK-${randInt(10000, 99999)}` : '',
    portInDate: isExport && stageIndex >= 4 ? addDays(gateOutDate || '2026-05-01', randInt(1, 5)) : '',
    etdSailingDate: isExport && stageIndex >= 4 ? addDays(gateOutDate || '2026-05-01', randInt(3, 8)) : '',
    croArrivalDate: isExport && stageIndex >= 5 ? addDays(gateOutDate || '2026-05-01', randInt(20, 35)) : '',
    actualArrivalDate: isExport && stageIndex >= statuses.length - 1 ? addDays(gateOutDate || '2026-05-01', randInt(22, 40)) : '',

    packingCost: randInt(2_000, 15_000),
    transportationCharges: !isExport ? randInt(5_000, 25_000) : 0,
    containerDetention: hasContainers && rng() > 0.5 ? randInt(3_000, 20_000) : 0,
    insurance: isExport ? randInt(3_000, 12_000) : 0,
    truckingLhrToKhi: isExport ? randInt(8_000, 20_000) : 0,
    fumigationCost: isExport && rng() > 0.5 ? randInt(2_000, 6_000) : 0,
    lashing: isExport ? randInt(1_000, 4_000) : 0,
    qflCharges: isExport ? randInt(3_000, 9_000) : 0,
    qflContainerMovement: isExport ? randInt(2_000, 7_000) : 0,
    customClearanceCharges: isExport ? randInt(5_000, 18_000) : 0,
    portCharges: isExport ? randInt(4_000, 14_000) : 0,
    dhlCharges: rng() > 0.6 ? randInt(500, 3_000) : 0,
    seaAirFreight: isExport ? randInt(40_000, 220_000) : 0,

    status,
    remarksLog: makeRemarksLog(orderKey),
    gateOutDate,
    // ~60% of orders that have progressed past the early stages have already
    // been handed to Trucking, so Trucking Status's from-logistics feed has
    // real rows to show without the user first checking the box themselves.
    sentToTrucking: hasProgressed && rng() > 0.4,
  }
}

const ORDER_PLANS = buildOrderPlans(24)
const ALL: LogisticsOrder[] = ORDER_PLANS.map((plan, i) => makeOrder(i, plan))

/* -- filtering ------------------------------------------------------- */
export interface LogisticsFilters {
  search?: string
  orderType?: OrderType[]
  status?: string[]
  customer?: string[]
  /** Date-range filter against gateOutDate (Status step's field) — the most
   *  prominent chronological field this module has since Transportation was
   *  removed. */
  gateOutFrom?: string
  gateOutTo?: string
}

const inSet = <T extends string>(v: T, s?: T[]) => !s || s.length === 0 || s.includes(v)

export function getLogisticsOrders(f: LogisticsFilters = {}): LogisticsOrder[] {
  const q = (f.search ?? '').trim().toLowerCase()
  return ALL.filter((o) => {
    if (!inSet(o.orderType, f.orderType)) return false
    if (!inSet(o.status, f.status as string[] | undefined)) return false
    if (f.customer?.length && !f.customer.includes(o.customerName)) return false
    if (f.gateOutFrom && (!o.gateOutDate || o.gateOutDate < f.gateOutFrom)) return false
    if (f.gateOutTo && (!o.gateOutDate || o.gateOutDate > f.gateOutTo)) return false
    if (q) {
      const hay = [
        o.systemId, o.customerName, o.moNo ?? '', batchDisplayLabel(o.batchNo, o.batchLabel),
        ...o.items.map((it) => `${it.itemDetail} ${it.jobNo}`),
      ].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

export function usedContainerNumbers(excludeSystemId?: string): Set<string> {
  const norm = (s: string) => s.replace(/\s+/g, '').toUpperCase()
  const set = new Set<string>()
  for (const o of ALL) {
    if (excludeSystemId && o.systemId === excludeSystemId) continue
    for (const c of o.containers ?? []) {
      if (c.containerNo?.trim()) set.add(norm(c.containerNo))
    }
  }
  return set
}

/** True if `containerNo` is already used by another order. Case/space-insensitive. */
export function isContainerNumberTaken(containerNo: string, excludeSystemId?: string): boolean {
  const norm = containerNo.replace(/\s+/g, '').toUpperCase()
  if (!norm) return false
  return usedContainerNumbers(excludeSystemId).has(norm)
}

export const getLogisticsOrder = (systemId: string): LogisticsOrder | undefined =>
  ALL.find((o) => o.systemId === systemId)

/**
 * Every item available for cross-batch allocation within the same MO group —
 * items owned by sibling batches sharing this order's MO number. Scans the
 * order store since it needs visibility across records, not just this one.
 */
export function getCrossBatchItems(moNo: string, currentSystemId: string): CrossBatchItem[] {
  if (!moNo) return []
  return ALL
    .filter((o) => o.moNo === moNo && o.systemId !== currentSystemId)
    .flatMap((o) => o.items.map((item): CrossBatchItem => ({
      sourceOrderId: o.systemId,
      sourceBatchLabel: batchDisplayLabel(o.batchNo, o.batchLabel),
      item,
    })))
}

/** Next batch number for a given MO — 1 if the MO doesn't exist yet in the
 *  store, otherwise one past the highest existing batch under it. Used by
 *  the wizard when creating a new order to auto-assign batchNo. */
export function nextBatchNoForMo(moNo: string): number {
  return nextBatchNo(moNo, ALL.map((o) => ({ moNo: o.moNo, batchNo: o.batchNo })))
}

/**
 * The MO-based half of the system id rule: Batch 1 under an MO IS that MO
 * number; Batch 2+ appends "-B{batchNo}". Returns null when there's no MO
 * number, so callers fall back to a sequential id — never a UUID.
 */
function moBasedSystemId(moNo: string | undefined, batchNo: number): string | null {
  const trimmed = moNo?.trim()
  if (!trimmed) return null
  return batchNo > 1 ? `${trimmed}-B${batchNo}` : trimmed
}

/** Sequential fallback for orders with no MO number: "LOG-{year}-####", one
 *  past the highest sequence already in the store this year. */
function nextSequentialSystemId(): string {
  const prefix = `LOG-${new Date().getFullYear()}-`
  const seqs = ALL
    .map((o) => o.systemId)
    .filter((sid) => sid.startsWith(prefix))
    .map((sid) => Number(sid.slice(prefix.length)))
    .filter((n) => Number.isFinite(n))
  const next = seqs.length ? Math.max(...seqs) + 1 : 1
  return `${prefix}${String(next).padStart(4, '0')}`
}

/**
 * System id for a NEW order, per the confirmed rule:
 *   - MO number + Batch 1  -> the MO number itself (e.g. "MO-2026-001")
 *   - MO number + Batch 2+ -> "{moNo}-B{batchNo}" (e.g. "MO-2026-001-B2")
 *   - No MO number          -> sequential "LOG-{year}-####", never a UUID
 *
 * Deterministic from (moNo, batchNo) in the MO case, so the wizard must
 * resolve batchNo (via nextBatchNoForMo) BEFORE calling this — see
 * LogisticsStatusWizard's commitNavigate.
 *
 * Known limitation (acceptable for this mock/demo data layer): batchNo is
 * only resolved against `ALL` (real, submitted orders), not `DRAFTS`. Two
 * concurrent in-progress creations under the same brand-new MO would both
 * resolve to Batch 1 and collide. A real backend would allocate the batch
 * number atomically at submit time instead.
 */
export function generateLogisticsSystemId(moNo: string | undefined, batchNo: number): string {
  return moBasedSystemId(moNo, batchNo) ?? nextSequentialSystemId()
}

/** Every package belonging to sibling batches under the same MO (excluding
 *  the given order itself) — used to compute outstanding quantity across the
 *  whole MO group, since a sibling batch's package can allocate against this
 *  order's items too (and vice versa). */
export function getSiblingPackages(moNo: string | undefined, excludeSystemId: string): LogisticsPackage[] {
  if (!moNo) return []
  return ALL
    .filter((o) => o.moNo === moNo && o.systemId !== excludeSystemId)
    .flatMap((o) => o.packages)
}

/** Outstanding quantity for a set of items, accounting for allocations
 *  across EVERY package in the MO group — the item's own batch's packages
 *  (ownPackages, typically the in-progress form's own `packages` field) PLUS
 *  every sibling batch's packages, not just one or the other. This is what
 *  makes Step 1's "items from previous batches" preview and Step 2's
 *  cross-batch allocation section show the true remaining quantity instead
 *  of the sibling's full order quantity. */
export function outstandingByItemAcrossMo(
  items: LogisticsItem[],
  ownPackages: LogisticsPackage[],
  moNo: string | undefined,
  excludeSystemId: string,
): Record<string, number> {
  const allPackages = [...ownPackages, ...getSiblingPackages(moNo, excludeSystemId)]
  return outstandingByItem(items, allPackages)
}

/** Summary of an existing MO group, for the "MO already exists" indicator on
 *  Step 1 — null when the MO doesn't exist yet (or is empty). Excludes the
 *  given order itself so editing an existing order doesn't count it as its
 *  own sibling. */
export function getMoGroupSummary(moNo: string, excludeSystemId: string): { batchCount: number; itemCount: number } | null {
  if (!moNo.trim()) return null
  const siblings = ALL.filter((o) => o.moNo === moNo && o.systemId !== excludeSystemId)
  if (siblings.length === 0) return null
  return {
    batchCount: siblings.length,
    itemCount: siblings.reduce((s, o) => s + o.items.length, 0),
  }
}

/**
 * Mutates the in-memory mock store — same convention as updateConsignment in
 * lib/importsStatusData.ts.
 *
 * RFD-CHANGE AUDIT: `plannedRfdDate`/`actualRfdDate` can be edited on Step 1,
 * and every change has to be logged (recordRfdChange). The comparison has to
 * happen HERE, against the record still sitting in `ALL`, because that is
 * the only place the field's true PREVIOUS value is still known — by the
 * time a step component sees `data`, react-hook-form has already applied the
 * user's edit, so the old value is gone from the form's own state. Matched
 * by item id (not index), so a newly-added item this session (no prior
 * record to diff against) is left alone.
 */
export function updateLogisticsOrder(systemId: string, data: LogisticsDraft, changedBy: string): void {
  const idx = ALL.findIndex((o) => o.systemId === systemId)
  if (idx === -1) return
  const existing = ALL[idx]

  const items = data.items.map((item) => {
    const prev = existing.items.find((p) => p.id === item.id)
    if (!prev) return item
    let history = prev.rfdHistory
    if (prev.plannedRfdDate !== (item.plannedRfdDate ?? '')) {
      history = recordRfdChange({ ...prev, rfdHistory: history }, 'plannedRfdDate', item.plannedRfdDate ?? '', changedBy).rfdHistory
    }
    if (prev.actualRfdDate !== (item.actualRfdDate ?? '')) {
      history = recordRfdChange({ ...prev, rfdHistory: history }, 'actualRfdDate', item.actualRfdDate ?? '', changedBy).rfdHistory
    }
    return { ...item, rfdHistory: history }
  })

  ALL[idx] = { ...data, items, systemId }
}

/**
 * Persists a brand-new order — called only from the wizard's final Submit.
 * The wizard mints its own id (generateLogisticsSystemId, MO-based — see
 * that function) the moment Step 1's Next is clicked, well before Submit —
 * so by the time this runs, `systemId` already appears in every URL the
 * user has been navigating through. Reusing it (rather than generating a
 * fresh id here) is what makes getLogisticsOrder(id) find the record
 * immediately after Submit. Clears the in-progress draft cache entry (see
 * below) since the order is now real.
 */
export function createLogisticsOrder(systemId: string, data: LogisticsDraft): void {
  ALL.push({ ...data, systemId })
  delete DRAFTS[systemId]
}

/**
 * Session cache for a NOT-YET-SUBMITTED new order — separate from `ALL`
 * (real, submitted records) so a multi-step creation survives the
 * `/new` → `/:id/edit/2` remount (a genuine remount: they're separate
 * <Route> entries in App.tsx, unlike every later step-to-step move, which
 * matches the same `:id/edit/:step` route and doesn't remount — see
 * LogisticsStatusWizard's commitNavigate) without the order counting as a
 * real, known record while it's still being filled in. Mirrors the
 * MANUAL_JOBS/EDITS split in lib/truckingStatusData.ts.
 */
const DRAFTS: Record<string, LogisticsDraft> = {}

export function saveLogisticsDraft(systemId: string, data: LogisticsDraft): void {
  DRAFTS[systemId] = data
}

export function getLogisticsDraft(systemId: string): LogisticsDraft | undefined {
  return DRAFTS[systemId]
}

/** True only for a real, submitted order — never for an in-progress draft.
 *  The wizard uses this (not "does getLogisticsOrder find it") to decide
 *  new-record-creation-mode vs. genuine-edit-mode, mirroring Trucking's
 *  isKnownRecord() for the identical reason. */
export function isKnownLogisticsOrder(systemId: string): boolean {
  return ALL.some((o) => o.systemId === systemId)
}

/**
 * An FOB import consignment surfaced as a Logistics open request. On FOB
 * terms the buyer (Qadri) owns the goods from the origin port, so Qadri's
 * Logistics team books the sea freight and appoints the clearing agent —
 * exactly the work this module does for its own export/local orders. These
 * are READ-ONLY: the real record lives in Imports Status, so the request row
 * links back there rather than opening a Logistics editor. Derived live from
 * the Imports store, never copied, so it always reflects the source.
 */
export interface LogisticsFobRequest {
  systemId: string           // TR-style synthetic id, e.g. LOG-REQ-QC-2026-0148
  sourceRef: string          // the real consignment systemId in Imports
  customerName: string       // the branch taking delivery
  itemSummary: string
  origin: string             // origin port / country
  status: string             // the consignment's current status
  needsClearingAgent: boolean
  open: true
}

/** FOB imports past Under Production that still need shipping / clearing
 *  arrangement. Mirror of truckingStatusData's deriveFromImportsFob. */
export function deriveImportFobRequests(): LogisticsFobRequest[] {
  try {
    const rows = importsData.getConsignments() ?? []
    const productionIdx = CONSIGNMENT_STATUSES.indexOf('Under Production')
    return rows
      .filter((r) => r.incoterm === 'FOB' && CONSIGNMENT_STATUSES.indexOf(r.status) > productionIdx)
      .map((r): LogisticsFobRequest => {
        const first = r.items[0]
        const more = r.items.length - 1
        return {
          systemId: `LOG-REQ-${r.systemId}`,
          sourceRef: r.systemId,
          customerName: r.branch,
          itemSummary: first ? `${first.itemName}${more > 0 ? ` +${more} more` : ''}` : 'No items',
          origin: r.origin,
          status: r.status,
          needsClearingAgent: !r.clearingAgent,
          open: true,
        }
      })
  } catch {
    return []
  }
}

/**
 * ---------------------------------------------------------------------------
 * Logistics Service Jobs
 * ---------------------------------------------------------------------------
 * Logistics performs shipping/clearing service work that isn't one of its own
 * export/local orders. Two kinds live together under "Service Jobs":
 *
 *   - Import FOB  — handed over from Imports (item details were entered THERE
 *                   first). These stay derived + read-only via
 *                   deriveImportFobRequests(); the record's home is Imports.
 *   - Customer Rework — a customer sends in old rolls / used goods for rework.
 *                   Imports is NOT involved, so Logistics enters every detail
 *                   itself. These are real, owned, editable records kept in the
 *                   in-memory store below (mirrors the ALL/DRAFTS pattern used
 *                   for orders and MANUAL_JOBS in trucking).
 *
 * Both are surfaced in the Service Jobs tab of the Logistics list.
 */
export type ServiceJobType = 'import-fob' | 'customer-rework'

export interface ServiceJob {
  systemId: string
  jobType: ServiceJobType
  customerName: string
  itemDetails: string       // logistics-entered for rework; summary for FOB
  quantity?: number
  origin: string
  status: string
  receivedDate?: string     // when the customer's goods arrived at logistics
  targetDate?: string       // when the rework/shipping should be done
  clearingAgent?: string
  remarks?: string
  /** For import-fob rows only: the source consignment in Imports. */
  sourceRef?: string
}

const REWORK_STATUSES = ['Received', 'Under Rework', 'Ready', 'Dispatched'] as const
export const reworkStatusList = [...REWORK_STATUSES]

// Seeded so the tab isn't empty in the demo.
const REWORK_JOBS: ServiceJob[] = [
  {
    systemId: 'SVC-2026-0001', jobType: 'customer-rework',
    customerName: 'Packages Ltd', itemDetails: 'Used kraft paper rolls — re-slitting',
    quantity: 24, origin: 'Lahore', status: 'Under Rework',
    receivedDate: '2026-05-02', targetDate: '2026-05-20', remarks: 'Customer-owned stock',
  },
  {
    systemId: 'SVC-2026-0002', jobType: 'customer-rework',
    customerName: 'Century Paper', itemDetails: 'Old film rolls — re-winding + inspection',
    quantity: 12, origin: 'Kasur', status: 'Received', receivedDate: '2026-05-11',
  },
]

let reworkSeq = 3

/** Derived FOB requests + owned rework jobs, unified as ServiceJob rows. */
export function getServiceJobs(jobType?: ServiceJobType): ServiceJob[] {
  const fob: ServiceJob[] = deriveImportFobRequests().map((r) => ({
    systemId: r.systemId,
    jobType: 'import-fob' as const,
    customerName: r.customerName,
    itemDetails: r.itemSummary,
    origin: r.origin,
    status: r.status,
    clearingAgent: r.needsClearingAgent ? undefined : 'Assigned',
    sourceRef: r.sourceRef,
  }))
  const all = [...fob, ...REWORK_JOBS]
  return jobType ? all.filter((j) => j.jobType === jobType) : all
}

export function getServiceJob(systemId: string): ServiceJob | undefined {
  return getServiceJobs().find((j) => j.systemId === systemId)
}

/** Create a customer-rework job (logistics enters everything itself). */
export function createReworkJob(input: Omit<ServiceJob, 'systemId' | 'jobType'>): ServiceJob {
  const job: ServiceJob = {
    ...input,
    systemId: `SVC-2026-${String(reworkSeq++).padStart(4, '0')}`,
    jobType: 'customer-rework',
  }
  REWORK_JOBS.unshift(job)
  return job
}

/** Update an existing customer-rework job in place. */
export function updateReworkJob(systemId: string, patch: Partial<ServiceJob>): void {
  const job = REWORK_JOBS.find((j) => j.systemId === systemId)
  if (job) Object.assign(job, patch)
}

export const customerList = [...CUSTOMERS]
export const orderTypeList = [...ORDER_TYPES]
export const departmentList = [...DEPARTMENTS]
/** Both pipelines' statuses, deduplicated — a status filter needs every
 *  label either order type can be in, not just one pipeline's set. */
export const statusList = [...new Set([...statusesFor('Export'), ...statusesFor('Local')])]
