import { apiFetch, apiFetchBlob } from './client'

/**
 * Logistics (orders) against the real backend — `/logistics`.
 *
 * Transport only: query building, the response envelope, the Excel download.
 * Turning a backend record into the shape the list table draws is
 * logisticsMap.ts's job — the same split imports uses.
 *
 * Envelope is `{ status_code, detail, data, pagination }`, matching the other
 * data-entry modules.
 *
 * SCOPE: orders only. The Service Jobs tab (import-FOB feed + customer rework)
 * is still on mock data — it has no backend at all yet — so nothing here
 * touches it.
 */

export interface ApiLogisticsItem {
  id: number
  consignment_id: number
  job_no: string | null
  item_detail: string | null
  quantity: string | number | null
  unit_weight: string | number | null
  gross_weight: string | number | null
  planned_rfd_date: string | null
  actual_rfd_date: string | null
  /** FE-driven nested collection, stored whole as JSON. */
  rfd_history: unknown
  is_deleted: boolean
}

export interface ApiLogisticsPackage {
  id: number
  consignment_id: number
  colour_code: string | null
  packing_works: string | null
  packing_ready_date: string | null
  packing_date: string | null
  quoted_packing_cost: string | number | null
  actual_packing_cost: string | number | null
  gross_weight: string | number | null
  status: string | null
  /** Cross-batch allocations, stored whole as JSON. */
  allocations: unknown
  is_deleted: boolean
}

export interface ApiLogisticsContainer {
  id: number
  consignment_id: number
  container_no: string | null
  container_type: string | null
  is_deleted: boolean
}

export interface ApiLogisticsOrder {
  id: number
  order_type: string | null
  department: string | null
  /** 'standard' (Orders tab) or 'rework' (Service Jobs). Set once at creation
   *  from whichever flow was entered; the update route ignores it. */
  job_kind: string
  /** EFS / Regular. Null on every loaded row — the workbooks have no such
   *  column — so the UI must show a gap rather than assume "Regular". */
  shipment_mode: string | null
  origin_country: string | null
  origin_city: string | null
  origin_province: string | null
  customer_name: string | null
  mo_no: string | null
  batch_no: number | null
  batch_label: string | null
  incoterm: string | null
  pol: string | null
  pod: string | null
  shipping_line: string | null
  clearing_agent: string | null
  booking_no: string | null
  port_in_date: string | null
  etd_sailing_date: string | null
  cro_arrival_date: string | null
  actual_arrival_date: string | null

  // named expenditure columns
  packing_cost: string | number | null
  transportation_charges: string | number | null
  container_detention: string | number | null
  insurance: string | number | null
  trucking_lhr_to_khi: string | number | null
  fumigation_cost: string | number | null
  lashing: string | number | null
  qfl_charges: string | number | null
  qfl_container_movement: string | number | null
  custom_clearance_charges: string | number | null
  port_charges: string | number | null
  dhl_charges: string | number | null
  sea_air_freight: string | number | null

  current_status: string | null
  effective_date: string | null
  gate_out_date: string | null
  sent_to_trucking: boolean
  /** Header remarks feed, stored whole as JSON. */
  remarks_log: unknown
  /** Generated server-side from status_updates, the trucking hand-off and
   *  every item's RFD change log — never stored, never sent back. */
  system_remarks: string | null

  record_state: string
  is_locked: boolean
  is_deleted: boolean
  created_by: string | null
  created_by_id: number | null
  created_at: string | null
  /** The named gaps that stop this order being submitted — same rule set
   *  /submit enforces, so a disabled Submit and a failed submit agree. */
  missing_fields: string[]

  items: ApiLogisticsItem[]
  packages: ApiLogisticsPackage[]
  containers: ApiLogisticsContainer[]
}

/* ------------------------------------------------------------ write shapes
 * Mirrors app/logistics/schemas.py field-for-field. Almost everything is
 * optional so a half-filled order still saves as a draft — the strict rules
 * only run on /submit.
 *
 * `id` on a line means "this row already exists, update it"; omitting it
 * means "new row". A line the payload leaves out entirely is treated as
 * DELETED by the update route's diff, which is why every save must send the
 * whole collection.
 */

export interface LogisticsItemPayload {
  id?: number | null
  job_no?: string
  item_detail?: string
  quantity?: number
  unit_weight?: number
  gross_weight?: number
  planned_rfd_date?: string
  actual_rfd_date?: string
  rfd_history?: unknown[]
}

export interface LogisticsPackagePayload {
  id?: number | null
  colour_code?: string
  packing_works?: string
  packing_ready_date?: string
  packing_date?: string
  quoted_packing_cost?: number
  actual_packing_cost?: number
  gross_weight?: number
  status?: string
  allocations?: unknown[]
}

export interface LogisticsContainerPayload {
  id?: number | null
  container_no?: string
  container_type?: string
}

export interface LogisticsPayload {
  order_type?: string
  department?: string
  /** CREATE only. Says which flow the record was started from — the server
   *  can't infer that. Ignored by the update route, so it never changes. */
  job_kind?: string
  shipment_mode?: string
  origin_country?: string
  origin_city?: string
  origin_province?: string
  customer_name?: string
  mo_no?: string
  batch_no?: number
  batch_label?: string
  incoterm?: string

  pol?: string
  pod?: string
  shipping_line?: string
  clearing_agent?: string
  booking_no?: string
  port_in_date?: string
  etd_sailing_date?: string
  cro_arrival_date?: string
  actual_arrival_date?: string

  packing_cost?: number
  transportation_charges?: number
  container_detention?: number
  insurance?: number
  trucking_lhr_to_khi?: number
  fumigation_cost?: number
  lashing?: number
  qfl_charges?: number
  qfl_container_movement?: number
  custom_clearance_charges?: number
  port_charges?: number
  dhl_charges?: number
  sea_air_freight?: number

  current_status?: string
  effective_date?: string
  gate_out_date?: string
  sent_to_trucking?: boolean
  remarks_log?: unknown[]

  items: LogisticsItemPayload[]
  packages: LogisticsPackagePayload[]
  containers: LogisticsContainerPayload[]
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
  data: ApiLogisticsOrder[]
  pagination: Pagination
}

interface DetailEnvelope {
  status_code: number
  detail: string
  data: ApiLogisticsOrder
}

interface OptionsEnvelope {
  status_code: number
  detail: string
  data: {
    statuses: { value: string; canonical: boolean }[]
    order_types: { value: string; canonical: boolean }[]
    customers: string[]
    departments: string[]
  }
}

/**
 * Everything the list screen can narrow by — a 1:1 match with what
 * GET /logistics/ accepts. Empty arrays / undefined are omitted, so an
 * untouched filter never appears in the query.
 *
 * Note there is deliberately no `includeClosed`: unlike imports, a delivered
 * (closed) order is NOT hidden from this list — it stays visible and simply
 * reports "Closed" in its own column. The backend list has no such param
 * either, so the two already agree.
 */
export interface LogisticsQuery {
  page?: number
  pageSize?: number
  status?: string[]
  orderType?: string[]
  customer?: string[]
  gateOutFrom?: string
  gateOutTo?: string
  includeDeleted?: boolean
  search?: string
  /** 'standard' (Orders, the server-side default), 'rework' (Service Jobs) or
   *  'all'. Not multi-select — a record is one kind or the other. */
  jobKind?: 'standard' | 'rework' | 'all'
}

function buildQuery(q: LogisticsQuery): URLSearchParams {
  const params = new URLSearchParams()

  if (q.page != null) params.set('page', String(q.page))
  if (q.pageSize != null) params.set('page_size', String(q.pageSize))
  if (q.includeDeleted) params.set('include_deleted', 'true')
  if (q.gateOutFrom) params.set('gate_out_from', q.gateOutFrom)
  if (q.gateOutTo) params.set('gate_out_to', q.gateOutTo)
  if (q.search?.trim()) params.set('q', q.search.trim())
  if (q.jobKind) params.set('job_kind', q.jobKind)

  // Multi-selects go out as repeated params — the backend reads them as IN.
  q.status?.forEach((v) => params.append('status', v))
  q.orderType?.forEach((v) => params.append('order_type', v))
  q.customer?.forEach((v) => params.append('customer', v))

  return params
}

export async function listLogisticsOrders(query: LogisticsQuery = {}) {
  const params = buildQuery(query)
  const res = await apiFetch<ListEnvelope>(`/logistics/?${params}`)
  return { rows: res.data, pagination: res.pagination }
}

export async function getLogisticsOrder(id: number | string): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>(`/logistics/${id}`)
  return res.data
}

/** Dropdown values built from what is actually stored — there is no customer
 *  master, so the only honest source for that filter is the DISTINCT. */
export async function fetchLogisticsFilterOptions() {
  const res = await apiFetch<OptionsEnvelope>('/logistics/filter-options')
  return res.data
}

/* ---------------------------------------------------------------- writes */

/** Draft save, first time — POST /logistics/. */
export async function createLogisticsOrder(payload: LogisticsPayload): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>('/logistics/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return res.data
}

/** Draft save, every time after — PUT /logistics/{id}. Send the WHOLE current
 *  draft (items/packages/containers included) every time: the update route
 *  diffs against what it already has, and a line missing from the payload is
 *  treated as deleted. */
export async function updateLogisticsOrder(
  id: number | string, payload: LogisticsPayload,
): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>(`/logistics/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return res.data
}

/** POST /logistics/{id}/submit — runs the full rule set server-side and only
 *  flips record_state to 'submitted' if nothing is missing. A 422 carries
 *  `{message, errors[]}`; parse it with parseSubmitErrors(). */
export async function submitLogisticsOrder(id: number | string): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>(`/logistics/${id}/submit`, { method: 'POST' })
  return res.data
}

/**
 * Soft delete, and its undo.
 *
 * NOTHING IS EVER HARD-DELETED (see CLAUDE.md): the row keeps its id, its
 * children and its change history, and only `is_deleted` flips. That is what
 * makes undo a real operation rather than a re-entry — and why a deleted record
 * still has to be reachable, since a list that hides it leaves the undo
 * endpoint with no way to be called. `includeDeleted` on the list query is what
 * brings them back; it already existed and nothing had ever asked for it.
 */
export async function deleteLogisticsOrder(id: number | string): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>(`/logistics/${id}`, { method: 'DELETE' })
  return res.data
}

export async function undoDeleteLogisticsOrder(id: number | string): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>(`/logistics/undo-delete/${id}`, { method: 'POST' })
  return res.data
}

/** POST /logistics/{id}/reopen — admin-only server-side; clears is_locked. */
export async function reopenLogisticsOrder(id: number | string): Promise<ApiLogisticsOrder> {
  const res = await apiFetch<DetailEnvelope>(`/logistics/${id}/reopen`, { method: 'POST' })
  return res.data
}

/**
 * An import consignment that imports handed to logistics
 * (`sent_to_logistics_at`). Read-through only — its home stays imports, so the
 * row links back to the source consignment rather than opening anything here.
 */
export interface ApiImportFobJob {
  source: string
  source_ref: string
  consignment_id: number
  instrument_number: string | null
  supplier: string | null
  origin: string | null
  item_summary: string | null
  status: string | null
  clearing_agent: string | null
  sent_at: string | null
}

/** GET /logistics/import-fob-jobs — the Import FOB half of Service Jobs. */
export async function getImportFobJobs(): Promise<ApiImportFobJob[]> {
  const res = await apiFetch<{ status_code: number; detail: string; data: ApiImportFobJob[]; total: number }>(
    '/logistics/import-fob-jobs',
  )
  return res.data
}

/** One trucking job created from this order. Only the fields the logistics
 *  read-through panel shows — the trucking module owns the full shape. */
export interface ApiLinkedTruckingJob {
  id: number
  transporter_name: string | null
  vehicles: { id: number; tracking_status: string | null; is_deleted: boolean }[]
}

/** GET /logistics/{id}/trucking-jobs — the reverse of "Send to Trucking":
 *  which jobs were created from this order (source "from-logistics"). */
export async function getLinkedTruckingJobs(id: number | string): Promise<ApiLinkedTruckingJob[]> {
  const res = await apiFetch<{ status_code: number; detail: string; data: ApiLinkedTruckingJob[]; total: number }>(
    `/logistics/${id}/trucking-jobs`,
  )
  return res.data
}

export interface SubmitErrorBody {
  message: string
  errors: string[]
}

/** The submit route's structured 422 body, or null if this wasn't one. */
export function parseSubmitErrors(detail: unknown): SubmitErrorBody | null {
  if (detail && typeof detail === 'object' && Array.isArray((detail as SubmitErrorBody).errors)) {
    return detail as SubmitErrorBody
  }
  return null
}

/* -------------------------------------------------------- change history */

export interface ApiFieldChange {
  old_value: unknown
  new_value: unknown
}

/** A child-row diff: per-column {old,new} plus a bare numeric `id` naming the
 *  row (the id is deliberately NOT a change object — see apply_updates). */
export type ApiChildChange = Record<string, ApiFieldChange | number | undefined> & { id?: number }

export interface ApiLogisticsHistoryPayload {
  fields?: Record<string, ApiFieldChange>
  items?: ApiChildChange[]
  packages?: ApiChildChange[]
  containers?: ApiChildChange[]
  new_items?: Record<string, unknown>[]
  new_packages?: Record<string, unknown>[]
  new_containers?: Record<string, unknown>[]
  deleted_items?: Record<string, unknown>[]
  deleted_packages?: Record<string, unknown>[]
  deleted_containers?: Record<string, unknown>[]
}

export interface ApiLogisticsHistoryEntry {
  id: number
  consignment_id: number
  change_type: string
  history: ApiLogisticsHistoryPayload
  changed_by_id: number | null
  changed_by: string | null
  changed_at: string | null
  is_reverted: boolean
  reverted_by_id: number | null
  reverted_by: string | null
  reverted_at: string | null
  is_revert: boolean
}

/**
 * GET /logistics/change-history/{id} — one page of change entries, newest
 * first. `includeReverted` defaults to TRUE here even though the backend
 * defaults it to false: the history screen greys reverted entries out rather
 * than hiding them.
 */
export async function getLogisticsChangeHistory(
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
    data: ApiLogisticsHistoryEntry[]
    pagination: Pagination
  }>(`/logistics/change-history/${id}?${params}`)
  return { entries: res.data, pagination: res.pagination }
}

/** PUT /logistics/revert-update/{id}/{historyId} — undoes one change. 400s
 *  unless it is the newest not-yet-reverted entry (the backend's LIFO rule). */
export async function revertLogisticsUpdate(id: number | string, historyId: number | string) {
  const res = await apiFetch<DetailEnvelope>(
    `/logistics/revert-update/${id}/${historyId}`,
    { method: 'PUT' },
  )
  return res.data
}

/** The .xlsx of the CURRENT filtered set (no paging) — same query params as
 *  the list, so what you export is what you see. */
export async function exportLogisticsExcel(query: LogisticsQuery = {}): Promise<Blob> {
  const params = buildQuery(query)
  // Paging is meaningless for an export; the backend ignores it, but don't send it.
  params.delete('page')
  params.delete('page_size')
  return apiFetchBlob(`/logistics/export?${params}`)
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
