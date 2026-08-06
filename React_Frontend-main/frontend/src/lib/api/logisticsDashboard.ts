import { apiFetch } from './client'

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
}

export interface ShipmentsResponse {
  kpis: ShipmentKpis
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
}

export interface PackingResponse {
  kpis: PackingKpis
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
}

export interface TransportResponse {
  kpis: TransportKpis
  statusSplit: LabelValue[]
  byMovementType: LabelValue[]
  byTransporter: LabelValue[]
  byPaymentStatus: LabelValue[]
  byCustomer: LabelValue[]
  byProvince: LabelValue[]
  statuses: string[]
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
  }
}
