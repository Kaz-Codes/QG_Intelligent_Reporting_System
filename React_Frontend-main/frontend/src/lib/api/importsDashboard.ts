import { apiFetch } from './client'

// Index signatures so these can go straight into the generic chart
// components (RankedBar/TrendLine take Record<string, unknown>[]) without a
// cast at every call site.
export interface ValueRow {
  [key: string]: unknown
  label: string
  value: number
}

export interface MonthlyValuePoint {
  [key: string]: unknown
  month: string
  value: number
}

export interface ImportsDashboardKpis {
  total_value_pkr: number
  consignments_shown: number
  open: number
  under_clearance: number
  suppliers: number
}

export interface ImportsDashboardData {
  kpis: ImportsDashboardKpis
  status_split: ValueRow[]
  value_by_country: ValueRow[]
  value_by_supplier: ValueRow[]
  value_by_branch: ValueRow[]
  monthly_value_trend: MonthlyValuePoint[]
}

export interface ImportsDashboardResponse {
  consignments: ImportsDashboardData
  works: string[]
  suppliers: string[]
  countries: string[]
  item_categories: string[]
  status: string[]
}

export interface ImportsDashboardFilters {
  work?: string
  supplier?: string
  country?: string
  item_category?: string
  status?: string
  mode_of_shipment?: string
  from_date?: string
  to_date?: string
}

interface RawResponse {
  status_code: number
  detail: string
  data: ImportsDashboardResponse
}

export async function getImportsDashboard(filters: ImportsDashboardFilters = {}): Promise<ImportsDashboardResponse> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value) params.set(key, value)
  }
  const qs = params.toString()
  const res = await apiFetch<RawResponse>(`/dashboard/imports${qs ? `?${qs}` : ''}`)
  return res.data
}
