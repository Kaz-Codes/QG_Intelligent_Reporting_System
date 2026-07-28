import {
  CONSIGNMENT_STATUSES,
  CLOSED_STATUS,
  DRAFT_DEFAULT_VALUES,
  SUBMITTED,
  emptyItem,
  type ConsignmentStatus,
  type ConsignmentDraft,
  type RequisitionType,
} from '@/features/importsStatus/schema'

/**
 * Imports Status mock data.
 *
 * Matches the house style of lib/mockData.ts — a module-level array built once,
 * with a *Filters interface and a get*() that filters it — but the rows are
 * structured (header + item lines + history) to match the wizard schema rather
 * than flat. A tiny seeded RNG lives here so the file has no external deps and
 * the numbers are stable between reloads.
 *
 * Replaced wholesale by the FastAPI /api/consignments endpoints.
 */

/* -- self-contained seeded RNG so rows are deterministic ------------- */
function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
const rng = mulberry32(31)
const randInt = (lo: number, hi: number) => lo + Math.floor(rng() * (hi - lo + 1))
const pick = <T>(arr: readonly T[]): T => arr[Math.floor(rng() * arr.length)]
const iso = (d: Date) => d.toISOString().slice(0, 10)
const addDays = (from: string, n: number) => iso(new Date(+new Date(from) + n * 86_400_000))

export const BRANCHES = ['Qadcast', 'Qadri Brothers Unit 2', 'Qadri Engineering', 'Qadbros Engineering'] as const
export const SUPPLIERS = [
  'Wuxi Kaiyuan Machinery Co., Ltd', 'SKF Sverige AB', 'Zhejiang Hengtai Industrial',
  'Siemens AG', 'Trelleborg Sealing Solutions', 'Bosch Rexroth AG',
  'Yaskawa Electric Corporation', 'Hyundai Steel Company',
] as const
export const ORIGINS = ['China', 'Germany', 'Sweden', 'Japan', 'Korea, Republic of', 'United States'] as const
export const CURRENCIES = ['USD', 'EUR', 'JPY'] as const
export const REQUISITION_LABELS = ['Store', 'Engineering', 'Others'] as const
export const PAYMENT_INSTRUMENTS = ['LC', 'Adv', 'DP', 'CAD'] as const

const CATALOGUE = [
  ['Ball bearing 6205-2RS', 'BRG-6205', 'Pcs'],
  ['Oil seal TC 35x52x7', 'SEL-3552', 'Pcs'],
  ['V-belt SPB 2000', 'VBT-SPB2000', 'Pcs'],
  ['PLC S7-1500 CPU', 'PLC-1515', 'Pcs'],
  ['Proportional valve 4WRE', 'HYD-VLV4WRE', 'Pcs'],
  ['Alloy steel round bar 80mm', 'STL-RB80', 'Kg'],
  ['Servo drive SGD7S', 'SRV-SGD7S', 'Pcs'],
  ['Hydraulic seal kit', 'HYD-KIT01', 'Set'],
] as const

export interface ConsignmentItemRow {
  itemName: string
  itemCode: string
  quantity: number
  uom: string
  requisitionType: string
  referenceNo: string
  hsCode: string | null
}

export interface ConsignmentRow {
  systemId: string
  branch: string
  supplier: string
  origin: string
  currency: string
  items: ConsignmentItemRow[]
  requisitionSummary: string // "Store", or "Store + Engineering" for a mixed consignment
  status: ConsignmentStatus
  etd: string | null
  eta: string | null
  etaHistory: string[] // oldest first; slippage is current minus the first
  foreignValue: number
  exchangeRate: number
  rateDate: string
  paymentInstrument: string
  paymentLabel: string
  paymentState: 'paid' | 'partial' | 'unpaid'
  outstanding: number
  clearingAgent: string | null
  arrivedAtPort: string | null
  gateOut: string | null
  freeDays: number | null
  missing: string[] // named gaps, not a count
}

function makeRow(i: number): ConsignmentRow {
  const status = pick(CONSIGNMENT_STATUSES)
  const stageIndex = CONSIGNMENT_STATUSES.indexOf(status)
  const currency = pick(CURRENCIES)
  const instrument = pick(PAYMENT_INSTRUMENTS)

  const lineCount = randInt(1, 3)
  const items: ConsignmentItemRow[] = Array.from({ length: lineCount }, () => {
    const [name, code, uom] = pick(CATALOGUE)
    const req = pick(REQUISITION_LABELS)
    return {
      itemName: name, itemCode: code, quantity: randInt(4, 400), uom,
      requisitionType: req,
      referenceNo:
        req === 'Store' ? `STR-2026-${randInt(800, 999)}`
        : req === 'Engineering' ? `ENG-2026-${randInt(400, 499)}` : '',
      hsCode: rng() > 0.25 ? `${randInt(7000, 8500)}.${randInt(10, 99)}.00` : null,
    }
  })
  const requisitionSummary = [...new Set(items.map((it) => it.requisitionType))].join(' + ')

  const hasSchedule = stageIndex >= 2
  const etd = hasSchedule ? addDays('2026-04-01', randInt(30, 110)) : null
  const eta = etd ? addDays(etd, randInt(18, 42)) : null

  const revisionCount = eta ? randInt(0, 2) : 0
  const etaHistory: string[] = []
  if (eta && revisionCount) {
    let cursor = eta
    for (let r = 0; r < revisionCount; r++) {
      cursor = addDays(cursor, -randInt(4, 9))
      etaHistory.unshift(cursor)
    }
  }

  const arrived = stageIndex >= 4 && eta ? addDays(eta, randInt(-2, 3)) : null
  const cleared = stageIndex >= 8 && arrived ? addDays(arrived, randInt(3, 14)) : null

  const foreignValue = randInt(3_000, 78_000)
  const exchangeRate =
    currency === 'JPY' ? 1.84 + rng() * 0.06 : currency === 'EUR' ? 318 + rng() * 10 : 279 + rng() * 6

  const roll = rng()
  const paymentState: ConsignmentRow['paymentState'] = roll > 0.62 ? 'paid' : roll > 0.3 ? 'partial' : 'unpaid'
  const outstanding = paymentState === 'paid' ? 0 : paymentState === 'partial' ? foreignValue / 2 : foreignValue
  const paymentLabel =
    instrument === 'LC'
      ? paymentState === 'paid' ? 'LC retired' : paymentState === 'partial' ? 'LC · partial' : 'LC pending'
      : instrument === 'Adv'
        ? paymentState === 'paid' ? 'Advance paid' : paymentState === 'partial' ? 'Advance · partial' : 'Advance due'
        : `${instrument} ${paymentState === 'paid' ? 'paid' : 'unpaid'}`

  const missing: string[] = []
  items.forEach((it, n) => {
    if (!it.hsCode) missing.push(`H.S. code on item ${n + 1}`)
    if (!it.referenceNo && it.requisitionType !== 'Others') missing.push(`Reference no. on item ${n + 1}`)
  })
  if (!etd) missing.push('ETD')
  if (!eta) missing.push('ETA')
  if (stageIndex >= 4 && !cleared) missing.push('Gate out date')

  return {
    systemId: `QC-2026-${String(160 - i).padStart(4, '0')}`,
    branch: pick(BRANCHES), supplier: pick(SUPPLIERS), origin: pick(ORIGINS), currency,
    items, requisitionSummary, status, etd, eta, etaHistory,
    foreignValue, exchangeRate: Number(exchangeRate.toFixed(2)), rateDate: etd ?? '2026-05-01',
    paymentInstrument: instrument, paymentLabel, paymentState, outstanding,
    clearingAgent: stageIndex >= 4 ? pick(['Prime Cargo Services', 'Indus Clearing Co.', 'Sea Link Logistics']) : null,
    arrivedAtPort: arrived, gateOut: cleared,
    freeDays: stageIndex >= 4 ? randInt(0, 9) : null,
    missing,
  }
}

const ALL: ConsignmentRow[] = Array.from({ length: 34 }, (_, i) => makeRow(i))

/* -- derived --------------------------------------------------------- */
export const pkrValue = (r: ConsignmentRow) => r.foreignValue * r.exchangeRate

export const slippageDays = (r: ConsignmentRow) =>
  r.etaHistory.length && r.eta
    ? Math.round((+new Date(r.eta) - +new Date(r.etaHistory[0])) / 86_400_000)
    : null

export const daysAtPort = (r: ConsignmentRow, today = '2026-07-24') =>
  r.arrivedAtPort ? Math.round((+new Date(r.gateOut ?? today) - +new Date(r.arrivedAtPort)) / 86_400_000) : null

export const freeDaysLeft = (r: ConsignmentRow) => {
  const at = daysAtPort(r)
  return at === null || r.freeDays === null ? null : r.freeDays - at
}

/* -- stage grouping: 11 statuses roll into 6 scannable stages -------- */
export const STAGE_GROUPS = [
  { key: 'Pre-shipment', statuses: ['TT/LC in Process'] },
  { key: 'Production', statuses: ['Under Production', 'Ready Awaiting Sailing'] },
  { key: 'In transit', statuses: ['In Transit'] },
  { key: 'Clearance', statuses: ['Arrived at Port', 'Under Custom Clearance', 'Under Examination', 'Under Assessment'] },
  { key: 'Inbound', statuses: ['Arrived at QFL', 'On Road'] },
  { key: 'Closed', statuses: ['Arrived at Works'] },
] as const
export type StageKey = (typeof STAGE_GROUPS)[number]['key'] | 'all'

export const stageOf = (status: string): StageKey =>
  STAGE_GROUPS.find((g) => (g.statuses as readonly string[]).includes(status))?.key ?? 'Pre-shipment'

export function stageCounts(includeClosed: boolean): { key: StageKey; count: number }[] {
  const openTotal = ALL.filter((r) => includeClosed || r.status !== CLOSED_STATUS).length
  return [
    { key: 'all' as StageKey, count: openTotal },
    ...STAGE_GROUPS.map((g) => ({
      key: g.key as StageKey,
      count: ALL.filter((r) => (g.statuses as readonly string[]).includes(r.status)).length,
    })),
  ]
}

/* -- filtering ------------------------------------------------------- */
export interface ConsignmentFilters {
  search?: string
  branch?: string[]
  status?: string[]
  requisition?: string[]
  supplier?: string[]
  stage?: StageKey
  includeClosed?: boolean
  missingOnly?: boolean
}

const inSet = (v: string, s?: string[]) => !s || s.length === 0 || s.includes(v)

export function getConsignments(f: ConsignmentFilters = {}): ConsignmentRow[] {
  const q = (f.search ?? '').trim().toLowerCase()
  const stageStatuses =
    f.stage && f.stage !== 'all'
      ? (STAGE_GROUPS.find((g) => g.key === f.stage)?.statuses as readonly string[] | undefined)
      : undefined

  return ALL.filter((r) => {
    if (!f.includeClosed && r.status === CLOSED_STATUS && f.stage !== 'Closed' && !f.status?.includes(CLOSED_STATUS)) return false
    if (stageStatuses && !stageStatuses.includes(r.status)) return false
    if (!inSet(r.branch, f.branch)) return false
    if (!inSet(r.status, f.status)) return false
    if (!inSet(r.supplier, f.supplier)) return false
    if (f.requisition?.length && !f.requisition.some((x) => r.requisitionSummary.includes(x))) return false
    if (f.missingOnly && r.missing.length === 0) return false
    if (q) {
      const hay = [r.systemId, r.supplier, r.origin, r.branch, ...r.items.map((i) => `${i.itemName} ${i.referenceNo}`)]
        .join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

export const getConsignment = (systemId: string) => ALL.find((r) => r.systemId === systemId)

export const branchList = [...BRANCHES]
export const statusList = [...CONSIGNMENT_STATUSES]
export const supplierList = [...SUPPLIERS]
export const requisitionList = [...REQUISITION_LABELS]

/* ------------------------------------------------------------------ */
/* Wizard draft bridge                                                 */
/* ------------------------------------------------------------------ */

/**
 * `ConsignmentRow` (above) is the flat, display-shaped record the list/detail
 * screens read. `ConsignmentDraft` (schema.ts) is the much deeper shape the
 * wizard's form actually edits — most of its fields (instrument no., ports,
 * ETA revision history, payments, status history, landed cost...) simply
 * aren't tracked by the row. Editing an existing consignment means bridging
 * the two: known overlapping fields come from the row, everything the row
 * doesn't carry starts blank, exactly like a brand-new draft would.
 *
 * `DRAFTS` caches the bridged (and then edited) draft per systemId so that
 * navigating between wizard steps — which fully remounts the page — doesn't
 * lose edits made on a step already visited this session.
 */
const DRAFTS: Record<string, ConsignmentDraft> = {}

const REQ_LABEL_TO_TYPE: Record<string, RequisitionType> = {
  Store: 'store', Engineering: 'engineering', Others: 'others',
}

function rowToDraft(row: ConsignmentRow): ConsignmentDraft {
  return {
    ...DRAFT_DEFAULT_VALUES,
    systemId: row.systemId,
    branch: row.branch,
    supplier: row.supplier,
    origin: row.origin,
    currency: row.currency,
    items: row.items.map((it, i) => ({
      ...emptyItem(`item-${row.systemId}-${i}`),
      itemName: it.itemName,
      itemCode: it.itemCode,
      quantity: it.quantity,
      uom: it.uom,
      requisitionType: REQ_LABEL_TO_TYPE[it.requisitionType],
      referenceNo: it.referenceNo,
      hsCode: it.hsCode ?? '',
    })),
    paymentInstrument: row.paymentInstrument as ConsignmentDraft['paymentInstrument'],
    exchangeRate: row.exchangeRate,
    rateDate: row.rateDate,
    etd: row.etd ?? '',
    eta: row.eta ?? '',
    status: row.status,
    clearingAgent: row.clearingAgent ?? '',
    freeDays: row.freeDays ?? undefined,
    gateOutDate: row.gateOut ?? '',
    // An existing record found in the system is treated as previously
    // submitted, not a fresh draft — DRAFT_DEFAULT_VALUES otherwise defaults
    // recordState to 'draft', which is only right for a brand-new consignment.
    recordState: SUBMITTED,
  }
}

/**
 * Edit-mode entry point for the wizard: returns the full draft for an
 * existing consignment (from the session's edit cache if this consignment has
 * already been opened/edited this session, otherwise bridged fresh from the
 * row), or `undefined` if no such consignment exists.
 */
export function getConsignmentDraft(systemId: string): ConsignmentDraft | undefined {
  if (DRAFTS[systemId]) return DRAFTS[systemId]
  const row = getConsignment(systemId)
  if (!row) return undefined
  const draft = rowToDraft(row)
  DRAFTS[systemId] = draft
  return draft
}

/**
 * Persists a step's edits for the session. Mutates the in-memory mock store:
 * the full draft cache (so every field the wizard tracks survives the next
 * step's full-page remount), and the fields `ConsignmentRow` itself carries
 * (so the list/detail screens — which read `ALL`, not the draft cache — also
 * reflect the edit).
 */
export function updateConsignment(systemId: string, data: ConsignmentDraft): void {
  DRAFTS[systemId] = data

  const row = ALL.find((r) => r.systemId === systemId)
  if (!row) return
  row.branch = data.branch || row.branch
  row.supplier = data.supplier || row.supplier
  row.origin = data.origin || row.origin
  row.currency = data.currency || row.currency
  row.status = (data.status || row.status) as ConsignmentStatus
  row.etd = data.etd || row.etd
  row.eta = data.eta || row.eta
  row.exchangeRate = data.exchangeRate ?? row.exchangeRate
  row.rateDate = data.rateDate || row.rateDate
  row.clearingAgent = data.clearingAgent || row.clearingAgent
  row.freeDays = data.freeDays ?? row.freeDays
  row.gateOut = data.gateOutDate || row.gateOut
}
