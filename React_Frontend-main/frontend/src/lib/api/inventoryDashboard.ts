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

/** Quantity totals (available_units / total_stock_qty) and on_hold were dropped
 *  from the endpoint: they summed incomparable units — kilograms plus pieces
 *  plus litres — so the number was arithmetic without a meaning. at_risk_pct
 *  went with them, replaced by the movement split, which says the same thing
 *  with a reason attached. Value is the comparable measure and is what remains. */
export interface InventoryKpis {
  /** Distinct ITEMS, folded across the branches that stock them. */
  items_total: number
  items_shown: number
  out_of_stock: number
  below_reorder: number
  total_stock_value: number
  available_value: number
}

/** Everything about movement comes from ONE pair of per-line numbers, so these
 *  KPIs, the split and the stock-days runway cannot disagree with each other. */
export interface MovementKpis {
  issued_value_12m: number
  issued_value_3m: number
  dead_items: number
  dead_value: number
  dead_value_pct: number | null
  window_12m: number
  window_3m: number
}

export interface MovementBucket {
  [key: string]: unknown
  movement: 'Fast moving' | 'Slow moving' | 'Dead'
  items: number
  count: number
  value: number
  items_pct: number | null
  value_pct: number | null
}

export interface BranchMovement {
  [key: string]: unknown
  branch: string
  label: string
  fast: number
  slow: number
  dead: number
  /** dead lines — what the bar plots; `value` is the money, shown on hover. */
  count: number
  value: number
  dead_value: number
  dead_pct: number | null
}

export interface BranchStockDays {
  [key: string]: unknown
  branch: string
  stock_value: number
  issued_value: number
  days_of_stock: number | null
}

export interface StockDays {
  total_days_of_stock: number | null
  by_branch: BranchStockDays[]
  window_days: number
  basis: string
}

/** The dates the 12m/3m windows actually cover. They end at the latest issuance
 *  in the DATA, not today, so a screen can state the real range instead of
 *  implying it runs to this morning. */
export interface IssuanceWindows {
  latest_issuance: string | null
  from_12m: string | null
  from_3m: string | null
}

export interface LabelValue {
  [key: string]: unknown
  label: string
  count: number
  value: number
}

export interface BranchItems {
  [key: string]: unknown
  branch: string
  label: string
  items: number
  count: number
  value: number
}

export interface ItemRunway {
  [key: string]: unknown
  item: string
  days_of_stock: number
}

export interface InventoryDashboardFilters {
  status?: string[]
  reorder_status?: string[]
  /** Fast moving / Slow moving / Dead — derived from issuance, filtered
   *  server-side like the other derived statuses. */
  movement?: string[]
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
    movement_kpis: MovementKpis
    stock_days: StockDays
    movement_split: MovementBucket[]
    movement_by_branch: BranchMovement[]
    issuance_windows: IssuanceWindows
    stock_health: LabelValue[]
    items_by_branch: BranchItems[]
    lowest_days_of_stock: ItemRunway[]
    statuses: string[]
    reorder_statuses: string[]
    movement_classes: string[]
    branches: string[]
    items: string[]
    item_categories: string[]
  }
}

export interface InventoryDashboardResponse {
  rows?: StockRow[]
  kpis: InventoryKpis
  movementKpis: MovementKpis
  stockDays: StockDays
  movementSplit: MovementBucket[]
  movementByBranch: BranchMovement[]
  issuanceWindows: IssuanceWindows
  stockHealth: LabelValue[]
  itemsByBranch: BranchItems[]
  lowestDaysOfStock: ItemRunway[]
  statuses: string[]
  reorderStatuses: string[]
  movementClasses: string[]
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
    movementKpis: data.movement_kpis,
    stockDays: data.stock_days,
    movementSplit: data.movement_split,
    movementByBranch: data.movement_by_branch,
    issuanceWindows: data.issuance_windows,
    stockHealth: data.stock_health,
    itemsByBranch: data.items_by_branch,
    lowestDaysOfStock: data.lowest_days_of_stock,
    statuses: data.statuses,
    reorderStatuses: data.reorder_statuses,
    movementClasses: data.movement_classes,
    branches: data.branches,
    items: data.items,
    itemCategories: data.item_categories,
  }
}
