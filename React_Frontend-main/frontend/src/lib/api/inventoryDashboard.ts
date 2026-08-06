import { apiFetch } from './client'

/**
 * Like the purchases endpoint, this returns finished figures — kpis,
 * stock_health, items_by_branch, at_risk_by_branch, top_items and
 * lowest_days_of_stock are all computed server-side, already in the shape the
 * charts want. The page renders those directly. `rows` is no longer returned
 * by the endpoint at all, which is why the runway chart (the one figure
 * derived from individual rows) has nothing to plot.
 *
 * Search is a server-side param here (unlike Purchases, where it only ever
 * scoped the table) because on this page it has always narrowed the KPIs and
 * charts too — keeping that behaviour means the server has to see it.
 */

export interface StockRow {
  [key: string]: unknown
  item_code: string | null
  item: string | null
  branch: string | null
  item_category: string | null
  specs: string | null
  available_qty: number | null
  stock_qty: number | null
  hold_qty: number | null
  reorder_level: number | null
  stock_qty_amount: number | null
  available_amount: number | null
  stock_status: 'Out of Stock' | 'Below Reorder' | 'OK'
  reorder_status: 'Reorder Needed' | 'Adequate'
  days_of_stock: number | null
}

export interface InventoryKpis {
  available_units: number
  total_stock_qty: number
  on_hold: number
  items_shown: number
  out_of_stock: number
  below_reorder: number
  at_risk_pct: number
  total_stock_value: number
  available_value: number
}

export interface LabelValue {
  [key: string]: unknown
  label: string
  value: number
}

export interface BranchItems {
  [key: string]: unknown
  branch: string
  items: number
}

export interface BranchAtRisk {
  [key: string]: unknown
  branch: string
  at_risk: number
}

export interface ItemQty {
  [key: string]: unknown
  item: string
  stock_qty: number
}

export interface ItemRunway {
  [key: string]: unknown
  item: string
  days_of_stock: number
}

export interface InventoryDashboardFilters {
  status?: string[]
  reorder_status?: string[]
  category?: string[]
  branch?: string[]
  item?: string[]
  search?: string
}

interface RawResponse {
  status_code: number
  detail: string
  data: {
    /** Optional: the endpoint stopped returning row-level data once the
     * payload was trimmed (it was ~99% of the response). Anything needing
     * individual rows has to cope with them being absent. */
    rows?: StockRow[]
    kpis: InventoryKpis
    stock_health: LabelValue[]
    items_by_branch: BranchItems[]
    at_risk_by_branch: BranchAtRisk[]
    top_items: ItemQty[]
    lowest_days_of_stock: ItemRunway[]
    statuses: string[]
    reorder_statuses: string[]
    branches: string[]
    items: string[]
    item_categories: string[]
  }
}

export interface InventoryDashboardResponse {
  rows?: StockRow[]
  kpis: InventoryKpis
  stockHealth: LabelValue[]
  itemsByBranch: BranchItems[]
  atRiskByBranch: BranchAtRisk[]
  topItems: ItemQty[]
  lowestDaysOfStock: ItemRunway[]
  statuses: string[]
  reorderStatuses: string[]
  branches: string[]
  items: string[]
  itemCategories: string[]
}

export async function getInventoryDashboard(filters: InventoryDashboardFilters = {}): Promise<InventoryDashboardResponse> {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) {
      for (const v of value) params.append(key, v)
    } else if (value) {
      params.set(key, value)
    }
  }
  const qs = params.toString()
  const { data } = await apiFetch<RawResponse>(`/dashboard/inventory${qs ? `?${qs}` : ''}`)
  return {
    rows: data.rows,
    kpis: data.kpis,
    stockHealth: data.stock_health,
    itemsByBranch: data.items_by_branch,
    atRiskByBranch: data.at_risk_by_branch,
    topItems: data.top_items,
    lowestDaysOfStock: data.lowest_days_of_stock,
    statuses: data.statuses,
    reorderStatuses: data.reorder_statuses,
    branches: data.branches,
    items: data.items,
    itemCategories: data.item_categories,
  }
}
