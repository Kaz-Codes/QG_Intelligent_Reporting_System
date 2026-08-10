import { apiFetch } from './client'
import type { Coverage, ResolvedPeriod } from '@/components/PeriodFilter'

/**
 * The cross-module overview — `GET /dashboard/overview`.
 *
 * The one dashboard that reads every module at once. It never returns rows:
 * every figure is a single SQL aggregate, so the payload stays a couple of KB
 * even though it spans ~245k issuance records.
 *
 * Counting units are consistent with the per-module screens: ORDERS for
 * procurement (distinct POs, not item lines), CONSIGNMENTS for imports, ITEMS
 * for stock (folded across the branches that hold them).
 *
 * Period vs lifetime is stated per figure rather than left to be inferred from
 * its name: imports and procurement are windowed, logistics counts and stores
 * are running totals or snapshots.
 */

export interface OverviewPeriod {
  from: string | null
  to: string
  kind: string
}

/** Money with no ETD falls in NO window, so it is reported beside the period
 *  figure rather than disappearing from every period at once. */
export interface ImportsPeriodValue {
  value: number
  consignments: number
  basis: string
  undated: { consignments: number; value: number }
}

export interface OverviewImports {
  period_value: ImportsPeriodValue
  in_process: { total: number; by_stage: { stage: string; consignments: number }[] }
  shafts: { in_process: number; arrived: number; total: number; arrived_pct: number | null }
}

export interface OverviewProcurement {
  period_value: { value: number; orders: number; quantity: number; basis: string }
  category_split: {
    total: number
    categories_total: number
    split: { category: string; value: number; share_pct: number | null; categories?: number }[]
  }
  delay: { delay_pct: number | null; late_orders: number; basis: number }
  cycle_time: {
    store_to_purchase_days: number | null
    store_to_purchase_basis: number
    po_to_purchase_days: number | null
    po_to_purchase_basis: number
  }
}

/** There is no "Local" movement type in the data and none can be inferred, so
 *  unclassified jobs get their own bucket rather than being folded into a
 *  category they may not belong to. */
export interface OverviewLogistics {
  trucking_cost: {
    total: number
    by_movement: {
      movement_type: string
      jobs: number
      actual_freight: number
      quoted_freight: number
      share_pct: number | null
    }[]
  }
  shipments_handled: { export_shipments: number; import_shipments: number; total: number }
}

export interface OverviewStores {
  stock_value: { stock_value: number; available_value: number; items: number }
  value_by_store: { branch: string; stock_value: number; items: number; share_pct: number | null }[]
  stock_days: {
    total_days_of_stock: number | null
    window_days: number
    by_branch: {
      branch: string
      stock_value: number
      consumed_value: number
      days_of_stock: number | null
    }[]
  }
  /** `exceeds_history` warns that the threshold reaches back past the issuance
   *  data, where the figure stops responding to it. */
  dead_stock: {
    items: number
    value: number
    threshold_days: number
    items_pct: number | null
    value_pct: number | null
    history_days: number
    exceeds_history: boolean
  }
}

export interface OverviewDashboardResponse {
  period: ResolvedPeriod & OverviewPeriod
  imports: OverviewImports
  procurement: OverviewProcurement
  logistics: OverviewLogistics
  stores: OverviewStores
}

export interface OverviewDashboardFilters {
  /** Omit BOTH for the backend's default, which is the current month. */
  date_from?: string
  date_to?: string
  /** How long stock must sit unissued to count as dead. Default 180. */
  dead_stock_days?: number
}

interface RawResponse {
  status_code: number
  detail: string
  data: OverviewDashboardResponse
}

export async function getOverviewDashboard(
  filters: OverviewDashboardFilters = {},
): Promise<OverviewDashboardResponse> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const qs = params.toString()
  const { data } = await apiFetch<RawResponse>(`/dashboard/overview${qs ? `?${qs}` : ''}`)
  return data
}

export type { Coverage }
