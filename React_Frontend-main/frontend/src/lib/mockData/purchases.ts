import {
  mulberry32, randInt, choice, recentDate,
  BRANCHES, SUPPLIERS, ITEMS, ITEM_CATEGORIES, MODES_OF_PURCHASE, SOURCING_OFFICERS,
} from './shared'

const MATERIALS = ['Steel', 'Aluminum', 'Rubber', 'Plastic', 'Composite'] as const
const PPC_STORE = ['PPC', 'Store'] as const

export interface PurchaseRow {
  ref_no: string
  po_number: string
  bill_no: string
  item: string
  supplier: string
  branch: string
  category: string
  material: string
  ppc_store: string
  mop: string
  sourcing_officer: string
  quantity: number
  amount: number
  purchase_date: Date
  required_date: Date
  status: 'Pending' | 'Completed' | 'Delayed'
  /** Only meaningful for Delayed rows. */
  days_overdue?: number
}

const rng = mulberry32(42)

function makeRow(i: number): PurchaseRow {
  const purchaseDate = recentDate(rng, 84)
  const requiredDate = new Date(purchaseDate)
  requiredDate.setDate(requiredDate.getDate() + randInt(rng, 7, 45))
  const roll = rng()
  const status: PurchaseRow['status'] = roll < 0.55 ? 'Completed' : roll < 0.8 ? 'Pending' : 'Delayed'
  const daysOverdue = status === 'Delayed' ? randInt(rng, 2, 110) : undefined
  return {
    ref_no: `PR-${1000 + i}`,
    po_number: `PO-${5000 + i}`,
    bill_no: `BL-${7000 + i}`,
    item: choice(rng, ITEMS),
    supplier: choice(rng, SUPPLIERS),
    branch: choice(rng, BRANCHES),
    category: choice(rng, ITEM_CATEGORIES),
    material: choice(rng, MATERIALS),
    ppc_store: choice(rng, PPC_STORE),
    mop: choice(rng, MODES_OF_PURCHASE),
    sourcing_officer: choice(rng, SOURCING_OFFICERS),
    quantity: randInt(rng, 10, 500),
    amount: randInt(rng, 50_000, 2_000_000),
    purchase_date: purchaseDate,
    required_date: requiredDate,
    status,
    days_overdue: daysOverdue,
  }
}

const ALL_PURCHASES: PurchaseRow[] = Array.from({ length: 70 }, (_, i) => makeRow(i))

export interface PurchaseFilters {
  status?: string[]
  supplier?: string[]
  branch?: string[]
  category?: string[]
  material?: string[]
  ppcStore?: string[]
  mop?: string[]
  sourcingOfficer?: string[]
}

function matches(value: string, selected?: string[]) {
  return !selected || selected.length === 0 || selected.includes(value)
}

export function getPurchases(filters: PurchaseFilters = {}): PurchaseRow[] {
  return ALL_PURCHASES.filter(
    (row) =>
      matches(row.status, filters.status) &&
      matches(row.supplier, filters.supplier) &&
      matches(row.branch, filters.branch) &&
      matches(row.category, filters.category) &&
      matches(row.material, filters.material) &&
      matches(row.ppc_store, filters.ppcStore) &&
      matches(row.mop, filters.mop) &&
      matches(row.sourcing_officer, filters.sourcingOfficer),
  )
}

export const purchaseStatusList = ['Pending', 'Completed', 'Delayed']
export const purchaseSupplierList = [...SUPPLIERS]
export const purchaseBranchList = [...BRANCHES]
export const purchaseCategoryList = [...ITEM_CATEGORIES]
export const purchaseMaterialList = [...MATERIALS]
export const purchasePpcStoreList = [...PPC_STORE]
export const purchaseMopList = [...MODES_OF_PURCHASE]
export const purchaseSourcingOfficerList = [...SOURCING_OFFICERS]
