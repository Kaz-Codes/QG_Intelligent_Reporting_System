import { mulberry32, randInt, choice, recentDate, CUSTOMERS, ITEM_CATEGORIES } from './shared'

const rng = mulberry32(23)

function matches(value: string, selected?: string[]) {
  return !selected || selected.length === 0 || selected.includes(value)
}

// ---------------------------------------------------------------- Shipments
export const COUNTRIES = ['China', 'UAE', 'Germany', 'Turkey', 'South Korea'] as const
export const SHIPPING_LINES = ['Maersk', 'MSC', 'CMA CGM', 'Hapag-Lloyd', 'COSCO'] as const
const PODS = ['Jebel Ali', 'Hamburg', 'Shanghai', 'Dubai'] as const
const SHIPMENT_STATUSES = ['Booked', 'Sailing', 'At Port', 'Delivered'] as const
const SHIPMENT_STAGES = ['Pre-Shipment', 'In Transit', 'Customs', 'Delivered'] as const

export interface ShipmentRow {
  exp_no: string
  customer: string
  country: string
  pod: string
  status: (typeof SHIPMENT_STATUSES)[number]
  stage: string
  shipping_line: string
  export_id: string | null
  total_logistics_cost: number
  cost_per_kg: number
  port_in_date: Date
}

const ALL_SHIPMENTS: ShipmentRow[] = Array.from({ length: 45 }, (_, i) => ({
  exp_no: `EXP-${3000 + i}`,
  customer: choice(rng, CUSTOMERS),
  country: choice(rng, COUNTRIES),
  pod: choice(rng, PODS),
  status: choice(rng, SHIPMENT_STATUSES),
  stage: choice(rng, SHIPMENT_STAGES),
  shipping_line: choice(rng, SHIPPING_LINES),
  export_id: rng() > 0.15 ? `EXPID-${i}` : null,
  total_logistics_cost: randInt(rng, 80_000, 1_500_000),
  cost_per_kg: randInt(rng, 40, 320),
  port_in_date: recentDate(rng, 84),
}))

export function getShipments(f: { status?: string[]; stage?: string[]; shippingLine?: string[]; country?: string[]; customer?: string[] } = {}) {
  return ALL_SHIPMENTS.filter((r) =>
    matches(r.status, f.status) && matches(r.stage, f.stage) && matches(r.shipping_line, f.shippingLine) &&
    matches(r.country, f.country) && matches(r.customer, f.customer))
}
export const shipmentStatusList = [...SHIPMENT_STATUSES]
export const shipmentStageList = [...SHIPMENT_STAGES]
export const shipmentShippingLineList = [...SHIPPING_LINES]
export const shipmentCountryList = [...COUNTRIES]
export const shipmentCustomerList = [...CUSTOMERS]

// ---------------------------------------------------------------- Packing
const PACKING_STATUSES = ['Pending Packing', 'In Progress', 'Completed'] as const
const BUSINESS_TYPES = ['Export', 'Local'] as const
const WORKS = ['Lahore', 'Karachi', 'Faisalabad', 'Multan'] as const

export interface PackingRow {
  jobs_no: string
  customer: string
  status: (typeof PACKING_STATUSES)[number]
  works: string
  product_category: string
  business_type: string
  rfd_delay_days: number | null
  actual_packing_cost: number
  packing_date: Date
}

const ALL_PACKING: PackingRow[] = Array.from({ length: 40 }, (_, i) => ({
  jobs_no: `PKG-${4000 + i}`,
  customer: choice(rng, CUSTOMERS),
  status: choice(rng, PACKING_STATUSES),
  works: choice(rng, WORKS),
  product_category: choice(rng, ITEM_CATEGORIES),
  business_type: choice(rng, BUSINESS_TYPES),
  rfd_delay_days: rng() > 0.2 ? randInt(rng, -5, 40) : null,
  actual_packing_cost: randInt(rng, 20_000, 400_000),
  packing_date: recentDate(rng, 84),
}))

export function getPacking(f: { status?: string[]; works?: string[]; productCategory?: string[]; businessType?: string[]; customer?: string[] } = {}) {
  return ALL_PACKING.filter((r) =>
    matches(r.status, f.status) && matches(r.works, f.works) && matches(r.product_category, f.productCategory) &&
    matches(r.business_type, f.businessType) && matches(r.customer, f.customer))
}
export const packingStatusList = [...PACKING_STATUSES]
export const packingWorksList = [...WORKS]
export const packingCategoryList = [...ITEM_CATEGORIES]
export const packingBusinessTypeList = [...BUSINESS_TYPES]
export const packingCustomerList = [...CUSTOMERS]

// ---------------------------------------------------------------- Transport / Shifting
const SHIFTING_STATUSES = ['Booked', 'In Progress', 'Delivered'] as const
const MOVEMENT_TYPES = ['Inbound', 'Outbound', 'Inter-Branch'] as const
const PAYMENT_STATUSES = ['Paid', 'Pending', 'Partial'] as const
const TRANSPORTERS = ['Sindh Cargo', 'Bilal Movers', 'TCS Logistics', 'Leopards Transport'] as const
const PROVINCES = ['Punjab', 'Sindh', 'KPK', 'Balochistan'] as const

export interface ShiftingRow {
  customer: string
  status: (typeof SHIFTING_STATUSES)[number]
  movement_type: string
  payment_status: string
  transporter: string
  province: string
  destination: string
  execution_date: Date
  actual_freight_rs: number
  savings_rs: number | null
}

const ALL_SHIFTING: ShiftingRow[] = Array.from({ length: 38 }, (_, i) => ({
  customer: choice(rng, CUSTOMERS),
  status: choice(rng, SHIFTING_STATUSES),
  movement_type: choice(rng, MOVEMENT_TYPES),
  payment_status: choice(rng, PAYMENT_STATUSES),
  transporter: choice(rng, TRANSPORTERS),
  province: choice(rng, PROVINCES),
  destination: `${choice(rng, PROVINCES)} Depot ${i % 5}`,
  execution_date: recentDate(rng, 84),
  actual_freight_rs: randInt(rng, 15_000, 300_000),
  savings_rs: rng() > 0.4 ? randInt(rng, 1_000, 40_000) : null,
}))

export function getShifting(f: {
  status?: string[]; movementType?: string[]; paymentStatus?: string[]
  customer?: string[]; province?: string[]; transporter?: string[]
} = {}) {
  return ALL_SHIFTING.filter((r) =>
    matches(r.status, f.status) && matches(r.movement_type, f.movementType) && matches(r.payment_status, f.paymentStatus) &&
    matches(r.customer, f.customer) && matches(r.province, f.province) && matches(r.transporter, f.transporter))
}
export const shiftingStatusList = [...SHIFTING_STATUSES]
export const shiftingMovementTypeList = [...MOVEMENT_TYPES]
export const shiftingPaymentStatusList = [...PAYMENT_STATUSES]
export const shiftingCustomerList = [...CUSTOMERS]
export const shiftingProvinceList = [...PROVINCES]
export const shiftingTransporterList = [...TRANSPORTERS]

// ---------------------------------------------------------------- Documentation
const DOC_STATUSES = ['Complete', 'Incomplete'] as const
const DOC_TYPES = ['Bill of Lading', 'Certificate of Origin', 'Packing List', 'Commercial Invoice', 'Insurance Certificate'] as const

export interface DocumentationRow {
  exp_no: string
  batch_no: string
  status: (typeof DOC_STATUSES)[number]
  completion_pct: number
  customs_completion_pct: number
  customer_completion_pct: number
  bank_completion_pct: number
  pending_documents: number
  submitted_date: Date
}

const ALL_DOCUMENTATION: DocumentationRow[] = Array.from({ length: 30 }, (_, i) => {
  const customs = randInt(rng, 40, 100)
  const customer = randInt(rng, 40, 100)
  const bank = randInt(rng, 40, 100)
  const completion = Math.round((customs + customer + bank) / 3)
  return {
    exp_no: `EXP-${3000 + i}`,
    batch_no: `BATCH-${randInt(rng, 100, 999)}`,
    status: completion >= 85 ? 'Complete' : 'Incomplete',
    completion_pct: completion,
    customs_completion_pct: customs,
    customer_completion_pct: customer,
    bank_completion_pct: bank,
    pending_documents: completion >= 85 ? 0 : randInt(rng, 1, 5),
    submitted_date: recentDate(rng, 84),
  }
})

export function getDocumentation(f: { status?: string[] } = {}) {
  return ALL_DOCUMENTATION.filter((r) => matches(r.status, f.status))
}
export const documentationStatusList = [...DOC_STATUSES]

export interface DocTypeRow { document_type: string; status: string; n: number }
export function getDocumentTypes(): DocTypeRow[] {
  const rows: DocTypeRow[] = []
  for (const type of DOC_TYPES) {
    rows.push({ document_type: type, status: 'Complete', n: randInt(rng, 20, 60) })
    rows.push({ document_type: type, status: 'Incomplete', n: randInt(rng, 2, 15) })
  }
  return rows
}
