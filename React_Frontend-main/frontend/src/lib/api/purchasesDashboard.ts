import { apiFetch } from './client'
import type { Coverage, ResolvedPeriod } from '@/components/PeriodFilter'
import type { ReferenceSet } from '@/components/ReferenceList'

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
  /** The same denominator as on_time_pct, so the two sum to 100. */
  delayed_pct: number
  /** Orders actually purchased — on-time plus delayed. Pending orders are in
   *  neither percentage, which is why they do not describe `orders_count`. */
  purchased_orders: number
  top_supplier: string | null
  top_supplier_amount: number
  /** Import (IOL) is the in-house import channel, not a vendor, so it is left
   *  out of the supplier figures. Named here so the screen can explain why the
   *  supplier chart does not add up to the total. */
  excluded_from_supplier_figures: string[]
  excluded_supplier_value: number
}

/** Total value + how late purchasing runs. Quantity, the second delay average
 *  and the delayed-line count were removed from the endpoint; `basis` is the
 *  denominator behind avg_delay_days, not a KPI in its own right. */
export interface ProcurementKpis {
  total_value: number
  avg_delay_days: number | null
  basis: number
}

/** Bucketed to FIT THE WINDOW, not to the calendar: 3-day steps inside a
 *  month, weeks across a quarter, months up to ~3 years, quarters beyond. A
 *  month-long window bucketed by month would be a single bar.
 *
 *  Empty buckets are included — omitting them draws the line straight across a
 *  gap and reads as steady spend where there was none. */
export interface ValueTrend {
  granularity: 'day' | 'week' | 'month' | 'quarter'
  bucket_days: number
  points: TrendPoint[]
  undated_orders: number
}

// Index signatures so these drop straight into the chart components, which
// take Record<string, unknown>[].
//
// `count` is what a bar plots — how many ORDERS. `value` is what they are
// worth, shown in the tooltip abbreviated to K/M/B. Rows arrive sorted by
// value, so the biggest bar is the one worth most attention rather than merely
// the most numerous.
export interface LabelValue {
  [key: string]: unknown
  label: string
  count: number
  value: number
}

export interface TrendPoint {
  [key: string]: unknown
  bucket: string
  label: string
  value: number
  count: number
}

export interface OverdueBucket {
  [key: string]: unknown
  bucket: string
  orders: number
  count: number
  value: number
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
  /** The dashboard-wide reporting window, on the PURCHASE date. Omit BOTH to
   *  get the backend's default, which is the current month — the front end
   *  never computes that itself, so the two cannot disagree. */
  date_from?: string
  date_to?: string
  /** Which procurement event the window measures: po_date | purchase. */
  date_field?: string
  /** Free text over PO number, ref, item, supplier and bill number. Applied
   *  server-side, so it narrows the KPIs and charts, not just a row list. */
  search?: string
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
    procurement_kpis: ProcurementKpis
    period: ResolvedPeriod
    coverage: Coverage
    date_field: string
    date_field_options: { value: string; label: string }[]
    status_split: LabelValue[]
    value_by_supplier: LabelValue[]
    value_by_branch: LabelValue[]
    overdue_buckets: OverdueBucket[]
    delayed_line_references: ReferenceSet
    references: PurchaseReferences
    value_trend: ValueTrend
    statuses: string[]
    suppliers: string[]
    branches: string[]
    sourcing_officers: string[]
    mops: string[]
    item_categories: string[]
  }
}

/** Which orders each headline counted — one set per tile that counts orders. */
export interface PurchaseReferences {
  orders: ReferenceSet
  /** ORDER-level, so its total IS `kpis.delayed_orders`. The LINE-level
   *  breakdown inside those orders is `delayedLineReferences`. */
  delayed: ReferenceSet
  on_time: ReferenceSet
  top_supplier: ReferenceSet
}

export interface PurchasesDashboardResponse {
  rows?: PurchaseRow[]
  kpis: PurchaseKpis
  procurementKpis: ProcurementKpis
  period: ResolvedPeriod
  coverage: Coverage
  dateField: string
  dateFieldOptions: { value: string; label: string }[]
  statusSplit: LabelValue[]
  valueBySupplier: LabelValue[]
  valueByBranch: LabelValue[]
  overdueBuckets: OverdueBucket[]
  /** The LINES behind the delay figures: PO, item, its own lateness. The
   *  headline is per order; this is what an order was late because of. */
  delayedLineReferences: ReferenceSet
  /** The ORDERS behind the non-delay tiles, badged with what they cost. */
  references: PurchaseReferences
  valueTrend: ValueTrend
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
    procurementKpis: data.procurement_kpis,
    period: data.period,
    coverage: data.coverage,
    dateField: data.date_field,
    dateFieldOptions: data.date_field_options,
    statusSplit: data.status_split,
    valueBySupplier: data.value_by_supplier,
    valueByBranch: data.value_by_branch,
    overdueBuckets: data.overdue_buckets,
    delayedLineReferences: data.delayed_line_references,
    references: data.references,
    valueTrend: data.value_trend,
    statuses: data.statuses,
    suppliers: data.suppliers,
    branches: data.branches,
    sourcingOfficers: data.sourcing_officers,
    mops: data.mops,
    itemCategories: data.item_categories,
  }
}
