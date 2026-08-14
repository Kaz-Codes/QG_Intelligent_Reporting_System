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
| `period_value.value` | Σ `CONSIGNMENT_VALUE` (booked `pkr_total`, or the item lines × exchange rate where none was booked) for every consignment with **at least one LINE** dated inside the window on `date_field` (a line's own `eta_works`, falling back to its header's where the line has none; `required_date` has no line equivalent so it always falls back) |
| `period_value.consignments` / `.lines` | consignment count, and every item line belonging to one of them (not only lines individually dated inside the window) |
| `period_value.undated` | consignments with a value but **no date reachable by any window** — no line (or header fallback) is ever dated, so they are reported separately rather than vanishing from every period at once |
| `in_process` | count where status ∉ {Arrived at Works, Order Cancelled}, split across the **six-stage pipeline** the imports list uses (`STAGE_GROUPS`, minus Closed) |
| `shafts` | consignments carrying a shaft line, split in-process vs arrived, + `arrived_pct` |

**`period_value` is HEADER-VALUED, by instruction** (`app/dashboard/whole/helpers.py::imports_period_value`)
— it deliberately matches the Imports module's own "Total Value" hero and
trend chart, which have always summed the WHOLE consignment under its header
value rather than splitting it by line. This is a reversal of the per-line
VALUING this figure used to use (see `app/dashboard/imports/calculations.py`'s
own `kpis`/`value_trend`, and CLAUDE.md's "Imports money is counted in the
month it ARRIVED" for the fuller history) — a consignment whose lines span
two months once again credits its full value to whichever month qualified it,
but the Overview and the Imports module screen now agree on the headline
number at a glance, which they did not before.

**Window MEMBERSHIP did not move with it — it is still by LINE**
(`_imports_window_membership`), the same "any line qualifies" test
`app.dashboard.imports.helpers.fetch_filtered_consigments` applies. Filtering
membership on the header column too (briefly, while the valuation reversal
above was made) undid the agreement one level up: a consignment with no header
`eta_works` but a dated line dropped out of every Overview imports figure while
the module still counted it, splitting "arrived" 5-vs-4 for the same month
even after the headline totals matched. `imports_population`,
`imports_in_process_by_stage`, `imports_delay` and their `references`
drill-downs all share the one membership helper for this reason.

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
| `dead_stock` | items (folded across every branch) that are `available_qty > 0`, **no issuance** within `dead_stock_days`, **and not purchased** within `dead_stock_days` either — see below |

**Days of stock is measured in rupees, not units** — a store holds many units of
incomparable things; summing bolts and shafts is meaningless, summing their
rupees is not.

**The formula lives in `app/dashboard/stock_runway.py` and BOTH screens call
it.** This section used to divide by a **90-day** window while its tile said "at
the last 12 months' usage", so the same warehouse read 81 days on Inventory and
54 here — two right answers to two different questions under one label. The
canonical window is **twelve months (365 days)**, ending at the **latest issuance
in the data**, not today: the data is historical, and anchoring to today would
measure an empty window and report every store as having infinite runway.

Consumption counts only issuance that **depletes stock actually held** — matched
to a stock row on `(item_code, branch)`. Counting every issuance put Rs 1.75bn
against items with no stock row at all, which cannot deplete anything on hand;
that population difference was the rest of the 81-against-58 gap once the windows
were unified. A branch with no consumption history has `days_of_stock: null` and
sorts **last**, so it never reads as the healthiest store on the list.

`dead_stock` also returns **`history_days`** (the span of the issuance table,
currently ~350) and **`exceeds_history`**. Once the threshold reaches back past
the first issuance, the figure is really "never issued in the data we hold" and
raising the threshold further cannot change it — the flag tells the front end to
say so.

**This is the SAME definition the Inventory dashboard's Dead bucket uses** —
see `derive_movement` under Inventory below, and "One dead-stock definition
too" in `CLAUDE.md`. The two used to be computed independently and disagreed
(different window, different qty field, no purchase check on either); now
both build on `app.dashboard.whole.helpers.dead_item_ids` /
`app.dashboard.inventory.calculations.derive_movement`, which encode the
identical rule, so the two screens' figures cannot drift apart again.
`dead_stock_days` (default **365**, shared with Inventory's fixed window via
`app.dashboard.period.DEAD_STOCK_WINDOW_DAYS`) stays adjustable here; only the
default had to stop disagreeing.

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
  - otherwise → **On Time**
- **days_overdue** = `(purchase − required_d).days` when Delayed, else `null`.

### KPIs
| KPI | Formula |
|---|---|
| `orders_count` | distinct POs (an order, never a line — see below) |
| `total_value` | Σ `amount` |
| `avg_order_value` | `total_value / orders_count` |
| `pending_orders` / `completed_orders` / `delayed_orders` | counts by derived ORDER status |
| `purchased_orders` | `completed + delayed` — the denominator both rates use |
| `on_time_pct` | `completed / purchased_orders × 100` |
| `delayed_pct` | `delayed / purchased_orders × 100` — sums to 100 with the above |
| `top_supplier` / `top_supplier_amount` | supplier with the largest Σ `amount` |

**ORDERS AND LINES ARE BOTH REAL, AND ARE NEVER MIXED.** Every KPI counts
ORDERS: an order's status is the worst of its lines (Pending > Delayed > On
Time), and its lateness is the **average across its late lines**, so one very
late line no longer speaks for a whole order. The reference list behind a tile
therefore counts orders too — `references.delayed` totals exactly
`delayed_orders`. The LINE-level breakdown is published separately as
`delayed_line_references`, and is a bigger number by construction: 247 delayed
orders currently contain 454 late lines. A tile reading 247 over a list reading
454 was the bug; publishing both, each labelled with its unit, is the fix.

### Charts
- **status_split** — Pending / On Time / Delayed counts.
- **value_by_supplier**, **value_by_branch** — Σ `amount`, top 8.
- **overdue_buckets** — Delayed rows bucketed by `days_overdue` into the four
  standard aging tiers (`0-30` / `31-60` / `61-90` / `90+ days`), in that fixed
  order (empty tiers kept). Feeds the "Delayed Orders — Days Overdue" bar chart.
- **monthly_value_trend** — Σ order value, one point per ORDER dated on its
  earliest date **on whichever field the window itself is filtered on**
  (`date_field` — `purchase` or `po_date`), falling back to the other field
  only when the primary is missing on a line.

  This has to track `date_field`, not hardcode `purchase`: `fetch_filtered_consignments`
  only ever includes a LINE whose own `date_field` value falls in the window,
  so when `date_field='po_date'` an order's (different, real) `purchase` date
  can legitimately sit outside it. Bucketing by a hardcoded `purchase` first
  regardless of `date_field` used to silently drop such orders from the trend
  while `kpis.orders_count` kept counting them — the trend and the KPI
  reporting a different number of orders for the same window.

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
- **days_of_stock** (per item, runway) = `available_qty ÷ avg daily issuance`,
  where avg daily issuance = Σ `Issuance.quantity` over the last
  `CONSUMPTION_WINDOW_DAYS` (ending at the latest `from_date`) ÷
  `CONSUMPTION_WINDOW_DAYS`. This is the per-item QUANTITY runway; the
  branch/overall roll-up on both this screen and the overview is the VALUE
  runway from `stock_runway.py` (see above), which is why the two are stated
  separately rather than one being derived from the other. Rounded to one
  decimal (not floored — a half-day runway is the most urgent, and `int()` would
  truncate it to 0). `null` when there's no issuance history **or the item is
  already out of stock** (`available ≤ 0`) — a "days remaining" figure is
  meaningless once you've run out, and those items would otherwise fill the
  "lowest days of stock" chart with zeros and hide the ones still running down.
  They are already counted as Out of Stock.

### KPIs
Counted over ITEMS (`group_by_item` — stock folded onto `item_code`, summed
across the branches that hold it), not stock lines: the question is how many
items the business holds, not how many `(item, branch)` records it keeps.

| KPI | Formula |
|---|---|
| `items_total` | count of items |
| `items_shown` | count of items with `available_qty > 0` (items you actually have — out-of-stock ones are excluded) |
| `out_of_stock` / `below_reorder` | counts by derived `stock_status` |
| `total_stock_value` | Σ `stock_qty_amount` |
| `available_value` | Σ `available_amount` |

**Removed** (see `CLAUDE.md`'s "Figures deliberately removed"): `available_units`
/ `total_stock_qty` / `on_hold` (quantity summed across incomparable units —
kg + pcs + litres — meaningless; value is the comparable measure), `at_risk_pct`
/ `top_items` (replaced by the movement split below, which says the same thing
with a reason attached).

### Movement: Fast / Slow / Dead (`derive_movement`)

Replaces "at risk", which was derived from the reorder level alone — it said
an item was in trouble without saying whether anybody actually wants it.
Movement answers that from real issuance, checked in this order:

1. **Fast** — issued within the last `MONTHS_3_DAYS` (92 days).
2. **Slow** — issued within the last `MONTHS_12_DAYS` (365 days) but not the last 92.
3. **Dead** — nothing issued in `MONTHS_12_DAYS`, `available_qty > 0` (not
   `stock_qty` — nothing available is nothing sitting idle, whether depleted
   or fully on hold), **and** not purchased in `MONTHS_12_DAYS` either — an
   item bought last week has not had the chance to be issued yet, which is
   not the same thing as stock nobody wants.
4. Anything that fails the Dead gate on `available_qty` or the purchase check
   is **unclassified** (`movement: null`) — it shows up in none of the three
   buckets, rather than being folded into Dead.

Both windows end at the **latest issuance in the data**, not today (the data
is historical). `MONTHS_12_DAYS` is shared with the Overview's `dead_stock`
figure via `app.dashboard.period.DEAD_STOCK_WINDOW_DAYS` — see `CLAUDE.md`'s
"One dead-stock definition too".

**Purchase recency is matched by branch**, via `PURCHASES_BRANCH_TO_STOCK_BRANCH`
(`QCL`→Qadcast, `QE`→Qadbros Engineering, `QEN`→Qadri Engineering,
`QB2`→Qadri Brothers Unit-II — a mapping given by the business, not derived;
`QBL`/`QE-II`/`IOL` are deliberately unmapped and filtered out of the check
entirely). The per-branch view (`serialize_row`, feeding `movement_by_branch`)
matches the exact `(item_code, branch)` pair; the folded, company-wide view
(`group_by_item`, feeding everything below) checks every KNOWN branch, not
just the ones the item's current stock snapshot happens to list — restricting
it to the snapshot's own branches undercounted for the same reason the
issuance fold below once did.

**Issuance is also folded per item_code, not derived from the stock rows.**
`group_by_item` used to sum each stock ROW's own attached issuance value —
which only ever covers branches the Stock table still has a row for. An item
issued at a branch with no remaining stock row (903 item codes) was invisible
to that fold, silently understating the item's issuance and sometimes calling
it dead despite having moved. `issuance_totals_by_item` (grouped by item_code
alone, across every branch that issued it) is the authoritative source now,
overriding the per-row fold when available.

| Figure | Formula |
|---|---|
| `movement_split` | items + value per class (Fast / Slow / Dead), each with `items_pct` / `value_pct` |
| `movement_kpis.dead_items` / `dead_value` | count / Σ `stock_qty_amount` of Dead items |
| `movement_kpis.dead_value_pct` | `dead_value / total_stock_value × 100` (denominator is every item's stock value, not just Dead's) |
| `movement_kpis.issued_value_12m` / `issued_value_3m` | Σ issued value over the two windows, folded per item — the same numbers `movement` is derived from, so they cannot disagree |
| `movement_by_branch` | Fast / Slow / Dead counts + Σ dead value, **per branch** — uses the per-branch (not folded) classification |

### Charts
- **stock_health** — OK / Below Reorder / Out of Stock counts (donut).
- **items_by_branch** — row count per branch.
- **movement_by_branch** — see table above; replaces `at_risk_by_branch`.
- **lowest_days_of_stock** — rows with a runway, ascending, top 8.

### Option lists
Returns the aggregates above plus dynamic filter option lists: `statuses`,
`reorder_statuses`, `branches`, `items`, `item_categories` — built from cheap
`SELECT DISTINCT` queries, not by loading the whole `stock` table. The per-row
table was dropped from the dashboard, so no row list is shipped (the derived
rows are still built internally, only to feed the aggregates).

### Tunable constants (`app/dashboard/inventory/helpers.py`)
`CONSUMPTION_WINDOW_DAYS = 90`, `DEMAND_WINDOW_DAYS = 180`,
`DEFAULT_LEAD_TIME_DAYS = 30`, `SAFETY_FACTOR = 0.2`,
`MONTHS_12_DAYS = 365` (= `app.dashboard.period.DEAD_STOCK_WINDOW_DAYS`,
shared with the Overview's `dead_stock_days` default), `MONTHS_3_DAYS = 92`.

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
  with zero spend. Company-wide and honest beats filtered and wrong.

  A mapping for four of the seven codes now exists and IS confirmed by the
  business — `QCL`→Qadcast, `QE`→Qadbros Engineering, `QEN`→Qadri Engineering,
  `QB2`→Qadri Brothers Unit-II (`QBL`/`QE-II`/`IOL` deliberately left unmapped;
  see Inventory's Movement section above) — but it is used only where dead
  stock needs it. This chart stays unfiltered on purpose even so: three of the
  seven codes still have no branch, and silently dropping their spend would be
  worse than not filtering at all.

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
