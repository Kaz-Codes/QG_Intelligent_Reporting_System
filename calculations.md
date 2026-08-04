# Dashboard calculations

Every figure on every dashboard is **derived at request time** from the source
tables — nothing dashboard-specific is stored. Money is always converted at the
rate booked on the record, never a live rate. Filter option lists are built
dynamically from the whole table so a dropdown shows every value present, not
just the ones on the current page.

This file covers the **imports**, **logistics**, **purchases** and **inventory**
dashboards. (The overview dashboard also exists; it follows the same shape.)

Each dashboard lives under `app/dashboard/<name>/` with the same four files:
`calculations.py` (the formulas below), `helpers.py` (the queries),
`serializers.py` (row + aggregate assembly) and `routes/` (the endpoint).

---

## Imports — `GET /dashboard/imports`

**Source:** `consignments` + their item lines. **Filters** (single value):
`work` (branch), `supplier`, `country`, `item_category`, `status`,
`mode_of_shipment`, `from_date`/`to_date`.

### Per-consignment value
```
consignment PKR value = ( Σ over item lines: quantity × unit_price ) × exchange_rate
```
A line with no price is skipped (not counted as zero); a consignment with no
priced line **or** no booked exchange rate has a PKR value of 0.

### KPIs
| KPI | Formula |
|---|---|
| `total_value_pkr` | Σ consignment PKR value |
| `consignments_shown` | row count |
| `open` | count where `current_status` ≠ "Arrived at Works" |
| `under_clearance` | count where `current_status` = "Under Custom Clearance" |
| `suppliers` | distinct `supplier_id` count |

### Charts
- **status_split** — count per `current_status`, in the canonical status order, present statuses only (no empty donut slices).
- **value_by_country** — Σ PKR value grouped by `origin`, top 8.
- **value_by_supplier** — Σ PKR value grouped by supplier name, top 8.
- **value_by_branch** — Σ PKR value grouped by branch name, top 8.
- **monthly_value_trend** — Σ PKR value grouped by month of `eta_works` (falling back to `etd` → `eta` → `cargo_readiness_date`), oldest month first. *(Not `po_date`/`created_at`: `po_date` isn't loaded and every bulk-loaded row shares one `created_at`, which would collapse the trend to a single point.)*

### Option lists
`works`, `suppliers`, `countries`, `item_categories`, `status`.

---

## Purchases — `GET /dashboard/purchases`

**Source:** `purchases_data` — a **flat** table, one row per purchase line (PO
fields repeat per item row). **Filters** (multi-select): `status`, `supplier`,
`branch`, `item_category`, `mop`, `sourcing_o`, plus `po_from_date`/`po_to_date`
and `search`.

### Derived per row
- **status**
  - no `purchase` date → **Pending**
  - `required_d < purchase` → **Delayed** (purchased late)
  - otherwise → **Completed**
- **days_overdue** = `(purchase − required_d).days` when Delayed, else `null`.

### KPIs
| KPI | Formula |
|---|---|
| `orders_count` | row count |
| `total_value` | Σ `amount` |
| `avg_order_value` | `total_value / orders_count` |
| `pending_orders` / `completed_orders` / `delayed_orders` | counts by derived status |
| `on_time_pct` | `completed / (completed + delayed) × 100` |
| `top_supplier` / `top_supplier_amount` | supplier with the largest Σ `amount` |

### Charts
- **status_split** — Pending / Completed / Delayed counts.
- **value_by_supplier**, **value_by_branch** — Σ `amount`, top 8.
- **overdue_buckets** — Delayed rows bucketed by `days_overdue` into the four
  standard aging tiers (`0-30` / `31-60` / `61-90` / `90+ days`), in that fixed
  order (empty tiers kept). Feeds the "Delayed Orders — Days Overdue" bar chart.
- **monthly_value_trend** — Σ `amount` by month of `purchase` (falling back to `po_date`).

### Option lists
Returns the aggregates above plus dynamic filter option lists: `statuses`,
`suppliers`, `branches`, `item_categories`, `mops`, `sourcing_officers`. These
are built from cheap `SELECT DISTINCT` queries (**not** by loading the whole
table into ORM objects — that was the multi-second floor on every request). The
per-row table was dropped from the dashboard, so no row list is shipped — the
payload stays a few KB.

### Notes
- `status` is derived, so it's filtered in Python after the SQL fetch.
- `item_category` lives on the item master and is filtered via the relationship (`.has()`).
- Dropped from the original design: the `material` filter and the "view data" toggle.

---

## Inventory (stocks) — `GET /dashboard/inventory`

**Source:** `stock` (flat, one row per item+branch) + `issuance` (for the
runway) + `store_requisition` (for the reorder level). **Filters**
(multi-select): `status`, `reorder_status`, `category`, `branch`, `item`, plus
`search`.

### Reorder level (derived from requisitions, drives every row)
```
reorder level = avg daily demand × lead time × (1 + safety factor)
```
per `(item_code, branch)`:
- **avg daily demand** = Σ `req_quantity` over the last `DEMAND_WINDOW_DAYS` (ending at the latest `prepare_date` in the data) ÷ `DEMAND_WINDOW_DAYS`
- **lead time** = average of `stock_in_date − prepare_date` over completed cycles; falls back to `DEFAULT_LEAD_TIME_DAYS` when none exist
- **safety factor** = `SAFETY_FACTOR`

Computed for every item+branch that has requisition demand. Items with **no**
requisition demand fall back to the stored `Stock.reorder_level` column (a
planner's manual value).

### Other derived per row
- **stock_status**
  - `available_qty ≤ 0` → **Out of Stock**
  - `available_qty < reorder_level` → **Below Reorder**
  - otherwise → **OK**
- **reorder_status** — `available_qty < reorder_level` → **Reorder Needed**, else **Adequate**.
- **days_of_stock** (runway) = `available_qty ÷ avg daily issuance`, where avg
  daily issuance = Σ `Issuance.quantity` over the last `CONSUMPTION_WINDOW_DAYS`
  (ending at the latest `from_date`) ÷ `CONSUMPTION_WINDOW_DAYS`. Rounded to one
  decimal (not floored — a half-day runway is the most urgent, and `int()` would
  truncate it to 0). `null` when there's no issuance history **or the item is
  already out of stock** (`available ≤ 0`) — a "days remaining" figure is
  meaningless once you've run out, and those items would otherwise fill the
  "lowest days of stock" chart with zeros and hide the ones still running down.
  They are already counted as Out of Stock.

### KPIs
| KPI | Formula |
|---|---|
| `available_units` | Σ `available_qty` |
| `total_stock_qty` | Σ `stock_qty` |
| `on_hold` | Σ `hold_qty` |
| `items_shown` | count of rows with `available_qty > 0` (items you actually have — out-of-stock lines are excluded) |
| `out_of_stock` / `below_reorder` | counts by derived status |
| `at_risk_pct` | `(out_of_stock + below_reorder) / total rows × 100` (denominator is the **full** row count, not the available-only `items_shown`) |
| `total_stock_value` | Σ `stock_qty_amount` |
| `available_value` | Σ `available_amount` |

### Charts
- **stock_health** — OK / Below Reorder / Out of Stock counts (donut).
- **items_by_branch** — row count per branch.
- **at_risk_by_branch** — `(out_of_stock + below_reorder) / total × 100` per branch.
- **top_items** — Σ `stock_qty` per item, top 8.
- **lowest_days_of_stock** — rows with a runway, ascending, top 8.

### Option lists
Returns the aggregates above plus dynamic filter option lists: `statuses`,
`reorder_statuses`, `branches`, `items`, `item_categories` — built from cheap
`SELECT DISTINCT` queries, not by loading the whole `stock` table. The per-row
table was dropped from the dashboard, so no row list is shipped (the derived
rows are still built internally, only to feed the aggregates).

### Tunable constants (`app/dashboard/inventory/helpers.py`)
`CONSUMPTION_WINDOW_DAYS = 90`, `DEMAND_WINDOW_DAYS = 180`,
`DEFAULT_LEAD_TIME_DAYS = 30`, `SAFETY_FACTOR = 0.2`.

### Notes
- `stock_status`/`reorder_status` are derived, so they're filtered in Python.
- `last_restocked` was dropped — `stock` has no such date.
- `specs` comes from the item master (`Item.default_specification`).

---

## Logistics — three tabs

The logistics dashboard is **three independent endpoints**, one per frontend
tab, each with its own data source, filters and dynamic option lists. All return
aggregates + option lists only (no rows). The Documentation tab is not built —
its per-document status data was never loaded.

### Shipments — `GET /dashboard/logistics/shipments`  (source: `LogisticsConsignment`)

Per order:
- **`total_logistics_cost`** = Σ of the 13 named cost columns (`packing_cost`,
  `transportation_charges`, `container_detention`, `insurance`,
  `trucking_lhr_to_khi`, `fumigation_cost`, `lashing`, `qfl_charges`,
  `qfl_container_movement`, `custom_clearance_charges`, `port_charges`,
  `dhl_charges`, `sea_air_freight`).
- **`cost_per_kg`** = `total_logistics_cost ÷ Σ item gross_weight` (null when no weight).
- **`stage`** = roll-up of `current_status` → Pre-Shipment / In Transit /
  Customs / Delivered (best-effort map; unmapped → Pre-Shipment).

| KPI | Formula |
|---|---|
| `shipments_shown` | row count |
| `delivered` | count where `current_status` = "Delivered" |
| `not_yet_linked` | count with no `mo_no` (no export number yet) |
| `total_cost` | Σ `total_logistics_cost` |
| `avg_cost_per_kg` | mean of the per-order `cost_per_kg` |
| `countries` | distinct `origin_country` |

Charts: **status_split**, **cost_per_kg_by_country** (avg, top 8). Filters:
`status[]`, `stage[]`, `shipping_line[]`, `country[]`, `customer[]`, ETD range
(`port_in_date`), `search`.

### Packing — `GET /dashboard/logistics/packing`  (source: `LogisticsPackage` + its order)

Per package: **`rfd_delay_days`** = `(packing_date − packing_ready_date).days`
(null if either is missing).

| KPI | Formula |
|---|---|
| `packing_jobs_shown` | row count |
| `packed` | count where package `status` = "Packed" |
| `total_cost` | Σ `actual_packing_cost` |
| `avg_rfd_delay_days` | mean of `rfd_delay_days` |
| `categories` | distinct order `department` |

Charts: **status_split**, **by_category** (order `department`),
**by_business_type** (order `order_type`), **by_customer** (top 8). Filters:
`status[]`, `works[]`, `product_category[]`, `business_type[]`, `customer[]`,
packing-date range, `search` (order-level filters go through the relationship).

### Transport — `GET /dashboard/logistics/transport`  (source: `TruckingConsignment`)

Trucking has no stored job status, so:
- **`status`** = roll-up over the vehicles: all delivered → **Delivered**; some →
  **In Progress**; none → **Booked**.
- **`freight_savings`** = `max(quoted_freight − actual_freight, 0)`.
- **`customer` / `city` / `province`** are **not** on the trucking job — for a job
  that came from a logistics order (`source = 'from-logistics'`, `source_ref` =
  the order id) they are resolved from that order (a local logistics consignment
  handed to trucking carries them). Manual / import-FOB jobs have none.

| KPI | Formula |
|---|---|
| `jobs_shown` | row count |
| `delivered` / `in_progress` | counts by derived status |
| `total_freight` | Σ `actual_freight` |
| `total_savings` | Σ `freight_savings` |

Charts: **status_split**, **by_movement_type**, **by_transporter** (top 8),
**by_payment_status**, **by_customer**, **by_province**. Filters: `status[]`
(derived), `movement_type[]`, `source[]`, `payment_status[]`, `transporter[]`,
`customer[]` (resolved), `province[]` (resolved), execution range, `search`.
