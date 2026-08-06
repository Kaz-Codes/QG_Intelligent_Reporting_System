import { apiFetch } from './client'

/**
 * The purchases dashboard endpoint returns the finished figures, not just raw
 * rows: kpis, status_split, value_by_supplier, value_by_branch and
 * monthly_value_trend are all computed server-side. The page renders those
 * directly rather than re-deriving them from `rows`.
 *
 * `rows` is now the only gap: the endpoint stopped returning it, and the
 * days-overdue aging chart is the one figure computed from it rather than
 * server-side, so that chart stays empty until the endpoint exposes either
 * the rows or the buckets. Dates stay as the "YYYY-MM-DD" strings the API
 * sends — shortDate() already accepts a string.
 */

export interface PurchaseRow {
  [key: string]: unknown
  ref_no: string | null
  po_number: string | null
  bill_no: string | null
  item: string | null
  item_code: string | null
  supplier: string | null
  branch: string | null
  category: string | null
  mop: string | null
  sourcing_officer: string | null
  quantity: number | null
  amount: number | null
  po_date: string | null
  purchase_date: string | null
  required_date: string | null
  ppc_store: string | null
  status: 'Pending' | 'Completed' | 'Delayed'
  days_overdue: number | null
}

export interface PurchaseKpis {
  orders_count: number
  total_value: number
  avg_order_value: number
  pending_orders: number
  completed_orders: number
  delayed_orders: number
  on_time_pct: number
  top_supplier: string | null
  top_supplier_amount: number
}

// Index signatures so these drop straight into the chart components, which
// take Record<string, unknown>[].
export interface LabelValue {
  [key: string]: unknown
  label: string
  value: number
}

export interface MonthlyValuePoint {
  [key: string]: unknown
  month: string
  value: number
}

export interface OverdueBucket {
  bucket: string
  orders: number
}

export interface PurchasesDashboardFilters {
  status?: string[]
  supplier?: string[]
  branch?: string[]
  item_category?: string[]
  mop?: string[]
  sourcing_o?: string[]
  po_from_date?: string
  po_to_date?: string
}

interface RawResponse {
  status_code: number
  detail: string
  data: {
    /** Optional: the endpoint stopped returning row-level data once the
     * payload was trimmed (it was ~99% of the response). Anything needing
     * individual rows has to cope with them being absent. */
    rows?: PurchaseRow[]
    kpis: PurchaseKpis
    status_split: LabelValue[]
    value_by_supplier: LabelValue[]
    value_by_branch: LabelValue[]
    overdue_buckets: OverdueBucket[]
    monthly_value_trend: MonthlyValuePoint[]
    statuses: string[]
    suppliers: string[]
    branches: string[]
    sourcing_officers: string[]
    mops: string[]
    item_categories: string[]
  }
}

export interface PurchasesDashboardResponse {
  rows?: PurchaseRow[]
  kpis: PurchaseKpis
  statusSplit: LabelValue[]
  valueBySupplier: LabelValue[]
  valueByBranch: LabelValue[]
  overdueBuckets: OverdueBucket[]
  monthlyValueTrend: MonthlyValuePoint[]
  statuses: string[]
  suppliers: string[]
  branches: string[]
  sourcingOfficers: string[]
  mops: string[]
  itemCategories: string[]
}

export async function getPurchasesDashboard(filters: PurchasesDashboardFilters = {}): Promise<PurchasesDashboardResponse> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) {
      for (const v of value) params.append(key, v)
    } else if (value) {
      params.set(key, value)
    }
  }
  const qs = params.toString()
  const { data } = await apiFetch<RawResponse>(`/dashboard/purchases${qs ? `?${qs}` : ''}`)
  return {
    rows: data.rows,
    kpis: data.kpis,
    statusSplit: data.status_split,
    valueBySupplier: data.value_by_supplier,
    valueByBranch: data.value_by_branch,
    overdueBuckets: data.overdue_buckets,
    monthlyValueTrend: data.monthly_value_trend,
    statuses: data.statuses,
    suppliers: data.suppliers,
    branches: data.branches,
    sourcingOfficers: data.sourcing_officers,
    mops: data.mops,
    itemCategories: data.item_categories,
  }
}
