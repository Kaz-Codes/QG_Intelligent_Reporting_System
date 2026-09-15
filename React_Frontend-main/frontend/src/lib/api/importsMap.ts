import type {
  ApiConsignment, ApiConsignmentItem, ConsignmentPayload,
  ConsignmentItemPayload, ConsignmentPaymentPayload,
} from './imports'
import type { MasterOption, PortOption } from './masters'
import { nameToId } from './masters'
import {
  CONSIGNMENT_STATUSES, CLOSED_STATUS, DRAFT_DEFAULT_VALUES, SUBMITTED,
  emptyItem, emptyPayment,
  type ConsignmentDraft, type ConsignmentItem as DraftItem, type Payment as DraftPayment,
} from '@/features/importsStatus/schema'

/**
 * Backend consignment -> the row the list table draws.
 *
 * This is where the two generations of data are reconciled. Rows loaded from
 * the Excel sheets and rows entered through the ERP do NOT carry the same
 * fields, so every mapping here has to treat "not recorded" as a first-class
 * value rather than assuming a number:
 *
 *  - foreign_total / pkr_total are NULL on every imported row (the loader never
 *    ran the derivation), so both are recomputed from the item lines when the
 *    stored figure is missing. A consignment with no priced line stays null —
 *    never 0, which would read as "worth nothing" instead of "not priced yet".
 *  - exchange_rate / rate_booked_on are missing on imported rows, so PKR value
 *    is null rather than a bogus conversion.
 *  - requisition_type and reference_number are NULL on every imported item
 *    (the sheet has no such column), so the requisition summary falls back to
 *    a dash instead of an empty string that looks like a rendering bug.
 *  - payments were never loaded (there are none for imported rows), so payment
 *    state is derived from what IS known and reported as 'unknown' rather than
 *    guessing "unpaid".
 *  - current_status may be a value the eleven-status enum has never heard of
 *    ("Order Cancelled", "LC in Process", ...). It's kept verbatim and flagged,
 *    so those rows stay visible and filterable instead of being dropped.
 */

/** A number that may arrive as a Decimal string from the API. Null-safe: a
 *  missing value stays null, it does NOT become 0. */
function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

const CANONICAL_STATUSES = new Set<string>(CONSIGNMENT_STATUSES)

export interface ImportsListItem {
  itemName: string
  placeholderName: string
  itemCode: string
  quantity: number | null
  uom: string
  requisitionType: string | null
  referenceNo: string
  hsCode: string | null
  unitPrice: number | null
  netWeight: number | null
  grossWeight: number | null
  length: number | null
  width: number | null
  height: number | null
}

export type PaymentState = 'paid' | 'partial' | 'unpaid' | 'unknown'

export interface ImportsListRow {
  /** The real database id — what every endpoint and route uses. */
  id: number
  /** THE ROUTE TARGET AND THE REACT KEY, as a string. NOT what the screen
   *  shows: on batch 2 of an order this is `184` while the consignment is
   *  called `21-2`, and printing it names a consignment nobody can look up
   *  (design 0.4). Use `consignmentNumber` for anything a person reads. */
  systemId: string
  /** Does this row's ORDER still have unallocated quantity? `null` = the
   *  caller did not ask (see apiToRow). Drives the pending highlight. */
  hasPendingAllocation: boolean | null
  /** Which order this batch belongs to, and where in it. `batchSequence` is
   *  what the number is derived from; neither is ever displayed raw. */
  batchGroupId: number | null
  batchSequence: number | null
  /** WHAT THE SCREEN SHOWS: `177`, or `177-1` / `177-2` once the order has
   *  split. Built by the server, never assembled here — the rule is "suffix
   *  only once an order has EVER held two batches", which is exactly the part
   *  a browser-side copy would get wrong. Empty only if the payload carried
   *  no number, which cannot happen for a row that has an order; it renders
   *  as a dash rather than falling back to the id, because a fallback that is
   *  wrong precisely in the case it exists for is worse than a visible gap. */
  consignmentNumber: string
  branch: string
  supplier: string
  origin: string
  currency: string
  incoterm: string | null
  /** THE ORDER'S BRANCH NAME, under its old key. `works` was free text on
   *  the consignment and is retired: the server now returns the works/branch
   *  NAME here, which is the same string as `branch`. Kept so nothing reading
   *  it breaks; nothing renders it any more (the detail's Finance section
   *  showed it beside an identical Branch row) and nothing writes it. */
  works: string | null

  items: ImportsListItem[]
  requisitionSummary: string

  status: string
  /** False when the stored status isn't one of the eleven — imported rows can
   *  carry sheet-only values, and the UI marks them rather than hiding them. */
  statusCanonical: boolean

  requisitionDate: string | null
  requiredDate: string | null
  etd: string | null
  eta: string | null
  /** Oldest promised ETA first; slippage is current minus the first. */
  etaHistory: string[]

  foreignValue: number | null
  exchangeRate: number | null
  rateDate: string | null
  pkrValue: number | null

  paymentInstrument: string | null
  paymentReference: string | null
  instrumentNo: string | null
  paymentLabel: string
  paymentState: PaymentState

  clearingAgent: string | null
  arrivedAtPort: string | null
  gateOut: string | null
  freeDays: number | null

  /** "A user marked this finished." Nothing verifies the claim — imports has
   *  no submit rule set, so there is no `missing` list beside this any more. */
  recordState: string
  isLocked: boolean
  isClosed: boolean

  /** Cross-module hand-off timestamps (ISO), or null when not sent. These
   *  drive the list's "Sent" column and disable each Send button. */
  sentToLogisticsAt: string | null
  sentToTruckingAt: string | null

  // --- detail-page-only fields (harmless on the list, just unused there) ---
  gdNumber: string | null
  gdFilingDate: string | null
  containerDetention: number | null
  /** Foreign-value amount still unpaid — foreignValue minus what's marked
   *  Paid. Null when foreignValue itself is null (nothing to subtract from). */
  outstanding: number | null
  /** Σ bank_charges across payment lines — a cost of the transaction, not
   *  against the goods, so it's kept separate from `outstanding`. */
  bankCharges: number
  demurrage: number | null
  /** Auto-generated from the ETA + status history — read-only. */
  systemRemarks: string
  /** The user's own free-text note — distinct from systemRemarks. */
  userRemarks: string | null
  createdBy: string | null
  /** Soft-deleted. Only ever present for an admin, who is the only
   *  one the list fetches deleted rows for. */
  isDeleted: boolean
}

function mapItem(item: ApiConsignmentItem): ImportsListItem {
  return {
    itemName: item.item_name ?? '',
    placeholderName: item.placeholder_name ?? '',
    itemCode: item.item_code ?? '',
    quantity: toNumber(item.quantity),
    uom: item.unit_of_measurement ?? '',
    requisitionType: item.requisition_type,
    referenceNo: item.reference_number ?? '',
    hsCode: item.hs_code,
    unitPrice: toNumber(item.unit_price),
    netWeight: toNumber(item.net_weight),
    grossWeight: toNumber(item.gross_weight),
    length: toNumber(item.length),
    width: toNumber(item.width),
    height: toNumber(item.height),
  }
}

/** Σ quantity × unit price across priced lines. Null when no line is priced —
 *  the same rule the backend's recompute_derived uses, applied here only as a
 *  fallback for rows whose stored total was never computed. */
function computeForeignTotal(items: ImportsListItem[]): number | null {
  const priced = items.filter((i) => i.quantity !== null && i.unitPrice !== null)
  if (priced.length === 0) return null
  return priced.reduce((sum, i) => sum + (i.quantity ?? 0) * (i.unitPrice ?? 0), 0)
}

/**
 * Payment state without inventing facts. Imported rows have no payment lines at
 * all, so they report 'unknown' — deliberately NOT 'unpaid', which would be an
 * assertion the data doesn't support.
 */
function derivePayment(c: ApiConsignment, foreignValue: number | null) {
  // THE REFERENCE LEADS; the bare instrument type is the fallback.
  //
  // The tile used to read "CAD - not recorded": the payment TYPE and the
  // state, with the number nowhere on the header. It now reads
  // "cad46048 - not recorded" - the same information plus the one thing an
  // operator needs in order to look the payment up.
  //
  // Falls back to the type and then to "Payment", so an order with no
  // instrument number still reads "CAD pending" rather than a bare separator.
  const instrument = c.payment_reference || c.payment_instrument
  const payments = (c.payments ?? []).filter((p) => !p.is_deleted)

  if (payments.length === 0) {
    return {
      state: 'unknown' as PaymentState,
      label: instrument ? `${instrument} · not recorded` : 'Not recorded',
    }
  }

  const paid = payments
    .filter((p) => p.status === 'Paid')
    .reduce((sum, p) => sum + (toNumber(p.value) ?? 0), 0)

  let state: PaymentState = 'unpaid'
  if (paid > 0) state = foreignValue !== null && paid >= foreignValue ? 'paid' : 'partial'

  const noun = instrument ?? 'Payment'
  const label =
    state === 'paid' ? `${noun} settled`
    : state === 'partial' ? `${noun} · partial`
    : `${noun} pending`

  return { state, label }
}


/** The earliest non-empty value of a per-LINE date across a consignment's live
 *  lines. The demand dates moved onto the item lines, and the two places that
 *  still want one value per consignment (the list row, the wizard's single
 *  input) take the earliest — the same rule the server applies to
 *  `required_date`, so the two cannot disagree about which date is shown. */
function earliestLineDate(
  c: ApiConsignment,
  key: 'requisition_date' | 'required_date',
): string | null {
  const dates = (c.items ?? [])
    .filter((i) => !i.is_deleted)
    .map((i) => i[key])
    .filter((d): d is string => !!d)
    .sort()
  return dates[0] ?? null
}

export function apiToRow(c: ApiConsignment): ImportsListRow {
  const items = (c.items ?? []).filter((i) => !i.is_deleted).map(mapItem)

  // Distinct requisition types across the lines — "Store + Engineering" for a
  // mixed consignment. Imported rows have none, hence the dash.
  const reqTypes = [...new Set(items.map((i) => i.requisitionType).filter((t): t is string => !!t))]
  const requisitionSummary = reqTypes.length ? reqTypes.join(' + ') : '—'

  const foreignValue = toNumber(c.foreign_total) ?? computeForeignTotal(items)
  const exchangeRate = toNumber(c.exchange_rate)
  const storedPkr = toNumber(c.pkr_total)
  const pkrValue =
    storedPkr ?? (foreignValue !== null && exchangeRate !== null ? foreignValue * exchangeRate : null)

  // The ETA chain, oldest first: the first revision's "previous" is the ETA
  // originally promised, then each new value in turn.
  const revisions = (c.eta_revisions ?? []).filter((r) => r.eta_type === 'eta')
  const etaHistory: string[] = []
  revisions.forEach((r, index) => {
    if (index === 0 && r.previous_eta) etaHistory.push(r.previous_eta)
    if (r.new_eta) etaHistory.push(r.new_eta)
  })

  // The day it actually berthed, from the status log.
  const arrivedAtPort =
    (c.status_updates ?? []).find((s) => s.new_status === 'Arrived at Port')?.effective_date ?? null

  const status = c.current_status ?? ''
  const payment = derivePayment(c, foreignValue)

  const payments = (c.payments ?? []).filter((p) => !p.is_deleted)
  const paidTotal = payments
    .filter((p) => p.status === 'Paid')
    .reduce((sum, p) => sum + (toNumber(p.value) ?? 0), 0)
  // Only meaningful once there's a value to subtract from; a consignment with
  // no priced line has no outstanding figure, not a false 0.
  const outstanding = foreignValue !== null ? Math.max(foreignValue - paidTotal, 0) : null
  const bankCharges = payments.reduce((sum, p) => sum + (toNumber(p.bank_charges) ?? 0), 0)

  return {
    id: c.id,
    systemId: String(c.id),
    consignmentNumber: c.consignment_number ?? '',
    // NULL MEANS "NOT ASKED FOR", not "fully allocated" — only a list fetched
    // with includeBatchContext carries a boolean. Kept nullable all the way to
    // the row so a screen that forgot the flag renders no highlight rather
    // than a confident "nothing pending".
    hasPendingAllocation: c.has_pending_allocation ?? null,
    batchGroupId: c.batch_group_id ?? null,
    batchSequence: c.batch_sequence ?? null,
    branch: c.branch?.name ?? '—',
    supplier: c.supplier?.name ?? '—',
    origin: c.origin ?? '—',
    currency: c.currency ?? '',
    incoterm: c.incoterm,
    works: c.works,

    items,
    requisitionSummary,

    status,
    statusCanonical: CANONICAL_STATUSES.has(status),

    // The requisition date is per LINE now, so a list row takes the earliest of
    // its lines for display; requiredDate is the earliest too, computed server-
    // side (the list payload carries no lines, so it has to be).
    requisitionDate: earliestLineDate(c, 'requisition_date'),
    requiredDate: c.required_date,
    etd: c.etd,
    eta: c.eta,
    etaHistory,

    foreignValue,
    exchangeRate,
    rateDate: c.rate_booked_on,
    pkrValue,

    paymentInstrument: c.payment_instrument,
    paymentReference: c.payment_reference ?? null,
    instrumentNo: c.instrument_number,
    paymentLabel: payment.label,
    paymentState: payment.state,

    clearingAgent: c.clearing_agent?.name ?? null,
    arrivedAtPort,
    gateOut: c.gate_out_date,
    freeDays: c.free_days_allowed,

    recordState: c.record_state,
    isLocked: c.is_locked,
    // Soft-deleted rows are only ever FETCHED for an admin (includeDeleted on
    // the list query), but the flag has to reach the row either way — it is
    // what decides between the delete and the undo button.
    isDeleted: !!c.is_deleted,
    isClosed: status === CLOSED_STATUS,

    sentToLogisticsAt: c.sent_to_logistics_at ?? null,
    sentToTruckingAt: c.sent_to_trucking_at ?? null,

    gdNumber: c.gd_number,
    gdFilingDate: c.gd_filing_date,
    containerDetention: toNumber(c.container_detention),
    outstanding,
    bankCharges,
    demurrage: toNumber(c.demurrage_or_detention_paid),
    systemRemarks: c.system_remarks ?? '',
    userRemarks: c.remarks,
    createdBy: c.created_by,
  }
}

//-----------------------------------------------------
// DERIVED FIGURES
//
// Each returns null when the inputs aren't there, so "no data" and "no delay"
// stay visually distinct — never coerced to 0.
//-----------------------------------------------------

const dayDiff = (from: string, to: string) =>
  Math.round((+new Date(to) - +new Date(from)) / 86_400_000)

/** Current ETA against the FIRST one ever promised. */
export const slippageDays = (r: ImportsListRow) =>
  r.etaHistory.length && r.eta ? dayDiff(r.etaHistory[0], r.eta) : null

/** How late the goods land against when they were required. Positive = late. */
export const requiredDelayDays = (r: ImportsListRow) =>
  r.requiredDate && r.eta ? dayDiff(r.requiredDate, r.eta) : null

/** Days the cargo has been sitting at the port (to gate-out, or to today). */
export const daysAtPort = (r: ImportsListRow) =>
  r.arrivedAtPort ? dayDiff(r.arrivedAtPort, r.gateOut ?? new Date().toISOString().slice(0, 10)) : null

export const freeDaysLeft = (r: ImportsListRow) => {
  const at = daysAtPort(r)
  return at === null || r.freeDays === null ? null : r.freeDays - at
}

//-----------------------------------------------------
// WIZARD <-> BACKEND
//
// The wizard's ConsignmentDraft (camelCase, internal short enum values like
// 'efs'/'store') is a different shape from the API's ConsignmentPayload
// (snake_case, the backend's own enum spellings, master NAMES resolved to
// ids). These two functions are the only place that boundary is crossed.
//-----------------------------------------------------

// consignmentType: the wizard's short internal value <-> the backend's enum text.
const CONSIGNMENT_TYPE_TO_API: Record<string, string> = { efs: 'EFS', regular: 'Regular import' }
const CONSIGNMENT_TYPE_FROM_API: Record<string, string> = { EFS: 'efs', 'Regular import': 'regular' }

// requisitionType: same idea, per item.
const REQ_TYPE_TO_API: Record<string, string> = { store: 'Store', engineering: 'Engineering', others: 'Others' }
const REQ_TYPE_FROM_API: Record<string, string> = { Store: 'store', Engineering: 'engineering', Others: 'others' }

/** '' / undefined -> undefined, so the key is omitted from the payload rather
 *  than sent as an empty string the backend would reject or store literally. */
function strOrUndef(v: string | undefined | null): string | undefined {
  const t = v?.trim()
  return t ? t : undefined
}

/**
 * `methods.getValues()` returns react-hook-form's RAW internal state, not the
 * zod-parsed output — and mounting an uncontrolled number input, even one the
 * user never touches, syncs its native empty-string DOM value into that state
 * (the same phenomenon the wizard's own normalizeForDirtyCheck comment
 * describes). So a field that was genuinely never filled in doesn't arrive
 * here as `undefined`, it arrives as the STRING `''` — which the old
 * `numGe0`/`numGt0` (typed for `number | undefined`, trusting the OUTPUT type)
 * let straight through into the JSON body as `""`, and Pydantic 422s trying to
 * parse an empty string as a Decimal. `unknown` + explicit coercion here is
 * what actually matches what's on the wire, regardless of what TypeScript's
 * static type claims after the wizard's input/output-type cast.
 */
function toFiniteNumber(v: unknown): number | undefined {
  if (v === '' || v === null || v === undefined) return undefined
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : undefined
}

/** Optional[Decimal] fields with `ge=0` — 0 is a real, valid value there, only
 *  "never typed" should be omitted. */
function numGe0(v: unknown): number | undefined {
  return toFiniteNumber(v)
}

/** Optional[Decimal] fields with `gt=0` (quantity, unit price, payment value /
 *  rate) — the backend 422s on exactly 0, so a 0 (or blank, coerced to 0 by
 *  some inputs) is treated the same as "not entered" rather than sent through
 *  to fail validation. */
function numGt0(v: unknown): number | undefined {
  const n = toFiniteNumber(v)
  return n === undefined || n <= 0 ? undefined : n
}

function itemToPayload(item: DraftItem): ConsignmentItemPayload {
  return {
    id: item.backendId ?? null,
    // SENT ON EVERY LINE THAT HAS ONE. Dropping it is not a missing feature,
    // it is a data corruption: the server reads a line with no order line as a
    // NEW item on the order and raises what the order bought. Measured before
    // the backend guard existed — one added line on batch 2 took an order from
    // 33.523 to 38.523 with a 200 response (design §3.7b finding 3).
    order_item_id: item.orderItemId ?? null,
    // Only when the operator actually changed it. On an unsplit order the
    // server keeps `ordered_quantity` in step with `quantity` on its own, and
    // sending a stale copy back would freeze it at whatever was last fetched.
    ordered_quantity: numGt0(item.orderedQuantity),
    item_name: strOrUndef(item.itemName),
    placeholder_name: strOrUndef(item.placeholderName),
    item_code: strOrUndef(item.itemCode),
    hs_code: strOrUndef(item.hsCode),
    specification: strOrUndef(item.specification),
    quantity: numGt0(item.quantity),
    unit_of_measurement: strOrUndef(item.uom),
    batch_no: strOrUndef(item.batchNo),
    requisition_type: item.requisitionType ? REQ_TYPE_TO_API[item.requisitionType] : undefined,
    unit_price: numGt0(item.foreignUnitPrice),
    net_weight: numGe0(item.netWeight),
    gross_weight: numGe0(item.grossWeight),
    length: numGe0(item.length),
    width: numGe0(item.width),
    height: numGe0(item.height),
    reference_number: strOrUndef(item.referenceNo),
    job_number: strOrUndef(item.jobNo),
    mo_number: strOrUndef(item.moNo),
    description: strOrUndef(item.othersDescription),
  }
}

function paymentToPayload(payment: DraftPayment): ConsignmentPaymentPayload {
  return {
    id: payment.backendId ?? null,
    retirement_date: strOrUndef(payment.date),
    value: numGt0(payment.value),
    payment_exchange_rate: numGt0(payment.exchangeRate),
    bank_charges: numGe0(payment.bankCharges),
    status: payment.status,
    bank_reference: strOrUndef(payment.reference),
  }
}

export interface WizardMasters {
  branches: MasterOption[]
  suppliers: MasterOption[]
  ports: PortOption[]
  agents: MasterOption[]
}

/**
 * The whole current form state -> the body PUT/POST expects. Always built from
 * the FULL draft (every step's fields), regardless of which step triggered the
 * save — react-hook-form holds one shared object across all six steps, and the
 * update route diffs items/payments against what it already has, so sending
 * anything less than the full items/payments arrays would read as "the rest
 * were deleted".
 *
 * A branch/supplier/port/agent NAME that doesn't match anything in `masters`
 * (a typo, or a value not yet in the system) resolves to no id at all — the
 * draft still saves; only a submit would then point out it's missing.
 */
export function draftToPayload(draft: ConsignmentDraft, masters: WizardMasters): ConsignmentPayload {
  const today = new Date().toISOString().slice(0, 10)

  return {
    branch_id: nameToId(masters.branches, draft.branch),
    supplier_id: nameToId(masters.suppliers, draft.supplier),
    origin: strOrUndef(draft.origin),
    currency: strOrUndef(draft.currency),
    consignment_type: draft.consignmentType ? CONSIGNMENT_TYPE_TO_API[draft.consignmentType] : undefined,
    incoterm: strOrUndef(draft.incoterm),
    po_date: strOrUndef(draft.poDate),
    requisition_date: strOrUndef(draft.requisitionDate),
    required_date: strOrUndef(draft.requiredDate),

    payment_instrument: strOrUndef(draft.paymentInstrument),
    instrument_number: strOrUndef(draft.instrumentNo),
    opening_or_retirement_date: strOrUndef(draft.instrumentDate),
    exchange_rate: numGe0(draft.exchangeRate),
    rate_booked_on: strOrUndef(draft.rateDate),
    rate_source: strOrUndef(draft.rateSource),

    mode_of_shipment: strOrUndef(draft.modeOfShipment),
    loading_port_id: nameToId(masters.ports, draft.portOfLoading),
    delivery_port_id: nameToId(masters.ports, draft.portOfDelivery),
    cargo_readiness_date: strOrUndef(draft.readinessDate),
    etd: strOrUndef(draft.etd),
    eta: strOrUndef(draft.eta),
    eta_works: strOrUndef(draft.etaWorks),

    current_status: strOrUndef(draft.status),
    // Required alongside current_status whenever it actually changes
    // (add_in_status_change_history 400s without it) — the wizard has no
    // separate "effective date" input, so this defaults to today. Harmless to
    // always include: the backend only acts on it if the status changed.
    effective_date: draft.status ? today : undefined,
    remarks: strOrUndef(draft.userRemarks),

    clearing_agent_id: nameToId(masters.agents, draft.clearingAgent),
    gd_number: strOrUndef(draft.gdNumber),
    gd_filing_date: strOrUndef(draft.gdDate),
    free_days_allowed: numGe0(draft.freeDays),
    gate_out_date: strOrUndef(draft.gateOutDate),
    demurrage_or_detention_paid: numGe0(draft.demurrageCost),
    container_detention: numGe0(draft.containerDetention),

    items: draft.items.map(itemToPayload),
    payments: draft.payments.map(paymentToPayload),
  }
}

/**
 * After a successful save, the response's items/payments carry real backend
 * ids — including brand-new ones the user just added in the wizard, which had
 * no id when the request went out. This attaches those ids to the matching
 * form rows, so the NEXT save sends them back as "still exists" (id set)
 * rather than creating a duplicate row every time.
 *
 * Rows that already had a backendId are left alone and their id is treated as
 * claimed; whatever backend rows are left over are handed to the still-
 * unmatched form rows in order — safe because both lists preserve the
 * relative order new rows were added in.
 */
function syncBackendIds<T extends { backendId?: number }>(
  formRows: T[],
  responseRows: { id: number }[],
): T[] {
  const claimed = new Set(formRows.map((r) => r.backendId).filter((id): id is number => id !== undefined))
  const unclaimed = responseRows.filter((r) => !claimed.has(r.id))

  let next = 0
  return formRows.map((row) => {
    if (row.backendId !== undefined) return row
    const match = unclaimed[next]
    next += 1
    return match ? { ...row, backendId: match.id } : row
  })
}

export function syncItemBackendIds(items: DraftItem[], responseItems: ApiConsignmentItem[]): DraftItem[] {
  return syncBackendIds(items, responseItems)
}

export function syncPaymentBackendIds(payments: DraftPayment[], responsePayments: { id: number }[]): DraftPayment[] {
  return syncBackendIds(payments, responsePayments)
}

/**
 * The API's full consignment -> the wizard's draft shape, for edit-mode's
 * initial load. Master ids come back already resolved to names (branch,
 * supplier, ports, clearing agent are nested objects on the response), so no
 * master list is needed here — only draftToPayload needs one, going the other
 * way.
 */
export function apiToDraft(c: ApiConsignment): ConsignmentDraft {
  return {
    ...DRAFT_DEFAULT_VALUES,
    systemId: String(c.id),
    // Display only — the wizard's step chips name the consignment by it. It is
    // never sent back: the server owns the number (draftToPayload does not
    // carry it).
    consignmentNumber: c.consignment_number ?? '',

    branch: c.branch?.name ?? '',
    supplier: c.supplier?.name ?? '',
    origin: c.origin ?? '',
    currency: c.currency ?? '',
    consignmentType: (c.consignment_type ? (CONSIGNMENT_TYPE_FROM_API[c.consignment_type] ?? '') : '') as ConsignmentDraft['consignmentType'],
    incoterm: (c.incoterm ?? '') as ConsignmentDraft['incoterm'],
    poDate: c.po_date ?? '',
    // A BRIDGE, AND STEP 8 REMOVES IT. The wizard has ONE header-level input
    // for each of these; the data model now has one per line. Reading the
    // earliest line keeps that single input round-tripping — it writes back to
    // EVERY line (draftToPayload sends the header key, which the server fans
    // out), so reading one value and writing one value stays symmetric. Without
    // this the input would show blank on every reload while the stored value was
    // perfectly intact, which looks like data loss and is not.
    requisitionDate: earliestLineDate(c, 'requisition_date') ?? '',
    requiredDate: c.required_date ?? '',

    items: (c.items ?? []).filter((i) => !i.is_deleted).map((item, i) => ({
      ...emptyItem(`item-${c.id}-${item.id ?? i}`),
      backendId: item.id,
      // READ IN SO IT CAN BE SENT BACK OUT. The round trip is the whole point:
      // a line that loses its order line on the way through the wizard becomes
      // a new item on the order the next time it is saved.
      orderItemId: item.order_item_id ?? undefined,
      orderedQuantity: toNumber(item.ordered_quantity) ?? undefined,
      requisitionType: (item.requisition_type ? (REQ_TYPE_FROM_API[item.requisition_type] ?? undefined) : undefined) as DraftItem['requisitionType'],
      referenceNo: item.reference_number ?? '',
      jobNo: item.job_number ?? '',
      moNo: item.mo_number ?? '',
      othersDescription: item.description ?? '',
      itemId: item.item_id != null ? String(item.item_id) : '',
      itemName: item.item_name ?? '',
      placeholderName: item.placeholder_name ?? '',
      itemCode: item.item_code ?? '',
      specification: item.specification ?? '',
      quantity: toNumber(item.quantity) ?? undefined,
      uom: item.unit_of_measurement ?? '',
      batchNo: item.batch_no ?? '',
      hsCode: item.hs_code ?? '',
      foreignUnitPrice: toNumber(item.unit_price) ?? undefined,
      netWeight: toNumber(item.net_weight) ?? undefined,
      grossWeight: toNumber(item.gross_weight) ?? undefined,
      length: toNumber(item.length) ?? undefined,
      width: toNumber(item.width) ?? undefined,
      height: toNumber(item.height) ?? undefined,
    })),

    paymentInstrument: (c.payment_instrument ?? '') as ConsignmentDraft['paymentInstrument'],
    instrumentNo: c.instrument_number ?? '',
    instrumentDate: c.opening_or_retirement_date ?? '',
    exchangeRate: toNumber(c.exchange_rate) ?? undefined,
    rateDate: c.rate_booked_on ?? '',
    rateSource: c.rate_source ?? '',

    modeOfShipment: (c.mode_of_shipment ?? '') as ConsignmentDraft['modeOfShipment'],
    portOfLoading: c.loading_port?.name ?? '',
    portOfDelivery: c.delivery_port?.name ?? '',
    readinessDate: c.cargo_readiness_date ?? '',
    etd: c.etd ?? '',
    eta: c.eta ?? '',
    etaWorks: c.eta_works ?? '',
    // Read-only chain built from eta_revisions; the wizard shows it but never
    // edits it directly (a new ETA change is captured by simply changing the
    // `eta` field — the backend appends the revision row on save).
    etaRevisions: (c.eta_revisions ?? [])
      .filter((r) => r.eta_type === 'eta')
      .map((r) => ({
        id: String(r.id),
        from: r.previous_eta ?? '',
        to: r.new_eta ?? '',
        reason: r.cause_of_revision ?? '',
        changedBy: '',
        changedAt: '',
      })),

    payments: (c.payments ?? []).filter((p) => !p.is_deleted).map((payment, i) => ({
      ...emptyPayment(`pay-${c.id}-${payment.id ?? i}`),
      backendId: payment.id,
      date: payment.retirement_date ?? '',
      value: toNumber(payment.value) ?? undefined,
      exchangeRate: toNumber(payment.payment_exchange_rate) ?? undefined,
      status: (payment.status === 'Paid' ? 'Paid' : 'Unpaid'),
      reference: payment.bank_reference ?? '',
      bankCharges: toNumber(payment.bank_charges) ?? undefined,
    })),

    status: (c.current_status ?? '') as ConsignmentDraft['status'],
    statusHistory: (c.status_updates ?? []).map((s) => ({
      id: String(s.id),
      from: s.previous_status,
      to: (s.new_status ?? '') as ConsignmentDraft['statusHistory'][number]['to'],
      effectiveDate: s.effective_date ?? '',
      note: s.remarks ?? '',
      changedBy: '',
      changedAt: '',
    })),
    systemRemarks: c.system_remarks ?? '',
    userRemarks: c.remarks ?? '',

    clearingAgent: c.clearing_agent?.name ?? '',
    gdNumber: c.gd_number ?? '',
    gdDate: c.gd_filing_date ?? '',
    freeDays: c.free_days_allowed ?? undefined,
    gateOutDate: c.gate_out_date ?? '',
    demurrageCost: toNumber(c.demurrage_or_detention_paid) ?? undefined,
    containerDetention: toNumber(c.container_detention) ?? undefined,

    // An existing record found through the API has necessarily been saved at
    // least once — treat it as submitted-or-draft per what the server says,
    // never silently reset to a fresh draft.
    recordState: c.record_state === SUBMITTED ? SUBMITTED : DRAFT_DEFAULT_VALUES.recordState,
    isDeleted: c.is_deleted,
    createdBy: c.created_by ?? '',
  }
}
