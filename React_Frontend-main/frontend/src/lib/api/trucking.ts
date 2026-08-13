import { apiFetch, apiFetchBlob } from './client'

/**
 * Trucking (jobs) against the real backend — `/trucking`.
 *
 * Transport only: query building, the response envelope, the Excel download.
 * Turning a backend record into the shape the list draws is truckingMap.ts's
 * job — the same split imports and logistics use.
 *
 * One structural difference from the other two modules: a trucking job has NO
 * stored job-level status. Tracking is PER VEHICLE, and the job-level rollup
 * is derived (see truckingMap.rollupStatus). That is also what "closed" means
 * here — every vehicle Delivered, and the job submitted.
 */

export interface ApiTruckingVehicle {
  id: number
  consignment_id: number
  vehicle_number: string | null
  vehicle_type: string | null
  no_of_packages: number | null
  driver_phone: string | null
  net_weight: string | number | null
  gross_weight: string | number | null
  container_no: string | null
  container_type: string | null
  /** Going to load | Loading | On road | Delivered. */
  tracking_status: string | null
  /** FE-driven JSON: which logistics packages this truck carries. */
  package_refs: unknown
  /** FE-driven JSON: which import consignments this truck carries. */
  import_consignment_refs: unknown
  /** FE-driven JSON: how much of each item rides this truck. */
  item_allocations: unknown
  is_deleted: boolean
}

/** One item line on a trucking job. Not yet its own table server-side — see
 *  the `items` JSON column note on ApiTruckingJob. */
export interface ApiTruckingItem {
  item_ref?: string | null
  item_details: string | null
  quantity: string | number | null
  uom: string | null
  pickup: string | null
  destination: string | null
  reference_no: string | null
}

export interface ApiTruckingJob {
  id: number
  movement_type: string | null
  /** Where the job came from: 'from-logistics', 'from-import-fob', or
   *  'manual' for one entered by hand. */
  source: string | null
  source_ref: string | null
  taken_at: string | null
  /** Snapshot captured when the job took its open request. */
  taken_snapshot: unknown

  execution_date: string | null
  transporter_name: string | null
  /** The Transporter master row transporter_name resolves to server-side
   *  (helpers.resolve_transporter_id) — derived, never sent by the wizard. */
  transporter_id: number | null
  shifting_type: string | null
  /** Repeatable item lines, once the backend has an `items` JSON column;
   *  absent/null on rows saved before this existed. */
  items?: ApiTruckingItem[] | null
  item_details: string | null
  pickup: string | null
  destination: string | null
  reference_no: string | null

  quoted_freight: string | number | null
  actual_freight: string | number | null
  payment_status: string | null
  paid_amount: string | number | null
  detention: string | number | null

  dispatch_note_date: string | null
  eta_works: string | null
  remarks: string | null

  record_state: string
  is_locked: boolean
  is_deleted: boolean
  created_by: string | null
  created_by_id: number | null
  created_at: string | null
  /** Named gaps that stop this job being submitted. */
  missing_fields: string[]

  vehicles: ApiTruckingVehicle[]
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
  data: ApiTruckingJob[]
  pagination: Pagination
}

interface DetailEnvelope {
  status_code: number
  detail: string
  data: ApiTruckingJob
}

interface OptionsEnvelope {
  status_code: number
  detail: string
  data: {
    movement_types: { value: string; canonical: boolean }[]
    sources: string[]
    transporters: string[]
  }
}

/**
 * Everything the list screen can narrow by — a 1:1 match with what
 * GET /trucking/ accepts.
 *
 * Note `openOnly` and `pendingOnly` are the backend's own names for two
 * derived toggles: open = not yet closed, pending = still a draft.
 */
export interface TruckingQuery {
  page?: number
  pageSize?: number
  movementType?: string[]
  source?: string[]
  /** Only jobs that are not yet closed. */
  openOnly?: boolean
  /** Only drafts (record_state === 'draft'). */
  pendingOnly?: boolean
  includeDeleted?: boolean
  search?: string
}

function buildQuery(q: TruckingQuery): URLSearchParams {
  const params = new URLSearchParams()

  if (q.page != null) params.set('page', String(q.page))
  if (q.pageSize != null) params.set('page_size', String(q.pageSize))
  if (q.openOnly) params.set('open_only', 'true')
  if (q.pendingOnly) params.set('pending_only', 'true')
  if (q.includeDeleted) params.set('include_deleted', 'true')
  if (q.search?.trim()) params.set('q', q.search.trim())

  // Multi-selects go out as repeated params — the backend reads them as IN.
  q.movementType?.forEach((v) => params.append('movement_type', v))
  q.source?.forEach((v) => params.append('source', v))

  return params
}

export async function listTruckingJobs(query: TruckingQuery = {}) {
  const params = buildQuery(query)
  const res = await apiFetch<ListEnvelope>(`/trucking/?${params}`)
  return { rows: res.data, pagination: res.pagination }
}

export async function getTruckingJob(id: number | string): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>(`/trucking/${id}`)
  return res.data
}

/** Dropdown values built from what is actually stored — transporter is free
 *  text on the job, so the DISTINCT is the only honest source. */
export async function fetchTruckingFilterOptions() {
  const res = await apiFetch<OptionsEnvelope>('/trucking/filter-options')
  return res.data
}

/** The .xlsx of the CURRENT filtered set (no paging). */
export async function exportTruckingExcel(query: TruckingQuery = {}): Promise<Blob> {
  const params = buildQuery(query)
  params.delete('page')
  params.delete('page_size')
  return apiFetchBlob(`/trucking/export?${params}`)
}

/* ---------------------------------------------------------------- writes */

export interface TruckingVehiclePayload {
  id?: number | null
  vehicle_number?: string
  vehicle_type?: string
  no_of_packages?: number
  driver_phone?: string
  net_weight?: number
  gross_weight?: number
  container_no?: string
  container_type?: string
  tracking_status?: string
  package_refs?: unknown[]
  import_consignment_refs?: unknown[]
  item_allocations?: { item_id: string; quantity: number | null }[]
}

/**
 * Mirrors app/trucking/schemas.py. Almost everything optional so a half-filled
 * job still saves as a draft — the strict rules only run on /submit.
 *
 * `id` on a vehicle means "this row exists, update it"; omitting it means new.
 * A vehicle the payload leaves out is treated as DELETED by the update diff,
 * which is why every save sends the whole collection.
 */
export interface TruckingPayload {
  movement_type?: string
  /** Where the job came from. Set once when a job is created from an open
   *  request; a manual job leaves it as 'manual'. */
  source?: string
  source_ref?: string

  execution_date?: string
  transporter_name?: string
  shifting_type?: string
  /** Repeatable item lines. Item[0] is also mirrored onto the legacy
   *  item_details/pickup/destination/reference_no fields below, so a backend
   *  without the `items` column yet still gets the first item's data. */
  items?: {
    item_ref?: string
    item_details?: string
    quantity?: number
    uom?: string
    pickup?: string
    destination?: string
    reference_no?: string
  }[]
  item_details?: string
  pickup?: string
  destination?: string
  reference_no?: string

  quoted_freight?: number
  actual_freight?: number
  payment_status?: string
  paid_amount?: number
  detention?: number

  dispatch_note_date?: string
  eta_works?: string
  remarks?: string

  vehicles: TruckingVehiclePayload[]
}

/** Draft save, first time — POST /trucking/. */
export async function createTruckingJob(payload: TruckingPayload): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>('/trucking/', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return res.data
}

/** Draft save, every time after — PUT /trucking/{id}. Send the WHOLE draft. */
export async function updateTruckingJob(
  id: number | string, payload: TruckingPayload,
): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>(`/trucking/${id}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return res.data
}

/** POST /trucking/{id}/submit — runs the full rule set server-side. A 422
 *  carries `{message, errors[]}`; parse it with parseSubmitErrors(). */
export async function submitTruckingJob(id: number | string): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>(`/trucking/${id}/submit`, { method: 'POST' })
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

/** A child-row diff: per-column {old,new} plus a bare numeric `id`. */
export type ApiChildChange = Record<string, ApiFieldChange | number | undefined> & { id?: number }

export interface ApiTruckingHistoryPayload {
  fields?: Record<string, ApiFieldChange>
  vehicles?: ApiChildChange[]
  new_vehicles?: Record<string, unknown>[]
  deleted_vehicles?: Record<string, unknown>[]
}

export interface ApiTruckingHistoryEntry {
  id: number
  consignment_id: number
  change_type: string
  history: ApiTruckingHistoryPayload
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
 * GET /trucking/change-history/{id} — one page, newest first.
 * `includeReverted` defaults to TRUE here even though the backend defaults it
 * to false: the history screen greys reverted entries out rather than hiding
 * them.
 */
export async function getTruckingChangeHistory(
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
    data: ApiTruckingHistoryEntry[]
    pagination: Pagination
  }>(`/trucking/change-history/${id}?${params}`)
  return { entries: res.data, pagination: res.pagination }
}

/** PUT /trucking/revert-update/{id}/{historyId} — undoes one change. 400s
 *  unless it is the newest not-yet-reverted entry (the backend's LIFO rule). */
export async function revertTruckingUpdate(id: number | string, historyId: number | string) {
  const res = await apiFetch<DetailEnvelope>(
    `/trucking/revert-update/${id}/${historyId}`,
    { method: 'PUT' },
  )
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
export async function deleteTruckingJob(id: number | string): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>(`/trucking/${id}`, { method: 'DELETE' })
  return res.data
}

export async function undoDeleteTruckingJob(id: number | string): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>(`/trucking/undo-delete/${id}`, { method: 'POST' })
  return res.data
}

/** POST /trucking/{id}/reopen — admin-only server-side; clears is_locked. */
export async function reopenTruckingJob(id: number | string): Promise<ApiTruckingJob> {
  const res = await apiFetch<DetailEnvelope>(`/trucking/${id}/reopen`, { method: 'POST' })
  return res.data
}

/**
 * The trucking inbox: work handed over from the other two modules and not yet
 * turned into a job. Both halves are EXPLICIT hand-offs — logistics orders
 * flagged sent_to_trucking, and import consignments with sent_to_trucking_at.
 * A request drops off once a job takes it (matched on source + source_ref).
 */
export interface ApiOpenRequest {
  source: string
  source_ref: string
  movement_type: string | null
  label: string
  supplier?: string | null
  customer?: string | null
  mo_no?: string | null
  instrument_number?: string | null
  snapshot: unknown
}

export async function getOpenRequests(): Promise<ApiOpenRequest[]> {
  const res = await apiFetch<{ status_code: number; detail: string; data: ApiOpenRequest[] }>(
    '/trucking/open-requests',
  )
  return res.data
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
