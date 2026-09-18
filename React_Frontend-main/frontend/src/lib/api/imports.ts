import { apiFetch, apiFetchBlob } from './client'

/**
 * Imports (consignments) against the real backend — `/consignments`.
 *
 * This module module is only the transport: query building, the response
 * envelope, and the Excel download. Turning a backend record into the shape the
 * list table draws is importsMap.ts's job.
 *
 * The data modules answer with `{ status_code, detail, data, pagination }` —
 * note this differs from the accounts/logs modules' `{ status, message, data }`.
 */

export interface ApiConsignmentItem {
  id: number
  /** The order line above this one. Echoed back on every save so a later
   *  batch's line stays attached to what the order bought. */
  order_item_id: number | null
  ordered_quantity: string | number | null
  item_id: number | null
  item_code: string | null
  item_name: string | null
  placeholder_name: string | null
  specification: string | null
  hs_code: string | null
  quantity: string | number | null
  /** How the line is priced — `quantity` or `weight` (enums.PriceBasis).
   *  NOT NULL server-side with a `quantity` default. */
  price_basis: string | null
  unit_price: string | number | null
  /** Per kilogram; read only under the weight basis. */
  weight_unit_price: string | number | null
  /** Kilograms PER UNIT — not the line's total, which is `net_weight`. */
  unit_weight: string | number | null
  unit_of_measurement: string | null
  batch_no: string | null
  /** THE DEMAND THIS LINE CAME FROM. Both live on the order line above this
   *  shipment line, not on the line itself, and the server adds them to the
   *  item payload explicitly (serialize_items) — a mapper walk over
   *  `consignment_items` cannot see them. */
  requisition_date: string | null
  required_date: string | null
  requisition_type: string | null
  reference_number: string | null
  job_number: string | null
  mo_number: string | null
  description: string | null
  net_weight: string | number | null
  gross_weight: string | number | null
  length: string | number | null
  width: string | number | null
  height: string | number | null
  elc: string | number | null
  alc: string | number | null
  is_deleted: boolean
}

export interface ApiMaster {
  id: number
  name: string
  [key: string]: unknown
}

export interface ApiEtaRevision {
  id: number
  eta_type: string | null
  previous_eta: string | null
  new_eta: string | null
  cause_of_revision: string | null
}

export interface ApiStatusUpdate {
  id: number
  previous_status: string | null
  new_status: string | null
  effective_date: string | null
  remarks: string | null
}

export interface ApiPayment {
  id: number
  retirement_date: string | null
  value: string | number | null
  payment_exchange_rate: string | number | null
  bank_charges: string | number | null
  status: string | null
  bank_reference: string | null
  is_deleted: boolean
}

/** An amendment to the LC. `value` is a SIGNED DELTA to the LC amount, not the
 *  revised total — a reduction is negative. Nothing sums it. */
export interface ApiAddendum {
  id: number
  addendum_date: string | null
  reference: string | null
  value: string | number | null
  description: string | null
  bank_charges: string | number | null
  is_deleted: boolean
}

export interface ApiConsignment {
  /** The row's PRIMARY KEY. A link target and a React key — never a display
   *  number. On a later batch the id and the number are different integers
   *  (design 0.4), so rendering this is how `184` reaches a screen. */
  id: number
  /** THE SHIPMENT'S NUMBER: `177`, or `177-2` once the order has split.
   *  Derived on the server from the founding batch's id, `batches_ever` and
   *  this row's sequence (order_view.consignment_number) — the suffix rule is
   *  the one thing a front-end copy would get wrong first. Null only if a row
   *  somehow has no order above it; `batch_group_id` is NOT NULL, so it does
   *  not happen. */
  consignment_number: string | null
  /** Does this row's ORDER still have quantity nobody has put in a batch?
   *
   *  `null` means NOT ASKED FOR, which is not the same as `false` — only a
   *  list fetched with `include_batch_context=true` carries a boolean. Read it
   *  as "no highlight" when null, never as "fully allocated". */
  has_pending_allocation: boolean | null
  /** The ORDER this batch belongs to, and its place in the order. Two batches
   *  of one LC share the group id and differ by the sequence. */
  batch_group_id: number | null
  batch_sequence: number | null
  branch: ApiMaster | null
  supplier: ApiMaster | null
  clearing_agent: ApiMaster | null
  loading_port: ApiMaster | null
  delivery_port: ApiMaster | null
  works: string | null
  origin: string | null
  po_date: string | null
  currency: string | null
  consignment_type: string | null
  incoterm: string | null
  mode_of_shipment: string | null
  /** THE EARLIEST required date across this batch's item lines — computed by the
   *  server, not a stored header column. The list payload carries no lines, so
   *  `requiredDelayDays` needs the minimum supplied here. */
  required_date: string | null
  /** NOT SENT ANY MORE. The requisition date moved onto the item lines (one
   *  order can carry lines requisitioned months apart), and unlike
   *  `required_date` it has no header-level consumer so nothing aggregates it.
   *  Read it from `items[].requisition_date`. Still ACCEPTED on write, where it
   *  fans onto every line — see draftToPayload. */
  requisition_date?: undefined
  cargo_readiness_date: string | null
  etd: string | null
  eta: string | null
  eta_works: string | null
  payment_instrument: string | null
  instrument_number: string | null
  /** The ORDER's payment reference, mode + number: `lc68756`. Built by the
   *  server (order_view.payment_reference), so this is the SAME string the
   *  notifications, dashboards and export use. Do NOT rebuild it here from
   *  payment_instrument + instrument_number: that is an eleventh copy of a
   *  rule nothing on this side can check against the other ten, and it
   *  would have to duplicate the cadCAD guard too. */
  payment_reference: string | null
  opening_or_retirement_date: string | null
  exchange_rate: string | number | null
  rate_booked_on: string | null
  rate_source: string | null
  /** LC-LEVEL, on the order. Insurance is taken out once per consignment, not
   *  per shipment, so every batch of an order reports the same figure. */
  insurance_amount: string | number | null
  foreign_total: string | number | null
  pkr_total: string | number | null
  current_status: string | null
  effective_date: string | null
  remarks: string | null
  system_remarks: string | null
  gd_number: string | null
  gd_filing_date: string | null
  free_days_allowed: number | null
  gate_out_date: string | null
  demurrage_or_detention_paid: string | number | null
  container_detention: string | number | null
  items: ApiConsignmentItem[]
  payments: ApiPayment[]
  /** The ORDER's addenda, published on every batch like `payments`. Optional
   *  because a list row's serializer emits it too but an older cached payload
   *  may not carry it. */
  addenda?: ApiAddendum[]
  /** DETAIL PAYLOAD ONLY — both read `batch_group` collections the list query
   *  does not load, so they are absent (undefined) on a list row. */
  allocation?: ApiAllocationLine[]
  group_frozen?: ApiGroupFrozen
  eta_revisions: ApiEtaRevision[]
  status_updates: ApiStatusUpdate[]
  /** Cross-module hand-off. NULL = not sent. Set only by the send routes. */
  sent_to_logistics_at: string | null
  sent_to_trucking_at: string | null
  record_state: string
  is_locked: boolean
  is_deleted: boolean
  created_by: string | null
  created_by_id: number | null
  created_at: string | null
}

/**
 * One change-history row from GET /consignments/change-history/{id}.
 *
 * `history` is the pre-change snapshot the update route wrote — the OLD
 * values, keyed the same way the backend stores them:
 *
 *   fields          { column: { old_value, new_value } }  header columns
 *   items/payments  [ { column: { old_value, new_value }, ..., id } ]
 *   new_*           [ fully serialized row ]  — added by this change
 *   deleted_*       [ fully serialized row ]  — removed by this change
 *
 * Turning that into the card's section/collection shape is importsChangeHistoryMap.ts's job.
 */
export interface ApiFieldChange {
  old_value: unknown
  new_value: unknown
}

/** A child-row diff: per-column {old,new} plus a bare numeric `id` naming the
 *  row. The id is deliberately NOT a change object — see apply_updates. */
export type ApiChildChange = Record<string, ApiFieldChange | number | undefined> & { id?: number }

export interface ApiChangeHistoryPayload {
  fields?: Record<string, ApiFieldChange>
  items?: ApiChildChange[]
  payments?: ApiChildChange[]
  new_items?: Record<string, unknown>[]
  new_payments?: Record<string, unknown>[]
  deleted_items?: Record<string, unknown>[]
  deleted_payments?: Record<string, unknown>[]
  /** ADDENDA — optional like the rest, and genuinely absent on every history
   *  row written before step 9 part 2. The backend reads these three with
   *  `.get` for that reason. */
  addenda?: ApiChildChange[]
  new_addenda?: Record<string, unknown>[]
  deleted_addenda?: Record<string, unknown>[]
}

export interface ApiChangeHistoryEntry {
  id: number
  consignment_id: number
  change_type: string
  history: ApiChangeHistoryPayload
  changed_by_id: number | null
  changed_by: string | null
  changed_at: string | null
  is_reverted: boolean
  reverted_by_id: number | null
  reverted_by: string | null
  reverted_at: string | null
  is_revert: boolean
}

export interface Pagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}

interface ListEnvelope {
  status_code: number
  detail: string
  data: ApiConsignment[]
  pagination: Pagination
}

interface DetailEnvelope {
  status_code: number
  detail: string
  data: ApiConsignment
}

interface OptionsEnvelope {
  status_code: number
  detail: string
  data: {
    statuses: { value: string; canonical: boolean }[]
    branches: { id: number; name: string }[]
    suppliers: { id: number; name: string }[]
    requisition_types: string[]
  }
}

/** Everything the list screen can narrow by. Empty arrays / undefined are
 *  omitted, so an untouched filter never appears in the query. */
export interface ConsignmentQuery {
  page?: number
  pageSize?: number
  /** Stage strip. 'all' means no stage narrowing. */
  stage?: string
  status?: string[]
  branchId?: number[]
  supplierId?: number[]
  requisitionType?: string[]
  /** Show the closed status ("Arrived at Works") too. */
  includeClosed?: boolean
  /** Only records nobody has marked finished (server-side: record_state === 'draft'). */
  draftsOnly?: boolean
  /** Only consignments handed to logistics and/or trucking — the "Forwarded" view. */
  sentOnly?: boolean
  includeDeleted?: boolean
  etdFrom?: string
  etdTo?: string
  search?: string
  /** Ask for the batching fields — currently `has_pending_allocation` on every
   *  row. Off by default because it costs a correlated EXISTS over a second
   *  table per page, and only the imports list wants it. */
  includeBatchContext?: boolean
}

function buildQuery(q: ConsignmentQuery): URLSearchParams {
  const params = new URLSearchParams()

  if (q.page != null) params.set('page', String(q.page))
  if (q.pageSize != null) params.set('page_size', String(q.pageSize))
  // 'all' is the frontend's "no stage filter" sentinel; the backend treats it
  // the same way, but leaving it off keeps the URL clean.
  if (q.stage && q.stage !== 'all') params.set('stage', q.stage)
  if (q.includeClosed) params.set('include_closed', 'true')
  if (q.draftsOnly) params.set('drafts_only', 'true')
  if (q.sentOnly) params.set('sent_only', 'true')
  if (q.includeDeleted) params.set('include_deleted', 'true')
  if (q.includeBatchContext) params.set('include_batch_context', 'true')
  if (q.etdFrom) params.set('etd_from', q.etdFrom)
  if (q.etdTo) params.set('etd_to', q.etdTo)
  if (q.search?.trim()) params.set('q', q.search.trim())

  // Multi-selects go out as repeated params — the backend reads them as IN.
  q.status?.forEach((v) => params.append('status', v))
  q.branchId?.forEach((v) => params.append('branch_id', String(v)))
  q.supplierId?.forEach((v) => params.append('supplier_id', String(v)))
  q.requisitionType?.forEach((v) => params.append('requisition_type', v))

  return params
}

export async function listConsignments(query: ConsignmentQuery = {}) {
  const params = buildQuery(query)
  const res = await apiFetch<ListEnvelope>(`/consignments/?${params.toString()}`)
  return { rows: res.data ?? [], pagination: res.pagination }
}

/** One consignment, in full — for the detail page and the wizard's edit-mode
 *  bridge. A 404 from the backend (no such id, or it belongs to nobody once
 *  soft-deleted rows are excluded) surfaces as an ApiError the caller can
 *  branch on. */
export async function getConsignment(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}`)
  return res.data
}

//-----------------------------------------------------
// WIZARD WRITES — create (draft), update (draft), submit
//
// Payload shapes mirror app/imports/schemas.py's ConsignmentSchema /
// ConsignmentItemSchema / ConsignmentPaymentSchema field-for-field (snake_case,
// nullable everywhere — a draft can be missing anything). Building one of these
// from the wizard's camelCase form state is importsMap.ts's draftToPayload().
//-----------------------------------------------------

/** One order line's allocation, from the DETAIL payload's `allocation` block.
 *  Quantities arrive as strings (Decimal) or numbers depending on the driver. */
export interface ApiAllocationLine {
  order_item_id: number
  item: string | null
  item_code: string | null
  unit_of_measurement: string | null
  ordered_quantity: string | number | null
  allocated_quantity: string | number | null
  /** ordered - allocated, derived server-side. What Step 3 shows as pending
   *  and what a new batch may draw from. */
  outstanding_quantity: string | number | null
}

export interface ApiGroupFrozen {
  is_frozen: boolean
  frozen_by: { consignment_id: number; consignment_number: string | null } | null
  /** PAYLOAD KEYS (`branch_id`, not `works_branch_id`), so a form can match
   *  them to its own inputs. Tier 1 refuses everyone; Tier 2 refuses all but
   *  an admin. */
  hard: string[]
  admin: string[]
}

export interface ConsignmentItemPayload {
  id?: number | null
  /** WHICH ORDER LINE THIS BATCH LINE ALLOCATES AGAINST.
   *
   *  MUST BE SENT for any line on a later batch. Without it the server reads
   *  the line as a NEW item on the order and silently raises what the order
   *  bought — correct on the founding batch, wrong on every other one (design
   *  §3.7b finding 3). Since 8b-1 the server refuses it on a later batch
   *  rather than duplicating the order line, but the refusal is the backstop:
   *  sending the id is the fix. */
  order_item_id?: number | null
  /** What the ORDER bought, as opposed to what this batch carries. Optional:
   *  on a single-batch order the server keeps it in step with `quantity`, and
   *  stops doing so once the order splits. */
  ordered_quantity?: number | null
  item_id?: number | null
  item_name?: string | null
  placeholder_name?: string | null
  item_code?: string | null
  hs_code?: string | null
  specification?: string | null
  quantity?: number | null
  unit_of_measurement?: string | null
  batch_no?: string | null
  requisition_type?: string | null
  unit_price?: number | null
  price_basis?: string | null
  weight_unit_price?: number | null
  unit_weight?: number | null
  net_weight?: number | null
  gross_weight?: number | null
  length?: number | null
  width?: number | null
  height?: number | null
  elc?: number | null
  alc?: number | null
  reference_number?: string | null
  job_number?: string | null
  mo_number?: string | null
  description?: string | null
}

export interface ConsignmentPaymentPayload {
  id?: number | null
  retirement_date?: string | null
  value?: number | null
  payment_exchange_rate?: number | null
  bank_charges?: number | null
  status?: string | null
  bank_reference?: string | null
}

export interface ConsignmentAddendumPayload {
  id?: number | null
  addendum_date?: string | null
  reference?: string | null
  /** SIGNED — no `numGt0`/`numGe0` on the way out, or a reduction never
   *  reaches the server. */
  value?: number | null
  description?: string | null
  bank_charges?: number | null
}

export interface ConsignmentPayload {
  branch_id?: number | null
  supplier_id?: number | null
  origin?: string | null
  currency?: string | null
  consignment_type?: string | null
  incoterm?: string | null
  po_date?: string | null
  requisition_date?: string | null
  required_date?: string | null

  payment_instrument?: string | null
  instrument_number?: string | null
  opening_or_retirement_date?: string | null
  works?: string | null
  exchange_rate?: number | null
  rate_booked_on?: string | null
  rate_source?: string | null
  insurance_amount?: number | null

  mode_of_shipment?: string | null
  loading_port_id?: number | null
  delivery_port_id?: number | null
  cargo_readiness_date?: string | null
  etd?: string | null
  eta?: string | null
  eta_works?: string | null
  cause_of_revision?: string | null

  current_status?: string | null
  effective_date?: string | null
  remarks?: string | null

  clearing_agent_id?: number | null
  gd_number?: string | null
  gd_filing_date?: string | null
  free_days_allowed?: number | null
  gate_out_date?: string | null
  demurrage_or_detention_paid?: number | null
  container_detention?: number | null

  items: ConsignmentItemPayload[]
  payments: ConsignmentPaymentPayload[]
  addenda: ConsignmentAddendumPayload[]
}

interface SubmitErrorBody {
  message: string
  errors: string[]
}

/** The shape ApiError.detail takes when a submit fails validation — see
 *  submit_consignment.py's 422 (`detail: {message, errors}`). Every other
 *  ApiError from this module (404/423/500) has a plain string detail, so
 *  callers should check the return before trusting the shape. */
export function parseSubmitErrors(detail: unknown): SubmitErrorBody | null {
  if (detail && typeof detail === 'object' && Array.isArray((detail as SubmitErrorBody).errors)) {
    return detail as SubmitErrorBody
  }
  return null
}

/** Draft save, first time — POST /consignments/. Returns the created record
 *  (with its real id) so the wizard can move the URL off the placeholder. */
export async function createConsignment(payload: ConsignmentPayload): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>('/consignments/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return res.data
}

/** Draft save, every time after — PUT /consignments/{id}. Send the WHOLE
 *  current draft (items/payments included) every time: the update route diffs
 *  against what it already has, and a line missing from the payload is treated
 *  as deleted. */
export async function updateConsignmentApi(id: number | string, payload: ConsignmentPayload): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return res.data
}

/** POST /consignments/{id}/submit — flips record_state to 'submitted'.
 *
 *  That is ALL it does. There is no rule set in imports any more, so it cannot
 *  422 and it does not lock the record; a consignment closes on reaching
 *  "Arrived at Works", which is a PUT, not this. Logistics and trucking keep
 *  their rule sets and their 422s — this divergence is imports-only. */
export async function submitConsignmentApi(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}/submit`, { method: 'POST' })
  return res.data
}

/**
 * GET /consignments/change-history/{id} — one page of change entries,
 * newest first.
 *
 * `includeReverted` defaults to TRUE here even though the backend defaults it
 * to false: the history screen greys reverted entries out rather than hiding
 * them, and hiding them would also break the LIFO rule the UI enforces (it
 * has to see a reverted entry to know it is not the revertable one).
 */
export async function getConsignmentChangeHistory(
  id: number | string,
  { page = 1, pageSize = 5, includeReverted = true }: {
    page?: number; pageSize?: number; includeReverted?: boolean
  } = {},
) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
    include_reverted: String(includeReverted),
  })
  const res = await apiFetch<{
    status_code: number
    detail: string
    data: ApiChangeHistoryEntry[]
    pagination: Pagination
  }>(`/consignments/change-history/${id}?${params}`)
  return { entries: res.data, pagination: res.pagination }
}

/** PUT /consignments/revert-update/{id}/{historyId} — undoes one change.
 *  400s unless it is the newest not-yet-reverted entry (the backend's LIFO
 *  rule); the UI only ever offers the button on that entry. */
/** What a revert could NOT put back, and why — one entry per field.
 *
 *  Two kinds of skip share this channel because they are the same event to the
 *  person reading it: a column that has since been RETIRED, and a group field a
 *  closed batch has FROZEN. The reason travels with the key so the caller never
 *  has to look one up. */
export interface RevertOutcome {
  consignment: ApiConsignment
  /** The server's sentence, already naming what it could not restore. */
  detail: string
  skippedFields: string[]
  skippedDetail: Record<string, string>
}

/** PUT /consignments/revert-update/{id}/{historyId}
 *
 *  IT RETURNS THE SKIPS, AND THAT IS THE POINT. This used to return `res.data`
 *  alone, so `skipped_fields` — served by the API since part 4 — reached
 *  nobody: an operator whose revert restored four fields and refused a fifth
 *  was told "Consignment reverted" and had no way to find out which. */
export async function revertConsignmentUpdate(
  id: number | string, historyId: number | string,
): Promise<RevertOutcome> {
  const res = await apiFetch<DetailEnvelope & {
    skipped_fields?: string[]
    skipped_detail?: Record<string, string>
  }>(
    `/consignments/revert-update/${id}/${historyId}`,
    { method: 'PUT' },
  )
  return {
    consignment: res.data,
    detail: res.detail,
    skippedFields: res.skipped_fields ?? [],
    skippedDetail: res.skipped_detail ?? {},
  }
}

/**
 * Hand a consignment over to Logistics (shipping + clearing) or Trucking
 * (inland movement). An explicit act, not something inferred: being bought FOB
 * only makes a consignment ELIGIBLE — the backend 400s on any other incoterm,
 * and the trucking inbox reads the resulting timestamp rather than the
 * incoterm. The record stays in imports afterwards; these just stamp when it
 * was handed over.
 */
export async function sendToLogisticsApi(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}/send-to-logistics`, { method: 'POST' })
  return res.data
}

export async function sendToTruckingApi(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}/send-to-trucking`, { method: 'POST' })
  return res.data
}

/** POST /consignments/{id}/reopen — admin-only server-side (403 for anyone
 *  else); clears is_locked so the consignment can be edited again. */
export async function reopenConsignmentApi(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}/reopen`, { method: 'POST' })
  return res.data
}


/**
 * Soft delete, and its undo.
 *
 * NOTHING IS EVER HARD-DELETED (see CLAUDE.md): the row keeps its id, its
 * children and its change history, and only `is_deleted` flips. That is what
 * makes undo a real operation rather than a re-entry, and why a deleted record
 * still has to be reachable — a list that hides it leaves the undo endpoint
 * with no way to be called.
 *
 * The DELETED ROWS ARE FETCHED WITH `includeDeleted`, which the list query
 * already supported and nothing had ever asked for.
 */
export async function deleteConsignmentApi(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/${id}`, { method: 'DELETE' })
  return res.data
}

export async function undoDeleteConsignmentApi(id: number | string): Promise<ApiConsignment> {
  const res = await apiFetch<DetailEnvelope>(`/consignments/undo-delete/${id}`, { method: 'POST' })
  return res.data
}

/** Dropdown values built from what is actually stored — see the backend route
 *  for why this can't just be the enums. */
/** GET /consignments/{id}/batches — every live batch of this order, itself
 *  included, in sequence order.
 *
 *  Not a `batch_group_id` filter on the list: the list carries the screen's own
 *  filters, paging and `include_closed`, so "the siblings of this order" would
 *  come back a different set depending on what the user had selected. */
export async function getBatches(id: number | string): Promise<ApiConsignment[]> {
  const res = await apiFetch<{ status_code: number; detail: string; data: ApiConsignment[]; total: number }>(
    `/consignments/${id}/batches`,
  )
  return res.data
}

export interface BatchNumbering {
  order_number: string
  batches_ever: number
  /** True exactly on the split — the moment `177` became `177-1`. What the
   *  renumbering warning confirms against after the fact. */
  siblings_renumbered: boolean
  batches: {
    consignment_id: number
    batch_sequence: number
    consignment_number: string
    /** Null on the batch just created: it had no number a moment ago. */
    previous_consignment_number: string | null
  }[]
}

/** POST /consignments/{id}/batches — add an arrival to this order.
 *
 *  Takes allocations and NOTHING else. Route, schedule, clearance and status
 *  start empty and are entered afterwards through the ordinary PUT, because a
 *  later batch's shipping section starts blank (requirements, Step 3). */
export async function createBatchApi(
  id: number | string,
  allocations: { order_item_id: number; quantity: number }[],
): Promise<{ batch: ApiConsignment; numbering: BatchNumbering }> {
  const res = await apiFetch<{
    status_code: number; detail: string
    data: { batch: ApiConsignment; numbering: BatchNumbering }
  }>(`/consignments/${id}/batches`, {
    method: 'POST',
    body: JSON.stringify({ allocations }),
  })
  return res.data
}

export async function fetchFilterOptions() {
  const res = await apiFetch<OptionsEnvelope>('/consignments/filter-options')
  return res.data
}

/** The .xlsx of the CURRENT filtered set (no paging) — same query params as the
 *  list, so what you export is what you see. */
export async function exportConsignmentsExcel(query: ConsignmentQuery = {}): Promise<Blob> {
  const params = buildQuery(query)
  // Paging is meaningless for an export; the backend ignores it, but don't send it.
  params.delete('page')
  params.delete('page_size')
  return apiFetchBlob(`/consignments/export?${params.toString()}`)
}

/** Trigger a browser download for a fetched blob. */
export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
