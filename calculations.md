# Dashboard calculations

Every figure on every dashboard is **derived at request time** from the source
tables — nothing dashboard-specific is stored. Money is always converted at the
rate booked on the record, never a live rate. Filter option lists are built
dynamically from the whole table so a dropdown shows every value present, not
just the ones on the current page.

This file covers the **overview**, **imports**, **logistics**, **purchases** and
**inventory** dashboards.

Each dashboard lives under `app/dashboard/<name>/` with the same four files:
`calculations.py` (the formulas below), `helpers.py` (the queries),
`serializers.py` (row + aggregate assembly) and `routes/` (the endpoint).

---

## Overview — `GET /dashboard/overview`

**Sources:** every module at once — `consignments` (+ item lines),
`purchases_data`, `logistics_consignments`, `trucking_consignments`, `stock`,
`issuance`. Permission: `can_view_overview_dashboard`.

Unlike the per-module dashboards this one **never materializes rows** — every
figure is a single SQL aggregate, so the whole payload builds in well under a
second despite spanning ~49k issuance rows.

**Params:** `date_from`, `date_to` (both omitted → **month to date**; either one
given → that custom range, echoed back under `period`), and `dead_stock_days`
(default **180**, 1–1825).

Two conventions run through the whole endpoint:

- **Every ratio ships with its denominator** (`*_basis`). Several rest on a small
  slice of the book, so a bare percentage would read as a fact about the whole
  table. The front end shows the basis beside the number.
- **A period figure is never silently zero.** Where the window holds no rows the
  payload says so, because the loaded data currently ends before the current
  month and an unqualified "Rs 0" reads as a broken tile.

### Imports

| Figure | Formula |
|---|---|
| `period_value.value` | Σ stored `pkr_total` where `etd` ∈ window |
| `period_value.undated` | consignments with a `pkr_total` but **no ETD** — they fall in *no* window, so they are reported separately rather than vanishing from every period at once |
| `in_process` | count where status ∉ {Arrived at Works, Order Cancelled}, split across the **six-stage pipeline** the imports list uses (`STAGE_GROUPS`, minus Closed) |
| `shafts` | consignments carrying a shaft line, split in-process vs arrived, + `arrived_pct` |

**ETD is the activity date**, not gate-out: gate-out is populated on well under
half the book and stops months earlier, so windowing on it would under-report a
period rather than measure it.

**Shafts are matched on `consignment_items.item_name`** against the curated
`SHAFT_ITEMS` list (reused from `app/reports/helpers.py`) — *not* through the
item master. Those names do not exist in `items`, and the line keeps its own copy
of the name anyway (imports rule 12), so the line is the only reliable match.

### Local procurement (all period-bounded, on `purchase` date)

| Figure | Formula |
|---|---|
| `period_value` | Σ `amount`, line count, Σ `qty` where `purchase` ∈ window |
| `category_split` | top **4** categories by value + a single **Other** bucket, each with `share_pct`; category comes from the item master via `item_code`, unresolved lines group as **Uncategorised** (dropped lines would make the shares fail to add up to the total shown beside them) |
| `delay.delay_pct` | `required_d < purchase` ÷ lines having a `required_d` |
| `cycle_time` | **two** readings, both returned |

`cycle_time` gives `store_to_purchase_days` (`ppc_store` → `purchase`) **and**
`po_to_purchase_days` (`po_date` → `purchase`). Which one "demand to purchase"
means is a business decision, so the backend returns both rather than baking in a
guess. Rows where the demand date sits *after* the purchase are excluded — they
are data errors, and counting them as negative lead time would drag the average
below what any real cycle took.

### Logistics (lifetime, not period — "till yet … handled" is a running total)

| Figure | Formula |
|---|---|
| `trucking_cost` | Σ `actual_freight` grouped by `movement_type`, + `quoted_freight` and `share_pct` per bucket |
| `shipments_handled` | standard logistics orders (`job_kind = 'standard'`) + import consignments |

**There is no "Local" movement type and none can be inferred.** Jobs with a NULL
`movement_type` (currently 191) get their own **Unclassified** bucket rather than
being folded into a category they may not belong to; they carry no actual freight,
so they move the job count and not the cost.

### Stores (a snapshot — not period-bounded; the two windows below are its own)

| Figure | Formula |
|---|---|
| `stock_value` | Σ `stock_qty_amount`, Σ `available_amount`, line count |
| `value_by_store` | the same grouped by `branch`, with `share_pct` |
| `stock_days` | per branch **and** total: stock value ÷ (value issued over the window ÷ window days) |
| `dead_stock` | lines with `stock_qty_amount > 0` and **no issuance** for that `(item_code, branch)` within `dead_stock_days` |

**Days of stock is measured in rupees, not units** — a store holds many units of
incomparable things; summing bolts and shafts is meaningless, summing their
rupees is not. The consumption window is **90 days** (matching the inventory
dashboard so the two agree) and ends at the **latest issuance in the data**, not
today: the data is historical, and anchoring to today would measure an empty
window and report every store as having infinite runway. A branch with no
consumption history has `days_of_stock: null` and sorts **last**, so it never
reads as the healthiest store on the list.

`dead_stock` also returns **`history_days`** (the span of the issuance table,
currently ~350) and **`exceeds_history`**. Once the threshold reaches back past
the first issuance, the figure is really "never issued in the data we hold" and
raising the threshold further cannot change it — the flag tells the front end to
say so.

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

### KPI-document figures (imports)

From `Supply_Chain_KPI's.docx`, computed over the **same filtered consignments**
as everything above, and returned alongside it — nothing was replaced.

| Key | Formula |
|---|---|
| `import_spend` | Σ **stored** `pkr_total` (+ how many consignments had none) |
| `demands` | received = row count · processed = terminal status (Arrived at Works **or** Order Cancelled) · in_process = the rest, so the three always reconcile |
| `delay` | late = arrival > `required_date`, where arrival is `gate_out_date` falling back to `eta` |
| `supplier_pareto` | suppliers by spend desc, each with `share_pct` and a running `cumulative_pct` |
| `category_delays` | delay stats per item-master category |

**`import_spend` uses the stored `pkr_total`; `kpis.total_value_pkr` recomputes
from the item lines.** The two therefore disagree (Rs 964.8M vs Rs 987.7M) —
they are different measures, not a bug, and both are kept because the original
tile predates the stored column. Imports rule 4 makes the **stored** figure the
one that matches a printed report, so `import_spend` is the one to trust.

**`delay` falls back to ETA** so a consignment still in transit counts as late
the moment its ETA passes the required date, rather than dropping out of the
measure until it lands. `measured_on_actual_arrival` says how many of the basis
used a real gate-out rather than an ETA.

**`category_delays` counts a consignment once per distinct category it
carries** — a mixed consignment genuinely delays all of them, and splitting the
delay between them would understate each. Lines that do not resolve to an item
master (most of them today) fall into **Uncategorised** rather than vanishing.
Rows are ranked by **number of delayed consignments, not percentage**: ranking
on percentage floats a category with one delayed consignment at 100% above one
with 17 of 34, which is noise on top of the real problem.

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

### KPI-document figures (local procurement) — `procurement_kpis`

The document asks for four; **two already existed** (`kpis.total_value` and
`kpis.on_time_pct`), so only the missing two were added.

| Key | Formula |
|---|---|
| `total_quantity` | Σ `qty` |
| `avg_delay_days` | mean days late, **late lines only** |
| `avg_days_vs_required` | mean of `purchase − required_d` across all comparable lines |
| `delayed_lines` / `basis` | the counts behind both averages |

The document defines the delay as *"AVERAGE of Required Date – Purchase Date"*,
which is **negative** when a line is late. The sign is flipped here so
`avg_delay_days` is positive when purchasing ran late — how a figure labelled
"delay" is read. Both averages are returned because they answer different
questions: how bad the late ones are (26.0 days), versus whether purchasing runs
early or late overall (1.4 days).

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

### KPI-document figure (stores) — `purchase_vs_issuance_by_category`

What each item category cost to **buy** against what it cost to **consume**.
The two sides come from different tables (`purchases_data`, `issuance`), summed
separately in SQL — issuance alone is ~49k rows and is never materialized.

Two things make this figure trustworthy, and both were bugs before they were
fixed:

- **Both sides are clipped to the window they SHARE**, returned as `period`.
  `purchases_data` currently holds **one month** (2026-06-09 → 2026-07-09) while
  `issuance` holds a **full year**. Summing each in full compares a month of
  buying against a year of consuming and reports every category as consuming
  ~10× what it buys — a fact about the data's coverage wearing the costume of a
  fact about the business. The window is derived, not hard-coded, so it widens
  on its own once more purchase history is loaded.
- **It is NOT filtered by branch** (`branch_filtered: false`).
  `purchases_data.branch` holds short codes (`QEN`, `QCL`, `QB2`, `QE`, `QBL`,
  `QE-II`, `IOL`); `issuance.branch` and `stock.branch` hold full company names.
  The vocabularies share no values, so a branch filter matches the issuance side
  and **nothing** on the purchases side, reporting a category as pure consumption
  with zero spend. Company-wide and honest beats filtered and wrong. Mapping the
  codes to names belongs in the loader, agreed with the business — `QE` vs `QEN`
  vs `QE-II` is not something to guess at.

A category present on one side and absent on the other still appears with zero
on the missing side; rows rank by the **larger** of the two sides, so a category
that is huge on consumption but barely purchased still makes the chart.

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

#### KPI-document figures (shipments)

Per order: **`is_dispatched`** = has an `actual_arrival_date`;
**`arrival_delay_days`** = `actual_arrival_date − cro_arrival_date` (null if
either is missing).

| Key | Formula |
|---|---|
| `dispatch_kpis.total_dispatches` | orders with an actual arrival |
| `.total_weight_dispatched_kg` | Σ item `gross_weight` over those orders |
| `.on_time_dispatches` / `.delayed_dispatches` / `.on_time_pct` / `.basis` | measured only on orders that ALSO have a planned arrival |
| `container_type_usage` | counted over the **container rows** of the filtered orders (one order can ship several types) |
| `customer_delays` | customers whose orders ran more than **7 days** late (threshold is a parameter) |

**Dispatched and on-time have different denominators by design.** Dispatch needs
only an actual arrival (141 orders); on-time needs a planned one to compare
against (104). Status cannot substitute — the loaded vocabulary has no
"dispatched" value and an order can sit at "Transportation" indefinitely.
Weight stays in **kg**, the unit the data is in; tonnes are a display choice.

**`dispatch_by_segment` returns `has_segmentation`, and it is currently
`false`.** The segment is `department` (Sugar / Cement), populated on 810 orders
and NULL on 614 — and the 614 are precisely the ones carrying arrival dates. So
every order the chart can measure is Unassigned and it draws one meaningless
bar. The flag lets the front end show "no segment data" instead. The figures are
right; the segmentation is missing. **Filling `department` on delivered orders is
what unlocks this chart** — no code change is needed.

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

#### KPI-document figures (packing) — `packing_cost_kpis`

Package count and weight are solid. **The cost figures are not**: no package in
the loaded data carries an `actual_packing_cost` and only **25 of 962** carry a
quoted one, so savings and saving-per-kg have nothing to compute from.

Rather than return a confident Rs 0 — which reads as "we packed for free" —
every cost figure ships with the number of packages it was measured over
(`packages_with_quoted_cost`, `packages_with_actual_cost`, `savings_basis`), and
**`total_savings` / `avg_saving_per_kg` stay `null`** until both sides of the
subtraction exist on the same package. Summing two differently-populated columns
and subtracting would invent a number. The front end shows "awaiting data".

| Key | Status today |
|---|---|
| `total_packages`, `total_weight_kg`, `packages_with_weight` | real (962 packages, 604 weighed) |
| `total_quoted_cost` | thin — 25 packages |
| `total_actual_cost` | **no data** — 0 packages |
| `total_savings`, `avg_saving_per_kg` | **null** — needs both figures on one package |

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
