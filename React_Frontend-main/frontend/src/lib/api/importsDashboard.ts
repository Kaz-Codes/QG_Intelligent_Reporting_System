import { apiFetch } from './client'
import type { Coverage, ResolvedPeriod } from '@/components/PeriodFilter'
import type { ReferenceSet } from '@/components/ReferenceList'
import type { DataNote } from '@/components/DataNotes'

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
/** Computed from the shaft LINES and dated by each line's own ETA, so a
 *  consignment whose rows land in two months contributes to both. It used to
 *  take the consignments whose HEADER fell in the window and sum all their
 *  shaft rows, which reported Rs 10.64m for ref 65704 in August when only
 *  Rs 8.98m of it arrived then. */
export interface ShaftsValue {
  value: number
  consignments: number
  lines: number
  /** Lines with no price or no booked rate — a short total, explained. */
  unpriced_lines: number
  references: ReferenceSet
}

/** Over half the consignments do not state EFS at all, so "Not stated" is its
 *  own bucket — folding it into Regular would assert something the sheet never
 *  said. `efs_pct_of_stated` is the share among those that DO say. */
export interface EfsSplit {
  counts: { label: string; consignments: number; pct: number | null }[]
  efs: number
  efs_value: number
  regular_value: number
  regular: number
  not_stated: number
  efs_pct_of_stated: number | null
  stated_basis: number
  efs_references: ReferenceSet
}

/** A figure that is a SET of consignments: how many, and how much. Every
 *  related tile uses this shape so a row of them can be read across. */
export interface CountAndValue {
  count: number
  value: number
  value_pct?: number | null
}

/** The screen's consignments cut by where they have got to. In Process +
 *  Arrived + Cancelled = Total, and Total is EVERY status — the same
 *  population the Overview counts, so the two screens agree. */
export interface Population {
  total: CountAndValue
  in_process: CountAndValue
  arrived: CountAndValue
  cancelled: CountAndValue
  references: {
    total: ReferenceSet
    in_process: ReferenceSet
    arrived: ReferenceSet
    cancelled: ReferenceSet
  }
}

export interface DemandCounts {
  received: number
  processed: number
  in_process: number
  processed_pct: number | null
  /** The consignments that reached a terminal status. */
  processed_references: ReferenceSet
}

/** ETA Works minus the required date. Positive is late; 0 or less is on time. */
export interface DeliveryDelay {
  delay_pct: number | null
  /** The money behind the delay, so the tile reports count AND value. */
  delayed_value: number
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

/** The screen's headline money, summed over the LINES arriving in the window
 *  and dated by them — the same basis and the same rows as the Overview's, so
 *  the two screens cannot report different money for one window. */
export interface PeriodValue {
  value: number
  consignments: number
  lines: number
  unpriced_lines: number
  basis: string
  references: ReferenceSet
}

export interface ImportsDashboardData {
  kpis: ImportsDashboardKpis
  period_value: PeriodValue
  /** In Process / Arrived / Cancelled, each with count AND value. Replaces the
   *  hidden "exclude Arrived at Works" filter that made this screen disagree
   *  with the Overview by Rs 52.7m over the same window. */
  population: Population
  /** Echoed back so the screen can label its tiles as the shaft subset. */
  shafts_only: boolean
  /** Every consignment on the screen, behind the headline count. */
  references: ReferenceSet
  /** How the money was arrived at, and what it misses — empty when every
   *  consignment carries a booked total. */
  data_notes: DataNote[]
  status_split: ValueRow[]
  value_by_country: ValueRow[]
  value_by_branch: ValueRow[]
  value_trend: ValueTrend
  shafts: ShaftsValue
  efs_split: EfsSplit
  demands: DemandCounts
  delivery_delay: DeliveryDelay
  supplier_pareto: { total: number; suppliers_total: number; rows: SupplierParetoRow[] }
  /** null while the Shafts tab is active: every row is a shaft there, so a
   *  chart of "delay by item category" would be one bar. */
  category_delays: CategoryDelay[] | null
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
  /** Which date the window is applied to, and the choices — named by the
   *  backend so the screen and the server cannot disagree. */
  date_field: string
  date_field_options: { value: string; label: string }[]
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
  /** The dashboard-wide reporting window. Omit BOTH for the backend's
   *  default, which is the current month. */
  date_from?: string
  date_to?: string
  /** Which date the window applies to: eta_works | required_date. */
  date_field?: string
  /** Free text over payment reference, GD number, origin, supplier and item. */
  search?: string
  /** Narrows every figure on the screen to shaft consignments. */
  shafts_only?: boolean
}

interface RawResponse {
  status_code: number
  detail: string
  data: ImportsDashboardResponse
}

export async function getImportsDashboard(filters: ImportsDashboardFilters = {}): Promise<ImportsDashboardResponse> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    // `false` is meaningful for shafts_only, so only skip empty/undefined.
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  const res = await apiFetch<RawResponse>(`/dashboard/imports${qs ? `?${qs}` : ''}`)
  return res.data
}
