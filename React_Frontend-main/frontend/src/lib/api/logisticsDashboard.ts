import { apiFetch } from './client'
import type { ReferenceSet } from '@/components/ReferenceList'
import type { ResolvedPeriod, Coverage } from '@/components/PeriodFilter'
import type { DataNote } from '@/components/DataNotes'

/** Every tab carries the same three things as the other dashboards: the window
 *  it actually used, what its source holds, and where a figure rests on a
 *  partly-filled column. Logistics was the one screen without them. */
export interface TabMeta {
  period: ResolvedPeriod
  coverage: Coverage
  dataNotes: DataNote[]
  dateField: string
  dateFieldOptions: { value: string; label: string }[]
}

/**
 * Logistics is three endpoints, not one — /dashboard/logistics/{shipments,
 * packing,transport} — matching the three tabs on the page. Each returns
 * finished figures plus its own filter option lists, the same contract as the
 * purchases and inventory dashboards, so the views render them directly.
 *
 * There is no documentation endpoint: that tab was removed for lack of data.
 */

export interface LabelValue {
  [key: string]: unknown
  label: string
  value: number
}

function buildQuery(filters: object): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (Array.isArray(value)) {
      for (const v of value) params.append(key, String(v))
    } else if (value) {
      params.set(key, String(value))
    }
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

// ------------------------------------------------------------------ shipments

export interface ShipmentKpis {
  shipments_shown: number
  delivered: number
  not_yet_linked: number
  total_cost: number
  avg_cost_per_kg: number
  countries: number
}

export interface ShipmentsFilters {
  status?: string[]
  stage?: string[]
  shipping_line?: string[]
  country?: string[]
  customer?: string[]
  etd_from?: string
  etd_to?: string
  search?: string
  /** The dashboard-wide window. Omit BOTH for the current month. */
  date_from?: string
  date_to?: string
  /** Which date it applies to: etd (sailing) | eta (arrival). */
  date_field?: string
}

export interface OrderTypeSplit {
  export: number
  local: number
  /** Orders whose type the sheet never states — shown rather than folded
   *  into either side. */
  not_stated: number
  total: number
}

export interface OrderTypeCounts extends OrderTypeSplit {
  windowed: boolean
  /** Orders with NO date in the chosen column, so they fall in no period at
   *  all. NOT ONE local order carries a business date, so without this the
   *  local tile is a silent zero that reads as "we do no local business". */
  undated: OrderTypeSplit
}

export interface ShipmentsResponse extends TabMeta {
  kpis: ShipmentKpis
  references: {
    orders: ReferenceSet
    delivered: ReferenceSet
    not_linked: ReferenceSet
    export: ReferenceSet
    local: ReferenceSet
    not_stated: ReferenceSet
    /** The orders no window reaches. */
    undated: ReferenceSet
  }
  /** Export against local IN THE WINDOW, with the undated orders alongside. */
  orderTypeCounts: OrderTypeCounts
  statusSplit: LabelValue[]
  costPerKgByCountry: LabelValue[]
  statuses: string[]
  stages: string[]
  shippingLines: string[]
  countries: string[]
  customers: string[]
}

export async function getShipmentsDashboard(filters: ShipmentsFilters = {}): Promise<ShipmentsResponse> {
  const { data } = await apiFetch<{ data: {
    kpis: ShipmentKpis
    status_split: LabelValue[]; cost_per_kg_by_country: LabelValue[]
    statuses: string[]; stages: string[]; shipping_lines: string[]
    countries: string[]; customers: string[]
    references: ShipmentsResponse['references']
    order_type_counts: OrderTypeCounts
    period: ResolvedPeriod
    coverage: Coverage
    data_notes: DataNote[]
    date_field: string
    date_field_options: { value: string; label: string }[]
  } }>(`/dashboard/logistics/shipments${buildQuery(filters)}`)
  return {
    kpis: data.kpis,
    statusSplit: data.status_split,
    costPerKgByCountry: data.cost_per_kg_by_country,
    statuses: data.statuses,
    stages: data.stages,
    shippingLines: data.shipping_lines,
    countries: data.countries,
    customers: data.customers,
    references: data.references,
    orderTypeCounts: data.order_type_counts,
    period: data.period,
    coverage: data.coverage,
    dataNotes: data.data_notes,
    dateField: data.date_field,
    dateFieldOptions: data.date_field_options,
  }
}

// -------------------------------------------------------------------- packing

export interface PackingKpis {
  packing_jobs_shown: number
  packed: number
  total_cost: number
  avg_rfd_delay_days: number | null
  categories: number
}

export interface PackingFilters {
  status?: string[]
  works?: string[]
  product_category?: string[]
  business_type?: string[]
  customer?: string[]
  packing_from?: string
  packing_to?: string
  search?: string
  date_from?: string
  date_to?: string
  /** packed | rfd */
  date_field?: string
}

export interface PackingResponse extends TabMeta {
  kpis: PackingKpis
  references: {
    packages: ReferenceSet
    packed: ReferenceSet
  }
  statusSplit: LabelValue[]
  byCategory: LabelValue[]
  byBusinessType: LabelValue[]
  byCustomer: LabelValue[]
  statuses: string[]
  works: string[]
  productCategories: string[]
  businessTypes: string[]
  customers: string[]
}

export async function getPackingDashboard(filters: PackingFilters = {}): Promise<PackingResponse> {
  const { data } = await apiFetch<{ data: {
    kpis: PackingKpis
    status_split: LabelValue[]; by_category: LabelValue[]
    by_business_type: LabelValue[]; by_customer: LabelValue[]
    statuses: string[]; works: string[]; product_categories: string[]
    business_types: string[]; customers: string[]
    references: PackingResponse['references']
    period: ResolvedPeriod
    coverage: Coverage
    data_notes: DataNote[]
    date_field: string
    date_field_options: { value: string; label: string }[]
  } }>(`/dashboard/logistics/packing${buildQuery(filters)}`)
  return {
    kpis: data.kpis,
    statusSplit: data.status_split,
    byCategory: data.by_category,
    byBusinessType: data.by_business_type,
    byCustomer: data.by_customer,
    statuses: data.statuses,
    works: data.works,
    productCategories: data.product_categories,
    businessTypes: data.business_types,
    customers: data.customers,
    references: data.references,
    period: data.period,
    coverage: data.coverage,
    dataNotes: data.data_notes,
    dateField: data.date_field,
    dateFieldOptions: data.date_field_options,
  }
}

// ------------------------------------------------------------------ transport

export interface TransportKpis {
  jobs_shown: number
  delivered: number
  in_progress: number
  total_freight: number
  total_savings: number
}

export interface TransportFilters {
  status?: string[]
  movement_type?: string[]
  source?: string[]
  payment_status?: string[]
  transporter?: string[]
  customer?: string[]
  province?: string[]
  exec_from?: string
  exec_to?: string
  search?: string
  date_from?: string
  date_to?: string
  /** etd (execution) | eta (arrival at works) */
  date_field?: string
}

export interface TransportResponse extends TabMeta {
  kpis: TransportKpis
  references: {
    jobs: ReferenceSet
    delivered: ReferenceSet
    in_progress: ReferenceSet
  }
  statusSplit: LabelValue[]
  byMovementType: LabelValue[]
  byTransporter: LabelValue[]
  byPaymentStatus: LabelValue[]
  byCustomer: LabelValue[]
  byProvince: LabelValue[]
  statuses: string[]
  /** Includes "Unclassified" — 207 jobs genuinely state no movement type. */
  movementTypes: string[]
  sources: string[]
  paymentStatuses: string[]
  transporters: string[]
  customers: string[]
  provinces: string[]
}

export async function getTransportDashboard(filters: TransportFilters = {}): Promise<TransportResponse> {
  const { data } = await apiFetch<{ data: {
    kpis: TransportKpis
    status_split: LabelValue[]; by_movement_type: LabelValue[]
    by_transporter: LabelValue[]; by_payment_status: LabelValue[]
    by_customer: LabelValue[]; by_province: LabelValue[]
    statuses: string[]; movement_types: string[]; sources: string[]
    payment_statuses: string[]; transporters: string[]
    customers: string[]; provinces: string[]
    references: TransportResponse['references']
    period: ResolvedPeriod
    coverage: Coverage
    data_notes: DataNote[]
    date_field: string
    date_field_options: { value: string; label: string }[]
  } }>(`/dashboard/logistics/transport${buildQuery(filters)}`)
  return {
    kpis: data.kpis,
    statusSplit: data.status_split,
    byMovementType: data.by_movement_type,
    byTransporter: data.by_transporter,
    byPaymentStatus: data.by_payment_status,
    byCustomer: data.by_customer,
    byProvince: data.by_province,
    statuses: data.statuses,
    movementTypes: data.movement_types,
    sources: data.sources,
    paymentStatuses: data.payment_statuses,
    transporters: data.transporters,
    customers: data.customers,
    provinces: data.provinces,
    references: data.references,
    period: data.period,
    coverage: data.coverage,
    dataNotes: data.data_notes,
    dateField: data.date_field,
    dateFieldOptions: data.date_field_options,
  }
}
