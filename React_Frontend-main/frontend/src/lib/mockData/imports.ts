import {
  mulberry32, randInt, choice, recentDate,
  BRANCHES, SUPPLIERS, CUSTOMERS, ITEM_CATEGORIES,
} from './shared'

export const COUNTRIES = ['China', 'UAE', 'Germany', 'Turkey', 'South Korea'] as const
export const SHIPPING_LINES = ['Maersk', 'MSC', 'CMA CGM', 'Hapag-Lloyd', 'COSCO'] as const
export const MODES_OF_SHIPMENT = ['Sea', 'Air', 'Land'] as const
export const BANKS = ['HBL', 'MCB', 'UBL', 'Meezan Bank'] as const
const STATUSES = ['LC in Process', 'Sailing', 'In Transit', 'Under Custom Clearance', 'Arrived at Works', 'Order Cancelled'] as const
const DOCUMENTATION_STATUSES = ['Complete', 'Incomplete'] as const

export interface ImportRow {
  import_ref: string
  customer: string
  supplier: string
  supplier_country: string
  category: string
  branch: string
  total_value_pkr: number
  total_wt_ton: number
  current_status: (typeof STATUSES)[number]
  documentation_status: (typeof DOCUMENTATION_STATUSES)[number]
  shipping_line: string
  mode_of_shipment: string
  bank: string
  demand_date: Date
}

const rng = mulberry32(17)

function makeRow(i: number): ImportRow {
  return {
    import_ref: `IMP-${2000 + i}`,
    customer: choice(rng, CUSTOMERS),
    supplier: choice(rng, SUPPLIERS),
    supplier_country: choice(rng, COUNTRIES),
    category: choice(rng, ITEM_CATEGORIES),
    branch: choice(rng, BRANCHES),
    total_value_pkr: randInt(rng, 500_000, 20_000_000),
    total_wt_ton: randInt(rng, 2, 400),
    current_status: choice(rng, STATUSES),
    documentation_status: choice(rng, DOCUMENTATION_STATUSES),
    shipping_line: choice(rng, SHIPPING_LINES),
    mode_of_shipment: choice(rng, MODES_OF_SHIPMENT),
    bank: choice(rng, BANKS),
    demand_date: recentDate(rng, 84),
  }
}

const ALL_IMPORTS: ImportRow[] = Array.from({ length: 55 }, (_, i) => makeRow(i))

export interface ImportFilters {
  status?: string[]
  documentationStatus?: string[]
  branch?: string[]
  category?: string[]
  supplier?: string[]
  customer?: string[]
  country?: string[]
  shippingLine?: string[]
  modeOfShipment?: string[]
  bank?: string[]
}

function matches(value: string, selected?: string[]) {
  return !selected || selected.length === 0 || selected.includes(value)
}

export function getImports(filters: ImportFilters = {}): ImportRow[] {
  return ALL_IMPORTS.filter(
    (row) =>
      matches(row.current_status, filters.status) &&
      matches(row.documentation_status, filters.documentationStatus) &&
      matches(row.branch, filters.branch) &&
      matches(row.category, filters.category) &&
      matches(row.supplier, filters.supplier) &&
      matches(row.customer, filters.customer) &&
      matches(row.supplier_country, filters.country) &&
      matches(row.shipping_line, filters.shippingLine) &&
      matches(row.mode_of_shipment, filters.modeOfShipment) &&
      matches(row.bank, filters.bank),
  )
}

export const importStatusList = [...STATUSES]
export const importDocumentationStatusList = [...DOCUMENTATION_STATUSES]
export const importBranchList = [...BRANCHES]
export const importCategoryList = [...ITEM_CATEGORIES]
export const importSupplierList = [...SUPPLIERS]
export const importCustomerList = [...CUSTOMERS]
export const importCountryList = [...COUNTRIES]
export const importShippingLineList = [...SHIPPING_LINES]
export const importModeOfShipmentList = [...MODES_OF_SHIPMENT]
export const importBankList = [...BANKS]
