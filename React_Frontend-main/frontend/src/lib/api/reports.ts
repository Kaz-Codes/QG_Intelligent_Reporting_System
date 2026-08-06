import { apiFetch, apiFetchBlob } from './client'

/**
 * The cross-module report builder — spans purchases/imports/inventory/
 * logistics, each normalised server-side into one flat row shape (see
 * app/reports/serializers.py ROW_KEYS). Dropdown filters are multi-select
 * (repeated query params); date range and search stay single-valued.
 * `/reports/data` is paged (the real tables are far too big to load whole —
 * Purchases alone is ~68k rows), `/reports/export` streams the whole
 * filtered set (capped) as an .xlsx.
 */

export type ReportType = 'purchases' | 'imports' | 'inventory' | 'logistics'

export const REPORT_TYPES: { value: ReportType; label: string }[] = [
  { value: 'purchases', label: 'Purchases' },
  { value: 'imports', label: 'Imports' },
  { value: 'inventory', label: 'Inventory' },
  { value: 'logistics', label: 'Logistics' },
]

export interface ReportRow {
  [key: string]: unknown
  type: ReportType
  ref: string | null
  item: string | null
  supplier: string | null
  branch: string | null
  category: string | null
  status: string | null
  value: number | null
  date: string | null
  po_number: string | null
  bill_no: string | null
  mop: string | null
  sourcing_officer: string | null
  quantity: number | null
  required_date: string | null
  ppc_store: string | null
  country: string | null
  mode_of_shipment: string | null
  specs: string | null
  stock_qty: number | null
  hold_qty: number | null
  reorder_level: number | null
  reorder_status: string | null
  customer: string | null
  pod: string | null
  stage: string | null
  shipping_line: string | null
  cost_per_kg: number | null
}

export interface ReportOptions {
  items: string[]
  // Optional: older/reverted backend builds don't return this field at all.
  shafts?: string[]
  suppliers: string[]
  branches: string[]
  categories: string[]
}

export interface ReportPagination {
  page: number
  page_size: number
  total: number
  total_pages: number
}

/** The dropdown/date/search filters shared by /data, /export and /options —
 * everything except pagination and (for export) the chosen columns. */
export interface ReportFilters {
  types?: ReportType[]
  item?: string[]
  shaft?: string[]
  supplier?: string[]
  branch?: string[]
  category?: string[]
  date_from?: string
  date_to?: string
  search?: string
}

function buildParams(filters: ReportFilters): URLSearchParams {
  const params = new URLSearchParams()
  const multi: [string, string[] | undefined][] = [
    ['types', filters.types], ['item', filters.item], ['shaft', filters.shaft],
    ['supplier', filters.supplier], ['branch', filters.branch], ['category', filters.category],
  ]
  for (const [key, values] of multi) {
    for (const v of values ?? []) params.append(key, v)
  }
  if (filters.date_from) params.set('date_from', filters.date_from)
  if (filters.date_to) params.set('date_to', filters.date_to)
  if (filters.search) params.set('search', filters.search)
  return params
}

export async function getReportOptions(types: ReportType[]): Promise<ReportOptions> {
  const params = new URLSearchParams()
  for (const t of types) params.append('types', t)
  const qs = params.toString()
  const { data } = await apiFetch<{ data: ReportOptions }>(`/reports/options${qs ? `?${qs}` : ''}`)
  return data
}

export interface ReportDataResult {
  rows: ReportRow[]
  pagination: ReportPagination
}

export async function getReportData(filters: ReportFilters, page: number, pageSize: number): Promise<ReportDataResult> {
  const params = buildParams(filters)
  params.set('page', String(page))
  params.set('page_size', String(pageSize))
  const res = await apiFetch<{ data: ReportRow[]; pagination: ReportPagination }>(`/reports/data?${params.toString()}`)
  return { rows: res.data, pagination: res.pagination }
}

// jsPDF/autotable render client-side, so a PDF export can't stream the whole
// (potentially tens-of-thousands-of-row) filtered set the way the server xlsx
// export does — this walks /reports/data page by page until either the whole
// filtered set or this cap is reached, whichever comes first.
const PDF_ROW_CAP = 2000
const PDF_PAGE_SIZE = 100

export async function fetchReportRowsForExport(
  filters: ReportFilters,
  cap = PDF_ROW_CAP,
): Promise<{ rows: ReportRow[]; total: number; truncated: boolean }> {
  let rows: ReportRow[] = []
  let total = 0
  let page = 1
  for (;;) {
    const res = await getReportData(filters, page, PDF_PAGE_SIZE)
    total = res.pagination.total
    rows = rows.concat(res.rows)
    if (res.rows.length === 0 || rows.length >= total || rows.length >= cap) break
    page += 1
  }
  const truncated = rows.length > cap || total > rows.length
  if (rows.length > cap) rows = rows.slice(0, cap)
  return { rows, total, truncated }
}

export async function downloadReportExcel(filters: ReportFilters, columns: string[], filename: string): Promise<void> {
  const params = buildParams(filters)
  for (const c of columns) params.append('columns', c)
  const blob = await apiFetchBlob(`/reports/export?${params.toString()}`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

//-----------------------------------------------------
// SAVED REPORTS
//
// Re-runnable templates: name, the types/columns/filters recipe, no date
// range (chosen fresh every run) and no search. Shared — everyone who can
// reach Reports sees the whole list; editing/deleting someone else's is
// admin-only (the backend 403s a non-admin, non-owner attempt).
//-----------------------------------------------------

export interface SavedReportFilters {
  item: string[]
  shaft: string[]
  supplier: string[]
  branch: string[]
  category: string[]
}

export interface SavedReport {
  id: number
  name: string
  types: ReportType[]
  columns: string[]
  filters: SavedReportFilters
  created_by: string | null
  created_by_id: number | null
  created_at: string
  updated_at: string
}

export interface SavedReportInput {
  name: string
  types: ReportType[]
  columns: string[]
  filters: SavedReportFilters
}

export async function getSavedReports(): Promise<SavedReport[]> {
  const { data } = await apiFetch<{ data: SavedReport[] }>('/reports/saved')
  return data
}

export async function createSavedReport(input: SavedReportInput): Promise<SavedReport> {
  const { data } = await apiFetch<{ data: SavedReport }>('/reports/saved', {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return data
}

export async function updateSavedReport(id: number, input: SavedReportInput): Promise<SavedReport> {
  const { data } = await apiFetch<{ data: SavedReport }>(`/reports/saved/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
  return data
}

export async function deleteSavedReport(id: number): Promise<void> {
  await apiFetch<{ status_code: number }>(`/reports/saved/${id}`, { method: 'DELETE' })
}
