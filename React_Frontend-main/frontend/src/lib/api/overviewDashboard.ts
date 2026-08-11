import { apiFetch } from './client'
import type { Coverage, ResolvedPeriod } from '@/components/PeriodFilter'
import type { DataNote } from '@/components/DataNotes'
import type { ReferenceSet } from '@/components/ReferenceList'

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
  /** Distinct consignments having a line in the window, and how many lines. */
  lines: number
  value: number
  consignments: number
  basis: string
  undated: { consignments: number; value: number }
}

/** A figure that is a SET of records: how many, and how much they are worth.
 *  Every related tile uses this shape so a row of them can be read across. */
export interface CountAndValue {
  count: number
  value: number
  /** Share of the section's total money, where one is meaningful. */
  value_pct?: number | null
}

interface SectionMeta {
  /** null only where a section has no date column at all. */
  period: ResolvedPeriod | null
  date_field: string | null
  /** What the source holds against what the window caught — drives the
   *  "latest data is ..." line and the jump to it. */
  coverage: Coverage
  /** Coverage problems behind this section's figures. Empty when the columns
   *  it depends on are fully populated. */
  data_notes: DataNote[]
}

export interface OverviewImports extends SectionMeta {
  period_value: ImportsPeriodValue
  /** `count` is the shared key; `total` is its alias for the stage chart. */
  in_process: CountAndValue & { total: number; by_stage: { stage: string; consignments: number }[] }
  arrived: CountAndValue
  cancelled: CountAndValue
  /** More than `grace_days` past the required date. `basis` is how many
   *  consignments carry both dates and could be measured at all. */
  delayed: CountAndValue & { basis: number; grace_days: number; delay_pct: number | null }
  /** Echoed back so the section can label its tiles as the shaft subset. */
  shafts_only: boolean
  shafts: { in_process: number; arrived: number; total: number; arrived_pct: number | null }
  /** The consignments behind each tile. A cross-module rollup is the figure a
   *  reader can least easily check, so every one of them opens its records. */
  references: {
    period_value: ReferenceSet
    in_process: ReferenceSet
    arrived: ReferenceSet
    cancelled: ReferenceSet
    delayed: ReferenceSet
  }
}

export interface OverviewProcurement extends SectionMeta {
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
  /** Grouped by PO, like every figure above them. */
  references: {
    period_value: ReferenceSet
    delay: ReferenceSet
  }
}

/** There is no "Local" movement type in the data and none can be inferred, so
 *  unclassified jobs get their own bucket rather than being folded into a
 *  category they may not belong to. */
export interface OverviewLogistics extends SectionMeta {
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
  shipments_handled: {
    export_shipments: number
    import_shipments: number
    total: number
    /** How many records could be dated at all — the export side is mostly
     *  undated, so a small windowed count needs explaining. */
    coverage: {
      export_datable: number
      export_total: number
      import_datable: number
      import_total: number
    }
  }
  /** One figure from each of the section's three areas, so "logistics" stops
   *  meaning "trucking". Each carries its own basis, because they rest on
   *  different — and in one case small — slices of the book. */
  packed_tonnage: { kilograms: number; tonnes: number; packages: number; basis: number }
  /** A RATE, not a second cost total. null when nothing weighed was moved. */
  freight_per_kg: { rate: number | null; freight: number; kilograms: number; basis: number }
  /** Sailing to arrival. Only 23% of orders record both dates. */
  transit_time: { days: number | null; basis: number }
  /** Export against local IN THE WINDOW. `undated` is the orders no window
   *  reaches — not one local order carries a business date, so without it the
   *  local tile is a silent zero. */
  order_types: {
    export: number
    local: number
    not_stated: number
    total: number
    windowed: boolean
    undated: { export: number; local: number; not_stated: number; total: number }
  }
  /** `by_movement` is keyed by movement type, with the NULL group under
   *  "Unclassified" — the same name its tile shows. */
  references: {
    trucking_cost: ReferenceSet
    by_movement: Record<string, ReferenceSet>
    shipments_handled: ReferenceSet
    export_orders: ReferenceSet
    local_orders: ReferenceSet
    undated_orders: ReferenceSet
  }
}

export interface OverviewStores extends SectionMeta {
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
  /** What was ISSUED in the section's window. Items are counted by item code,
   *  folded across branches — the same unit the Inventory dashboard uses, so
   *  the number is identical on both screens. */
  issuance: { value: number; items: number; lines: number; quantity: number }
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
  /** Both lists fold onto the ITEM across the branches stocking it, matching
   *  how the Inventory dashboard counts. */
  references: {
    stock_value: ReferenceSet
    dead_stock: ReferenceSet
    issuance: ReferenceSet
  }
}

export interface DateFieldOption { value: string; label: string }

export interface OverviewDashboardResponse {
  /** Selectable date columns, named by the backend so the screen and the
   *  server cannot disagree about what is filterable. */
  date_field_options: {
    imports: DateFieldOption[]
    purchases: DateFieldOption[]
    logistics: DateFieldOption[]
    stores: DateFieldOption[]
  }
  imports: OverviewImports
  procurement: OverviewProcurement
  logistics: OverviewLogistics
  stores: OverviewStores
}

/** One window per section — a consignment's arrival, a PO's date and a truck's
 *  run are different events, so a single shared filter compared unlike things.
 *  Omit BOTH bounds of a section for the backend's default, the current month. */
export interface OverviewDashboardFilters {
  imports_date_from?: string
  imports_date_to?: string
  /** eta_works | required_date */
  imports_date_field?: string

  purchases_date_from?: string
  purchases_date_to?: string
  /** po_date | purchase */
  purchases_date_field?: string

  logistics_date_from?: string
  logistics_date_to?: string
  /** etd | eta */
  logistics_date_field?: string

  /** Stock is a snapshot; this window applies to what was ISSUED. */
  stores_date_from?: string
  stores_date_to?: string

  /** How long stock must sit unissued to count as dead. Default 180. */
  dead_stock_days?: number

  /** Narrows every imports figure to shaft consignments — the Shafts tab. */
  shafts_only?: boolean
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
