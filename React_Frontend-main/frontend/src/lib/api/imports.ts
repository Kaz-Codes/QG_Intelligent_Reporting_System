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
  item_id: number | null
  item_code: string | null
  item_name: string | null
  placeholder_name: string | null
  specification: string | null
  hs_code: string | null
  quantity: string | number | null
  unit_price: string | number | null
  unit_of_measurement: string | null
  batch_no: string | null
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

export interface ApiConsignment {
  id: number
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
  requisition_date: string | null
  required_date: string | null
  cargo_readiness_date: string | null
  etd: string | null
  eta: string | null
  eta_works: string | null
  payment_instrument: string | null
  instrument_number: string | null
  opening_or_retirement_date: string | null
  exchange_rate: string | number | null
  rate_booked_on: string | null
  rate_source: string | null
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
  eta_revisions: ApiEtaRevision[]
  status_updates: ApiStatusUpdate[]
  missing_fields: string[]
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
  /** Only records still incomplete (server-side: record_state === 'draft'). */
  missingOnly?: boolean
  /** Only consignments handed to logistics and/or trucking — the "Forwarded" view. */
  sentOnly?: boolean
  includeDeleted?: boolean
  etdFrom?: string
  etdTo?: string
  search?: string
}

function buildQuery(q: ConsignmentQuery): URLSearchParams {
  const params = new URLSearchParams()

  if (q.page != null) params.set('page', String(q.page))
  if (q.pageSize != null) params.set('page_size', String(q.pageSize))
  // 'all' is the frontend's "no stage filter" sentinel; the backend treats it
  // the same way, but leaving it off keeps the URL clean.
  if (q.stage && q.stage !== 'all') params.set('stage', q.stage)
  if (q.includeClosed) params.set('include_closed', 'true')
  if (q.missingOnly) params.set('missing_only', 'true')
  if (q.sentOnly) params.set('sent_only', 'true')
  if (q.includeDeleted) params.set('include_deleted', 'true')
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

export interface ConsignmentItemPayload {
  id?: number | null
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

/** POST /consignments/{id}/submit — runs the full rule set server-side and
 *  only flips record_state to 'submitted' if nothing is missing. A 422's
 *  ApiError.message is a JSON string; parse it with parseSubmitErrors(). */
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
export async function revertConsignmentUpdate(id: number | string, historyId: number | string) {
  const res = await apiFetch<DetailEnvelope>(
    `/consignments/revert-update/${id}/${historyId}`,
    { method: 'PUT' },
  )
  return res.data
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

/** Dropdown values built from what is actually stored — see the backend route
 *  for why this can't just be the enums. */
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
