import { mulberry32, randInt, choice, recentDate, BRANCHES, ITEMS, ITEM_CATEGORIES } from './shared'

export interface StockRow {
  item_code: string
  item: string
  branch: string
  item_category: string
  specs: string
  available_qty: number
  stock_qty: number
  hold_qty: number
  reorder_level: number
  stock_status: 'Out of Stock' | 'Below Reorder' | 'OK'
  reorder_status: 'Reorder Needed' | 'Adequate'
  last_restocked: Date
  days_of_stock?: number
}

const rng = mulberry32(99)
const SPECS = ['Std grade', 'Heavy duty', 'Galvanized', 'Stainless', 'Coated'] as const

function makeRow(i: number): StockRow {
  const reorderLevel = choice(rng, [50, 100, 150])
  const availableQty = randInt(rng, 0, 800)
  const holdQty = randInt(rng, 0, 60)
  const stockQty = availableQty + holdQty
  const stockStatus: StockRow['stock_status'] =
    availableQty <= 0 ? 'Out of Stock' : availableQty < reorderLevel ? 'Below Reorder' : 'OK'
  const hasHistory = rng() > 0.25
  return {
    item_code: `${1000 + i}-60`,
    item: choice(rng, ITEMS),
    branch: choice(rng, BRANCHES),
    item_category: choice(rng, ITEM_CATEGORIES),
    specs: choice(rng, SPECS),
    available_qty: availableQty,
    stock_qty: stockQty,
    hold_qty: holdQty,
    reorder_level: reorderLevel,
    stock_status: stockStatus,
    reorder_status: availableQty < reorderLevel ? 'Reorder Needed' : 'Adequate',
    last_restocked: recentDate(rng, 84),
    days_of_stock: hasHistory ? randInt(rng, 2, 90) : undefined,
  }
}

const ALL_STOCK: StockRow[] = Array.from({ length: 60 }, (_, i) => makeRow(i))

export interface StockFilters {
  status?: string[]
  reorderStatus?: string[]
  category?: string[]
  branch?: string[]
  item?: string[]
}

function matches(value: string, selected?: string[]) {
  return !selected || selected.length === 0 || selected.includes(value)
}

export function getStock(filters: StockFilters = {}): StockRow[] {
  return ALL_STOCK.filter(
    (row) =>
      matches(row.stock_status, filters.status) &&
      matches(row.reorder_status, filters.reorderStatus) &&
      matches(row.item_category, filters.category) &&
      matches(row.branch, filters.branch) &&
      matches(row.item, filters.item),
  )
}

export const inventoryStatusList = ['Out of Stock', 'Below Reorder', 'OK']
export const inventoryReorderStatusList = ['Reorder Needed', 'Adequate']
export const inventoryCategoryList = [...ITEM_CATEGORIES]
export const inventoryBranchList = [...BRANCHES]
export const inventoryItemList = [...ITEMS]
