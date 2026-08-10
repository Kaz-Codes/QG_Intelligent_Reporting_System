import { apiFetch } from './client'
import type { Coverage, ResolvedPeriod } from '@/components/PeriodFilter'
import type { ReferenceSet } from '@/components/ReferenceList'

// Index signatures so these can go straight into the generic chart
// components (RankedBar/TrendLine take Record<string, unknown>[]) without a
// cast at every call site.
/** A chart row. `count` is what a bar plots (how many consignments); `value`
 *  is what they are worth and appears only in the tooltip, abbreviated to
 *  K/M/B. Rows arrive sorted by value, so the biggest bar is the one worth
 *  most attention rather than merely the most numerous. */
export interface ValueRow {
  [key: string]: unknown
  label: string
  count: number
  value: number
}

/** Bucketed to fit the window: 3-day steps inside a month, weeks across a
 *  quarter, months up to ~3 years, quarters beyond. Empty buckets are kept so
 *  the line never draws straight across a gap. */
export interface ValueTrend {
  granularity: 'day' | 'week' | 'month' | 'quarter'
  bucket_days: number
  points: { [key: string]: unknown; bucket: string; label: string; value: number; count: number }[]
  undated_consignments: number
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

/** Value of the SHAFT LINES specifically — not of the consignments carrying
 *  them, which would overstate it badly (a consignment usually carries other
 *  items too). Replaces the old "import spend" tile, which restated
 *  kpis.total_value_pkr on a different basis. */
export interface ShaftsValue {
  value: number
  consignments: number
  references: ReferenceSet
  /** Consignments whose shaft rows were missing a price or a booked rate, so a
   *  short total is explained rather than silently short. */
  incomplete_consignments: number
  item_names: string[]
}

/** Over half the consignments do not state EFS at all, so "Not stated" is its
 *  own bucket — folding it into Regular would assert something the sheet never
 *  said. `efs_pct_of_stated` is the share among those that DO say. */
export interface EfsSplit {
  counts: { label: string; consignments: number; pct: number | null }[]
  efs: number
  regular: number
  not_stated: number
  efs_pct_of_stated: number | null
  stated_basis: number
  efs_references: ReferenceSet
}

export interface DemandCounts {
  received: number
  processed: number
  in_process: number
  processed_pct: number | null
}

/** ETA Works minus the required date. Positive is late; 0 or less is on time. */
export interface DeliveryDelay {
  delay_pct: number | null
  delayed: number
  on_time: number
  basis: number
  not_measurable: number
  avg_days_late: number | null
  worst_days_late: number | null
  definition: string
  /** Late, but inside the grace — so "on time" is not read as "arrived by the
   *  required date". */
  within_grace: number
  grace_days: number
  delayed_references: ReferenceSet
}

export interface SupplierParetoRow {
  [key: string]: unknown
  /** Same `label`/`count`/`value` shape as every other chart row, so this
   *  drops into RankedBar without a cast. */
  label: string
  supplier: string
  count: number
  value: number
  share_pct: number | null
  cumulative_pct: number | null
}

export interface CategoryDelay {
  [key: string]: unknown
  category: string
  consignments: number
  delayed: number
  delay_pct: number | null
  avg_days_late: number | null
}

export interface ImportsDashboardData {
  kpis: ImportsDashboardKpis
  /** Every consignment on the screen, behind the headline count. */
  references: ReferenceSet
  status_split: ValueRow[]
  value_by_country: ValueRow[]
  value_by_branch: ValueRow[]
  value_trend: ValueTrend
  shafts: ShaftsValue
  efs_split: EfsSplit
  demands: DemandCounts
  delivery_delay: DeliveryDelay
  supplier_pareto: { total: number; suppliers_total: number; rows: SupplierParetoRow[] }
  category_delays: CategoryDelay[]
}

export interface ImportsDashboardResponse {
  consignments: ImportsDashboardData
  period: ResolvedPeriod
  coverage: Coverage
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
  /** The dashboard-wide reporting window, on ETA Works. Omit BOTH for the
   *  backend's default, which is the current month. */
  date_from?: string
  date_to?: string
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
