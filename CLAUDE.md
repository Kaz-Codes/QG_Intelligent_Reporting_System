# Qadri Group ERP

Internal ERP for Qadri Group, replacing the manual Excel sheets that still run
the business (imports status, logistics, trucking, purchases, stores/stock).
Runs on the office LAN, ~10–30 users, not internet-facing.

Business rules are **not to be invented** — if something is ambiguous, stop and
ask rather than guessing. A wrong assumption baked into the data model is
expensive; a question is cheap.

> **Dashboard formulas live in `calculations.md`, not here.** This file is the
> architecture + implementation reference for everything else.

---

## Stack (as built)

The original plan was Django + server-rendered templates; it was built as a
**FastAPI API + a separate React SPA** instead. Treat the following as the real
stack — do not reintroduce Django/templates.

**Backend** (`app/`)
- FastAPI, SQLAlchemy 2.0 (`Mapped` / `mapped_column`), PostgreSQL, Python 3.12 (venv).
- Pydantic schemas for request bodies; plain dict serializers for responses.
- Cookie-based auth (an httpOnly session cookie set by `/auth/login`).
- Excel export via **openpyxl**. No server-side PDF (the frontend prints/exports client-side).
- **No migration tool** — `Base.metadata.create_all()` runs on startup. Schema
  changes therefore need the tables dropped & recreated (or manual `ALTER`).
  `create_all` only creates missing tables; it never adds/drops columns.

**Frontend** (`React_Frontend-main/frontend/`)
- React + Vite + TypeScript, React Router, **@tanstack/react-query**, react-hook-form + zod, Tailwind.
- Talks to the backend through `lib/api/client.ts`'s `apiFetch` (`credentials: 'include'`).
- Only the **imports** module is wired to the live backend so far; the rest still runs on mock data (`lib/mockData`, `lib/*StatusData.ts`).

---

## Project layout

```
app/
  main.py            FastAPI app: create_all, seed permissions+admin, CORS, include routers
  database.py        engine (json_serializer = json.dumps(..., default=str)), SessionLocal, Base
  models_mixins.py   TimestampMixin (created_at/updated_at, server_default now())
  enums.py           every fixed list as a (str, Enum), stored in String columns
  export_utils.py    xlsx_response(filename, headers, rows) → StreamingResponse
  cross_module.py    trucking ⇆ logistics/imports linkage (open requests + reverse lookup)
  accounts/          User (is_admin) + Permission (many-to-many) + the catalogue
  auth/              cookie login/logout, authenticate(), authorize()
  masters/           6 master lists (config-driven registry) + inline create + review queue
  imports/           consignments: header + item/payment children + history + revert
  logistics/         orders: header + item/package/container children + history + revert
  trucking/          jobs: header + vehicle children + history + revert
  logs/              activity-log middleware + admin live feed (WebSocket)
  dashboard/         imports · logistics · purchases · inventory · whole (overview)
  reports/           cross-module report builder (4 types → one normalised row) + saved templates
  loading/           Excel → DB migration loaders + stores schemas (Stock, Issuance, StoreRequisition, PurchasesData)
React_Frontend-main/frontend/   React SPA
```

Each data-entry module (`imports`, `logistics`, `trucking`) has the same file
shape: `models.py`, `schemas.py` (Pydantic in), `serializers.py` (dict out),
`helpers.py` (queries + create/update/revert logic), `routes/` (one file per
endpoint, all hanging off a shared `router`, listed in `routes/__init__.py`).

---

## App bootstrap (`main.py`)

On startup: import every model module (so `Base.metadata` knows all tables) →
`create_all` → seed the permission catalogue and a default admin (is_admin) if absent → add CORS →
`include_router` for every module (data-entry, masters, auth, logs, and the five
dashboards). **Startup does not load data** — that is the separate
`python -m app.loading.scripts.load_all` CLI (see the loading module).

Route files self-register by importing the shared `router` and decorating it;
`routes/__init__.py` imports every route file so one `include_router` wires the
whole module. **Ordering matters** where a literal path could be captured by a
param path: `GET /export`, `GET /open-requests` etc. are imported **before**
`get_consignment` (`GET /{consignment_id}`), or FastAPI 422s on the int param.

---

## Auth & authorization

**There are no roles.** A user is either an **admin** (`User.is_admin`, which
passes every check including account management) or a normal account holding an
explicit set of **permissions**. Users ⇆ permissions is many-to-many
(`user_permissions`). The permission catalogue is `app/accounts/permissions.py`
(seeded at startup); reference the constants, never raw strings.

- `POST /auth/login` verifies credentials and sets an httpOnly cookie; `POST /auth/logout` clears it. The token carries only the user id.
- `authenticate(request)` reads the cookie and returns the user payload (401 if missing/invalid).
- `authorize(user_payload, permission, db)` — passes if the user **is_admin** OR holds `permission`; 403 otherwise. `permission` is one name **or a list** (any-of; e.g. Submit needs `can_add_*` OR `can_edit_*`). Returns the user.
- `require_admin(user_payload, db)` — admin-only routes: **account management, the activity-log feed, and reopening a closed record**. No permission grants these.
- **Entry-ownership**: `verify_entry_ownership` lets an **admin** touch any
  record but restricts everyone else to records they created — applied to edit,
  submit, delete, undo-delete and revert (view is not ownership-scoped).
- Enforced **server-side** on every route. The frontend hiding something is UX, never the security boundary.

### The permission catalogue

`can_{view,add,edit,delete}_{imports,logistics,trucking}_consignments` ·
`can_view_{overview,imports,logistics,purchases,inventory}_dashboard` ·
`can_{view,add,edit}_master` · `can_make_reports` · `can_use_assistant`.

Mapping: create→`can_add_*`, list/get/export/history→`can_view_*`,
update→`can_edit_*` (+own), delete/undo-delete→`can_delete_*` (+own),
submit→`can_add_*|can_edit_*` (+own), reopen→admin-only. Masters read→
`can_view_master`, inline-create→`can_add_master`, manage→`can_edit_master`.
Reports (data/export/options + saved templates)→`can_make_reports` (saved
edit/delete restricted to the owner or an admin). Viewing needs the matching
`can_view_*` — a data-entry user also needs `can_view_master` for the dropdowns.

Viewers of a record **can** see values, prices and PKR amounts — nothing
financial is gated. The account-creation checkbox on the front end sets
`is_admin`; otherwise the chosen permission names come in as `permissions[]`
(`POST/PUT /users`).

---

## Conventions

- `snake_case` columns, `PascalCase` singular model names.
- Every model carries `created_at` / `updated_at` (via `TimestampMixin`, DB
  `server_default now()`) and a `created_by_id` where a creator applies.
- **Nothing is hard-deleted.** Every table has `is_deleted` (+ `deleted_at`,
  `deleted_by_id`); deleting sets the flag so closed/removed rows stay for reports.
- **Money & weights are `Numeric`, never `Float`.** Foreign amounts / unit
  prices `Numeric(18,4)`; exchange rate `Numeric(12,6)`; PKR amounts
  `Numeric(20,2)`; quantities/weights `Numeric(14,3)`.
- **Enums** live in `enums.py` as `(str, Enum)` and are stored in **String**
  columns (not DB enum types), so adding a value is a one-line change, no
  `ALTER TYPE`. Status values are Title Case and must match the frontend's.
- **Server-side defaults for loader-written flags.** A Python-side `default=`
  never runs on a raw `psycopg2` insert (the loaders), so flags the loaders rely
  on (`record_state`, `is_locked`) use `server_default` too.
- Business logic lives in models/helpers, never in serializers or routes-as-logic.
- Use `selectinload` / `joinedload` on list & detail fetches — N+1 is the only
  realistic performance risk. **Index** every column used in a list filter.
- Branch, commit, push, open a PR. Never commit to `main` directly.

---

# Modules

## accounts

Custom `User` (username, **plaintext** password, `is_admin`) and `Permission`,
joined many-to-many via `user_permissions`. The permission catalogue and a
default admin (`is_admin=True`, no permissions needed) are seeded at startup.
`apply_account_access(db, user, is_admin, names)` sets the flag / assigns the
permission rows on create+edit (an unknown name is a 400). See **Auth &
authorization** for the model.

## masters

The dropdown source-of-truth tables: **Customer, Supplier, Port, ClearingAgent,
Branch, Item** (+ `HsCode` under Item). Free text is banned for anything
reported on — three spellings of one supplier destroys supplier-wise reporting.

**There is no Works master.** Works and Branch are the same thing to the
business: the imports sheet's "Works" column is what fills a consignment's
`branch_id`. The separate `works` list was a duplicate that held zero rows and
that nothing referenced, so it is gone from the registry, the serializers and
the Masters screen. The model and table survive untouched (no DDL is run against
them) and `GET /masters/works` now 404s. The free-text `Consignment.works`
column is a separate vestige — NULL on every loaded row.

- **Config-driven registry** (`registry.py`): one dict per master (model,
  serializer shape, search fields, whether it has HS codes / a port relation),
  so `list`/`get`/`create`/`update` are generic over a `{master}` path param.
- Endpoints: `GET /masters/{master}` (list, `?q`, `include_inactive`,
  `unverified_only`), `GET /masters/{master}/{id}`, `POST /masters/{master}`,
  `PUT /masters/{master}/{id}`, `POST /masters/{master}/inline`,
  `POST /masters/{master}/{id}/verify`, `.../deactivate`, `.../reactivate`,
  `GET /masters/review-queue`, `GET /masters/item-search`.
- **`is_active`** turns a row off without deleting (rows pointing at it keep working).
- **`is_verified`** — a row created mid-data-entry starts `False` and waits in
  the review queue; rows created through the Masters screen are `True`.
- **Inline creation** (Customer, Supplier, Item, Port, ClearingAgent): type a
  name that matches nothing → appended with `verified=False`. Ports also capture
  a Sea/Air type at creation. **Branch is never creatable inline.**
- **Customer** — **name only**, by decision: the logistics workbooks carry
  nothing else about a customer, so address/contact columns would just be empty
  fields on the screen. It is the one master counted against **logistics orders**
  rather than import consignments (`used` = orders shipped to it).
  - `logistics_consignments` carries **both** `customer_name` (free text, what
    the wizard sends and what all 1,424 loaded rows have) **and** `customer_id`.
    `helpers.resolve_customer_id` re-derives the id from the name on create,
    update **and revert**, so the pair cannot drift and the wizard needed no
    change. A name matching no customer leaves `customer_id` NULL rather than
    minting a master row — silently creating a customer from a typo is how a
    master list becomes the free-text mess it exists to prevent.
  - Seeded from the 348 distinct order names by
    `python -m app.loading.scripts.add_customer_master` → **335 customers**
    (13 case-only duplicates merged), **1,424/1,424 orders linked**.
  - **Verification is targeted, not blanket.** A name that is the only spelling
    of its stem lands verified (268); a name sharing a stem with another —
    "CHERAT CEMENT" vs "CHERAT CEMENT LTD." — stays unverified (67, in 29
    groups) because which is the real customer is a business call. Seeding all
    of them unverified would flood the review queue and make the "Unverified"
    badge meaningless; seeding all verified would assert a cleanliness the data
    does not have.
- **Item** carries multiple H.S. codes (one-to-many), a default UoM and default
  specification, and a free-text `category`. These *populate* a consignment line
  when the item is picked, but the line stores its own copy — changing the
  master later never rewrites past records.

## imports (consignments) — `/consignments`

The flagship module. See **Imports data model rules** below for the domain
spec; this is the implementation.

**Tables:** `Consignment` (header) → `ConsignmentItem` (lines), `Payment`
(child), plus history tables `EtaRevisionHistory`, `StatusUpdateHistory`,
`ConsignmentChangeHistory`. Header FKs to masters (`branch_id`, `supplier_id`,
`loading_port_id`, `delivery_port_id`, `clearing_agent_id`); `works` is free
text (typed by hand, not a master).

**Stored derived values** (recomputed on every save — see rule 4):
`Consignment.foreign_total`, `Consignment.pkr_total`, and per-item
`variance_absolute` / `variance_percentage`. `helpers.recompute_derived` runs in
create, update **and revert** (revert too, because these columns aren't in the
change-history JSON).

**System remarks** (rule 6): `serializers.build_system_remarks` generates a
read-only string from the ETA-revision + status history at serialize time
(never stored); the user's own `remarks` is a separate field.

**ELC/ALC audit** (rule 11): each figure records who entered it and when,
separately (`elc_updated_by_id`/`_at`, `alc_updated_by_id`/`_at`);
`stamp_landed_cost_audit` stamps only the figure that actually changed.

**Endpoints:** `POST /`, `GET /` (paged + filtered), `GET /export` (xlsx of the
filtered set), `GET /{id}`, `GET /{id}/trucking-jobs`, `PUT /{id}`,
`POST /{id}/submit`, `POST /{id}/reopen`, `DELETE /{id}`,
`POST /undo-delete/{id}`, `GET /change-history/{id}`,
`GET /change-history/{id}/{hid}`, `PUT /revert-update/{id}/{hid}`.

## logistics — `/logistics`

Export/local orders, restructured to header + children (the frontend redesign
turned it from a flat order into a 5-step wizard: Order, **Packing**, Shipping,
Expenditures, Status).

**Tables:** `LogisticsConsignment` (header: department, order type, origin,
customer, MO/batch, incoterm, shipping, the named expenditure columns +
`container_detention`, status, `gate_out_date`, `sent_to_trucking`) →
`LogisticsItem`, `LogisticsPackage`, `LogisticsContainer` children, plus
`LogisticsStatusHistory` and `LogisticsChangeHistory`.

FE-driven nested collections that are always written whole are stored as **JSON**
rather than their own tables: per-item `rfd_history`, per-package `allocations`
(cross-batch: `{item_id, source_order_id, quantity}`), and the header
`remarks_log` feed. MO/batch numbering and cross-batch resolution are
frontend-driven — the backend stores what it's given.

Endpoints mirror imports (`POST /`, `GET /`, `GET /export`, `GET /filter-options`,
`GET /{id}`, `GET /{id}/trucking-jobs`, `PUT`, `POST /{id}/submit`,
`POST /{id}/reopen`, `DELETE`, undo-delete, change-history, revert).

**Closes/locks at "Delivered" AND submitted** — the same two-part rule as
imports, not status alone. Only `POST /{id}/submit` sets `is_locked`; the update
route never closes an order, so a draft may sit at "Delivered" and stay
editable. `serialize_consignment` returns `missing_fields` (from
`submission_errors`, imported inside the function to dodge the helpers cycle)
so a disabled Submit and a failed submit can't disagree.

`shipment_mode` (**EFS / Regular**, `ShipmentMode`) is an order-level attribute
like department. Nullable and NULL on every loaded row — the workbooks have no
such column — so the UI shows a gap rather than defaulting it to "Regular".

**Frontend (orders) is wired**: `lib/api/logistics.ts` (transport),
`logisticsMap.ts` (`apiToRow` / `apiToDraft` / `draftToPayload` /
`remapNewChildIds`), `logisticsChangeHistoryMap.ts`. List, detail, wizard and
change history all run on the API. Two things to know:

- The list has **no closed stage and no `include_closed`** — a delivered order
  stays visible and reports "Closed" in its own column. The backend list has no
  such param either, so the two agree by construction.
- **Child-row identity.** The wizard identifies items/packages/containers by a
  string id, and a package's `allocations` reference items by it. There is no
  column for that string, so it is DERIVED from the backend id (`item-42`) and
  is stable across reloads. A row added in the browser carries a uuid until the
  first save; `remapNewChildIds` rewrites it — and any allocation pointing at
  it — once the backend assigns real ids.

### Service Jobs — the two halves are not alike

**Customer Rework is WIRED, and has no table of its own.** A rework job is
structurally an order (items, packing, shipping, expenditures, status, Send to
Trucking), so it is a `logistics_consignments` row with **`job_kind='rework'`**
(`JobKind`) as the discriminator — which gives it change history, submit and
the closed lock for free.

- **Not a user-facing field.** There is no form control; it follows from which
  flow was entered ("New Logistics Order" vs "New Rework Job"), is accepted on
  **create only**, and is **immutable** — `helpers.updated_fields` excludes it,
  so a PUT can never move a record between the two tabs. The wizard sends the
  whole draft on every save, so it *is* in the payload; ignoring it is what
  makes it stick. On an existing record the wizard reads the kind from the
  server, never from the route.
- `GET /logistics/` and `/export` take **`job_kind`** — `standard` (**the
  default**, so the Orders list can't accidentally show service jobs),
  `rework`, or `all`.

**Import FOB is a READ-THROUGH, and is also wired.** The consignment's home
stays imports (its item details were entered there); logistics only sees the
ones imports explicitly handed over. `GET /logistics/import-fob-jobs` lists
consignments with `sent_to_logistics_at` set, and the row opens the **source
consignment in imports** rather than anything in logistics. There is no "take"
step, so — unlike trucking's queue — nothing is ever consumed off this list.

## trucking — `/trucking`

One job → many trucks (header + vehicle children), the same header/lines pattern
as imports.

**Tables:** `TruckingConsignment` (movement type, source + `source_ref` +
`taken_at` + `taken_snapshot` (JSON), execution/transport fields, freight +
`detention`, tracking) → `TruckingVehicle` (per-truck fields + `package_refs` /
`import_consignment_refs` as JSON) + `TruckingChangeHistory`. There is **no
stored job-level status** — the tracking status is per-vehicle, and the job
rollup is derived.

Endpoints mirror imports, plus **`GET /open-requests`** (see cross-module) and
**`GET /filter-options`**.

**Closes/locks when every active vehicle is "Delivered" AND the job is
submitted** — the same two-part rule as imports and logistics, not the vehicles
alone. Only `POST /{id}/submit` sets `is_locked`; the update route never closes
a job. `serialize_consignment` returns `missing_fields`, and the history
serializer returns `changed_at` (both imported inside the function to dodge the
helpers cycle).

**Frontend is wired**: `lib/api/trucking.ts`, `truckingMap.ts`,
`truckingChangeHistoryMap.ts` — list, detail, wizard and change history all on
the API. Two things specific to this module:

- **No job-level status anywhere, including the UI.** Tracking is per vehicle;
  the job-level reading is `schema.trackingRollup` over the vehicles, computed
  at render. Nothing stores it, so it cannot drift from what it summarises.
- **Vehicle rows carry an `id`** (`vehicleSchema.id`, derived from the backend
  id as `vehicle-42`). It was added because without it the update diff matched
  nothing and every save read as delete-all + insert-all, losing vehicle ids and
  their change history. A row added in the browser holds a uuid until
  `remapNewVehicleIds` swaps in the real id after the first save.
- The list's two tables are **two different endpoints**: Open Requests
  (`/open-requests` — derived, no trucking id, cannot be opened or edited) and
  Trucking Jobs (`/`). "Take Action" opens the new-job wizard carrying
  `?source=&source_ref=`, which the wizard seeds into the draft — that pair is
  what later drops the request off the queue.

## cross-module linkage (`cross_module.py`)

The three modules are one flow; trucking work originates in the other two.

**Nothing is inferred — every hand-off is an explicit act.** Imports records it
on the consignment itself: **`sent_to_logistics_at`** / **`sent_to_trucking_at`**
(nullable timestamps, NULL = not sent), set only by
`POST /consignments/{id}/send-to-logistics` and `.../send-to-trucking`.
**`incoterm == 'FOB'` decides only whether Send is OFFERED** — the routes 400 on
any other incoterm, and 423 on a closed consignment. Sending is idempotent and
one-way; the front end disables each button once its own timestamp is set.

**The record stays everywhere.** It keeps its row in imports (and appears under
`?sent_only=true`, the "Forwarded" view), shows in logistics' Service Jobs, and
sits in trucking's open requests until a job takes it — after which the JOB is
the link back, which is why a taken request drops off that one queue.

- **`GET /trucking/open-requests`** — the trucking inbox: logistics orders with
  `sent_to_trucking` + import consignments with **`sent_to_trucking_at`**
  (NOT every FOB consignment — that older behaviour filled the queue with work
  nobody had asked for), **minus** the ones a trucking job already took (matched
  by `(source, source_ref)`). Each carries a snapshot the "New Trucking Job"
  form pre-fills from.
- **`GET /logistics/import-fob-jobs`** — the logistics side: consignments with
  `sent_to_logistics_at`. Never consumed; logistics has no "take" step.
- **`GET /consignments/{id}/trucking-jobs`** and
  **`GET /logistics/{id}/trucking-jobs`** — the reverse lookup (which jobs came
  from this consignment/order).

Record-level only; the per-vehicle `package_refs`/`import_consignment_refs` are
stored but not yet resolved.

## logs

An activity-log middleware records who did what; an **admin live feed** streams
new activity over a WebSocket.

## dashboards (`app/dashboard/*`)

Read-only dashboards. Every figure is derived at request time from the source
tables; filter option lists are built dynamically from the whole table;
multi-select filters are repeated query params; and each returns **aggregates +
option lists only — no row lists** (the per-row "view data" table was dropped,
keeping payloads in KBs).

- **imports** `GET /dashboard/imports` — operational consignments.
- **logistics** — **three tab endpoints**, each its own data source + filters:
  `GET /dashboard/logistics/shipments` (`LogisticsConsignment`), `/packing`
  (`LogisticsPackage` + its order), and `/transport` (**`TruckingConsignment`** —
  export trucking; `customer`/`city`/`province` resolved from the linked
  logistics order via `source_ref`). The Documentation tab is **not** built —
  its per-document status data was never loaded.
- **purchases** `GET /dashboard/purchases` and **inventory**
  `GET /dashboard/inventory` — the flat loaded stores tables (`purchases_data`,
  `stock`, `issuance`, `store_requisition`). Purchases derives an order status
  (Pending/Completed/Delayed) + overdue; inventory derives stock status,
  **reorder level** (from store requisitions) and **days-of-stock runway** (from
  issuance).
- **whole** `GET /dashboard/overview` — the cross-module overview, and the one
  dashboard that reads every module at once (imports, purchases, logistics,
  trucking, stores). It **never materializes rows** — every figure is a single
  SQL aggregate, so spanning ~49k issuance rows still answers in well under a
  second. Four sections: **imports** (period value, in-process by stage, shafts),
  **procurement** (period value, category split, delay %, cycle time),
  **logistics** (trucking cost by movement, shipments handled) and **stores**
  (stock value, value by store, days of stock, dead stock).
  - **Params:** `date_from` / `date_to` — **both omitted → month to date**,
    either given → that custom range; the resolved window is echoed back under
    `period` so the front end labels tiles with what was actually computed, not
    what it asked for. Plus `dead_stock_days` (default **180**).
  - **Period vs lifetime is stated per figure**, not inferred from its name:
    imports/procurement figures are windowed, logistics counts and stores are
    running totals or snapshots.
  - **Every ratio ships with its denominator** (`*_basis`), because several rest
    on a small slice of the book and a bare percentage would read as a fact about
    the whole table.
  - **Gaps are surfaced, never swallowed**: `imports.period_value.undated` is the
    money with no ETD (it falls in *no* window); trucking's NULL `movement_type`
    jobs get an **Unclassified** bucket rather than being folded into Inbound or
    Outbound (there is no "Local" type in the data and none can be inferred); and
    `dead_stock.exceeds_history` warns when the threshold reaches back past the
    issuance data, where the figure stops responding to it.
- **The KPI document** (`Supply_Chain_KPI's.docx`) is implemented **across the
  per-module dashboards**, added alongside each screen's original figures rather
  than replacing them: imports gets spend/demands/delay/supplier-Pareto/category
  delays, purchases gets quantity + delay, logistics gets dispatch KPIs, segment
  split, container usage and customer delays (shipments) plus the packing cost
  block, and inventory gets purchase-vs-issuance by category.
  - **Where a figure has no data, it returns `null` with its basis — never 0.**
    Packing has no `actual_packing_cost` at all, so savings stay null; a
    confident Rs 0 would read as "we packed for free".
  - Two figures the data blocks today, each unlocked by data entry and not by
    code: **packing cost/savings** (needs `actual_packing_cost`) and the
    **shipments segment split** (needs `department` on delivered orders — it is
    NULL on exactly the orders that have arrival dates, so `has_segmentation`
    comes back false).
  - **`purchases_data.branch` holds short codes (`QEN`, `QCL`, `QB2`…) while
    `issuance`/`stock` hold full company names.** They share no values, so the
    purchase-vs-issuance chart is deliberately **not** branch-filtered. Mapping
    them belongs in the loader, agreed with the business.
### The reporting window (`app/dashboard/period.py`)

**Every dashboard defaults to the CURRENT MONTH.** Both bounds omitted → the 1st
to today; either given → that custom range. The front end never computes the
default itself — it just omits both dates — so the two cannot disagree about
what "this month" means. `date_from`/`date_to` are the dashboard-wide window;
each screen's own older range filters (`po_from_date`, `from_date`) still exist
and are separate.

**Every period figure ships with `coverage`**, because the sources do not all
run to today: purchases stop **2026-01-23** while issuance runs to this morning.
Defaulting to the current month therefore leaves purchases legitimately empty,
and `is_empty` + `latest_month` let the screen say *"no purchases in August 2026
— latest data is 23 Jan 2026"* with a one-click jump, instead of a confident
Rs 0 that reads as a collapse in spend.

### Figures deliberately removed (they were duplicates or meaningless)

- imports `import_spend` — restated `kpis.total_value_pkr` on a different basis;
  **shafts value** took the tile.
- imports `value_by_supplier` — `supplier_pareto` is the same breakdown plus the
  cumulative line.
- purchases `total_quantity` — summed kg + pcs + litres.
- purchases `avg_days_vs_required` / `delayed_lines` — a second delay average
  beside the first, and a count already on the Delayed tile.
- inventory `available_units` / `total_stock_qty` / `on_hold` — quantity totals
  across incomparable units. Value is the comparable measure.
- inventory `at_risk_pct` / `top_items` — replaced by **movement**
  (fast / slow / dead), which says the same thing with a reason attached.

### Frontend conventions for dashboards

- **Every KPI carries a `help` tooltip** (`components/MetricInfo.tsx`): what the
  figure means, how it is calculated, and — where two figures could be confused
  — how it differs from the other one. Definitions live in `lib/metricHelp.ts`;
  the **basis line comes from the API**, never hardcoded, so a stated
  denominator cannot drift from the data. Opens on hover *and* keyboard focus.
- `components/PeriodFilter.tsx` is the shared timeline control plus
  `PeriodSummary`, which renders the empty-window message described above.
- **All the formulas are in `calculations.md`.**

## reports — `/reports`

The **cross-module report builder**: pick one or more of four data types
(**purchases, imports, inventory, logistics**), filter them, and get one flat
table back — the four sources normalised into a single row shape (shared keys
`ref/item/supplier/branch/category/status/value/date` + type-specific keys; a
key a type has no value for is null, and every row carries its `type`). Unlike
the dashboards this **does** return rows (a report is a table you download), so
it is **paginated**. Reuses the dashboard derivations (purchase status, stock
status + reorder level, logistics cost/kg + stage) — a figure in a report
matches the same figure on its dashboard.

- **`GET /reports/data`** — `types[]` + the shared filters (`item[]`, `shaft[]`,
  `supplier[]`, `branch[]`, `category[]` — **multi-select, repeated params → IN**;
  plus single `date_from`/`date_to`, `search`) + `page`/`page_size`. **`shaft`** is
  a static curated list of item names (`SHAFT_ITEMS`) — those items live in the
  imports item lines, so shaft is its own filter matched on item name across
  purchases, imports (via its lines) and inventory (`item` supports only
  purchases/inventory).
  The result is the selected types **concatenated in a fixed order**
  (purchases→imports→inventory→logistics) and paged as one list; only the rows
  on the page are ever fetched (`plan_slices` maps the global offset/limit to a
  per-type sub-offset/limit, after a cheap `COUNT` per type).
- **Filter ↔ type support** (`FILTER_SUPPORT`): a type that can't honour an
  active filter is **dropped entirely**, mirroring the front end — logistics has
  no branch, so filtering by branch hides logistics; inventory has no date, so a
  date range hides inventory. `search` never drops a type.
- **`GET /reports/export`** — same query, whole filtered set (capped at 20 000),
  `columns[]` picks/orders the sheet columns; `xlsx_response`. **`GET
  /reports/options`** — distinct dropdown values (items/suppliers/branches/
  categories) scoped to the selected types.
- **Saved templates** — `SavedReport` (`types`/`columns`/`filters` as JSON, no
  date range — chosen fresh each run; soft-deleted like everything). The list is
  **shared** (everyone who can reach Reports sees all templates), replacing the
  front end's localStorage. `GET/POST /reports/saved`, `GET/PUT/DELETE
  /reports/saved/{id}`. All of reports is gated by `can_make_reports`; a saved
  template may be edited/deleted only by its creator or an admin.
- **Dropped for want of a backend source** (by decision): imports `customer` /
  `weight` / `shipping line` / `bank` / `documentation status`; inventory
  `last_restocked`; purchases `material`. Imports `ref` falls back to the LC
  instrument number (then `IMP-{id}`); `ppc_store` stays a date.
- The front end (`Reports.tsx`, `reportBuilder.tsx`, `savedReports.ts`) is still
  mock + localStorage — **not yet wired** to these endpoints.

## loading

One-off Excel → DB migration loaders (pandas + raw `psycopg2`, not the ORM):
stores tables, the imports sheet, and the logistics workbook (merged from three
sheets into orders + item/package/container children). Keyed grouping, name→id
resolution, explicit ids + sequence bumping. Because the inserts are raw, any
NOT-NULL column with only a Python-side default must be set explicitly, and
enum-backed columns are **normalised onto the canonical enums** — e.g. the
logistics loader maps the workbook's status vocabulary onto `LogisticsStatus` /
`PackingStatus` and **defaults anything unmapped**, so junk (stray dates, sizes)
never lands in a status column. `stores_schemas.py` defines the flat stores
models (`Stock`, `Issuance`, `StoreRequisition`, `PurchasesData`) the purchases
& inventory dashboards read.

- **`Stock.rank` — the ABC classification, per item PER BRANCH.** `A`/`B` come
  from the `ab_items` workbook's **`Main`** sheet, matched on
  `(Item Code, Branch Name)`; every stock line the sheet doesn't list defaults to
  **`C`** (`ItemRank` in `enums.py`, `server_default 'C'` since the loaders insert
  raw). It lives on `Stock` and **not** on the `Item` master deliberately: the
  ranking is driven by each branch's own stock and issuance, so one item is
  legitimately an A line at one branch and a B line at another — 12 codes in the
  current sheet do exactly that, and `items.item_code` is unique, so the master
  could only ever hold one of the two. The sheet's other ranked tabs
  (`Re-Order`, `Critical`) are filtered views of `Main`, so only `Main` is read.
  An AB entry whose branch has no stock row is simply not applied (66 currently).

- **Each loader reads _every_ workbook in its folder** (`etl_common.list_excel_files`
  + `read_and_concat`), skipping `~$` lock files — dropping another period's file
  into the folder loads it too, no code change. Multiple workbooks in one folder
  must share the same sheet structure.
- **Loading is an explicit CLI, never an import side effect.** Run
  **`python -m app.loading.scripts.load_all`** for a destructive full reload
  (drop → `create_all` → load). It is **not** run on server start: doing so on
  every start (and every `--reload`) silently doubled `purchases_data` (no natural
  key, and the DROP list had `purchases` instead of `purchases_data`, so the
  clear was a no-op). `app.main` only does `create_all` + seed on startup.
- **The imports sheet's missing Item Codes are filled in before grouping**
  (`imports/item_codes.py`). This is not cosmetic: `_group()` drops any row
  without a code, and the current workbook has codes on only **157 of 451** rows
  (the previous one had all 451), so loading it untouched discarded 65% of the
  import lines. Order of preference: the sheet's own code → a code already on
  another row for the same item → the items master matched on **(name, spec)** →
  a generated `IMP-<hash>` code.
  - **Keyed on name + SPEC, never name alone.** In the master, "servo drive"
    carries four codes differing only by spec; every one of the 12 name matches
    was ambiguous. Blank spec means the name alone identifies the item.
  - The generated code is a **hash of the item's identity, not a counter**, so
    the same item gets the same code on every reload — a counter renumbers
    everything the moment an item is inserted earlier in the sheet. Every real
    code matches `<digits>-<digits>`, so the `IMP-` prefix cannot collide.
  - **`backfill_import_demand_dates` applies the same assignment before it
    groups.** It must, or its groups diverge from the loader's and every value
    lands on the wrong consignment. Its id-alignment check exists for exactly
    this and did catch it.
- **`QH` is not a branch** and is not loaded as one; the 2 consignments naming it
  are kept with **no branch** rather than dropped. Branch names are canonicalised
  per `works_id` by the most-used spelling, because the sheet writes both
  "QBL-II" and "QBl-II" under one id and `drop_duplicates` would otherwise store
  whichever row came first.
- **The AB-items workbook changed shape and both layouts are read**
  (`stores/load_05_stock.py`). The old one had a single "Main" sheet with a
  Branch Name column; the new *Combined Planning Sheet* has **one sheet per
  branch**, named with the branch CODE, header on row 5. The old code warned and
  carried on, which would have silently dropped every item to rank C. The
  code→branch map was derived by matching item codes against each branch's stock
  (each sheet covered exactly one branch 100%) — worth doing, because
  **`QEN` is Qadri Engineering while `QE` is Qadbros Engineering**, the opposite
  of the intuitive reading. Ranks outside A/B/C (the sheet has stray `Q` and `D`)
  are ignored, leaving the C default.
- **Transactional sheets may reference items the catalogue lacks**
  (`stores/item_registry.py`). `purchases_data.item_code` and
  `issuance.item_code` are foreign keys onto `items`, and the catalogue export
  lags: the current workbooks reference 30 and 3 unknown codes, which failed the
  constraint and took the whole load down. Those rows carry a name, spec and
  category, so a minimal **unverified** catalogue row is created rather than the
  code being nulled — nulling would cut 0.1% of rows out of every category chart.
- **`python -m app.loading.scripts.reload_changed`** reloads ONLY purchases,
  issuance and imports (+ the masters the imports sheet feeds). Use it instead of
  `load_all` when only those workbooks changed: `load_all` would also rebuild
  logistics and destroy the 1,424 `customer_id` links for nothing. It re-runs the
  demand-dates backfill and the sequence resync afterwards.
- **Explicit ids mean the sequence must be bumped.** The loaders insert ids by
  hand through raw psycopg2, which does **not** advance the table's id sequence;
  the first row the APP then inserts reuses id 1 and dies on the primary key,
  surfacing as a bare "Internal server error". `etl_common.bump_sequence(conn,
  table)` is the fix and every loader calls it. Suppliers, branches and
  clearing_agents did not, which is exactly why "Add Supplier / Branch /
  Clearing Agent" on the Masters screen 500'd while ports and works worked.
  **`python -m app.loading.scripts.resync_sequences`** repairs a database loaded
  before that fix (`--check` to report only); it only ever moves a sequence
  forward, so it is safe to run at any time.
- **`backfill_import_demand_dates` is standalone and must be re-run after any
  imports reload.** It is the only source of `requisition_date`, `required_date`,
  `pkr_total` and `foreign_total` on loaded consignments — the imports loader
  writes none of them. It is *not* part of `load_all`, so a reload silently wipes
  all four and every figure built on them (the overview's import value, the
  reports spend column) reads zero without erroring. Run
  **`python -m app.loading.scripts.backfill_import_demand_dates`** after loading
  imports. The other backfills do not have this problem — terminal flags, stock
  rank and the logistics/trucking close flags were folded into their loaders and
  survive a reload on their own.

---

# Cross-cutting patterns

**Header + children create/update/revert.** create builds the header + child
objects and saves in one flush. update diffs: new lines (no id), field-level
changes on existing lines, and lines missing from the payload (soft-deleted) —
recording each in the change history so it can be undone.

**Change history + field-level revert.** Every update writes one
`*ChangeHistory` row whose `history` JSON holds the pre-change values (header
`fields`, plus per-collection `new_*` / `deleted_*` / updated diffs). Revert
(`can_edit_*` + own-record, latest-first) writes the old values back, re-adds soft-deleted
lines and soft-deletes added ones. The engine's `json_serializer` uses
`default=str`, so Decimals/dates serialize into JSON as strings; `coerce_value`
turns them back on revert.

**Draft vs submitted** (rule 8) and **the closed lock** — see the imports rules.
Present in all three modules; server-controlled columns, opt-in submit.

**List filters** — each `GET /<module>/` applies every filter its list screen
offers, in SQL, on the paged queryset; multi-select as repeated params → `IN`;
masters filter by **id**, enums/statuses by stored value. The contract:

- **Imports** `GET /consignments/`: `status[]`, `stage` (6 pipeline groups →
  statuses), `branch_id[]`, `supplier_id[]`, `requisition_type[]` (via items),
  `missing_only` (= draft), `etd_from`/`etd_to`, `include_closed` (default false
  hides "Arrived at Works"), `include_deleted`, `q`, `page`, `page_size`.
- **Logistics** `GET /logistics/`: `status[]`, `order_type[]`, `customer[]`,
  `gate_out_from`/`gate_out_to`, `include_deleted`, `q`, `page`, `page_size`.
- **Trucking** `GET /trucking/`: `movement_type[]`, `source[]`, `open_only`,
  `pending_only` (= draft), `include_deleted`, `q`, `page`, `page_size`.

`include_deleted` (soft-deleted) ≠ `include_closed` (closed-status). Keep this in
lockstep with the list screens — add a param here in the same change.

**Exports.** Each module has `GET /<module>/export` taking the **same query
params as its list** and running the list query with no page cap, so the export
is exactly the filtered set. Built with `export_utils.xlsx_response` (openpyxl).
Excel only; PDF is the frontend's client-side job.

---

# Imports data model rules (the domain spec)

These are the authoritative business rules for the imports module. They are
implemented as described above; kept here because they encode domain knowledge,
not code.

**1. Consignment (header) → ConsignmentItem (lines).** One consignment carries
many items. Flattening this breaks finance and clearance. Header holds branch,
supplier, origin, currency, consignment type, PO/requisition/required dates,
incoterm, payment instrument+number+date, works, exchange rate + date + source,
status, remarks, clearing agent, GD number, gate out, free days, demurrage,
container detention. Line holds requisition type + reference/job/MO, item + code
+ specification, quantity, UoM, batch no, H.S. code, foreign unit price, ELC/ALC.

**2. Requisition details belong to the ITEM.** Reference/Job/MO are properties of
the demand, so requisition type sits on the line — one consignment can carry
Store + Engineering items together (show the distinct set in list/reports). The
conditional fields are one rules dict (`REQUISITION_REQUIRED`): Store→reference;
Engineering→reference+job+MO; Others→description. Adding a type is a one-line change.

**3. Money is Decimal.** See Conventions.

**4. Calculated values are computed, never keyed in** — and the money totals are
**stored** (recomputed on save) so a later rate change or edit can't restate a
printed report: line total = qty × unit price; consignment `foreign_total` = Σ
line totals; `pkr_total` = foreign_total × booked exchange rate; per-item
variance = ALC − ELC (absolute + %). Transit time (ETA−ETD) and clearance time
(gate-out − actual arrival) are shown but not stored. **Never** convert a stored
foreign value at a live rate.

**5. History tables, never text fields.** `EtaRevisionHistory` and
`StatusUpdateHistory` drive the "1st ETA…2nd ETA…" line and stage-ageing;
slippage = current ETA − first ETA ever promised.

**6. Remarks are two fields.** `system_remarks` (generated from ETA+status
history, read-only) and user `remarks` (free text) — displayed together, never
one input.

**7. Payments are a child table.** Partial payments are normal; instrument
drives the number/date labels (LC→LC number/Retirement; Adv/DP/CAD→reference/Opening).

**8. Draft vs submitted + the closed lock.** State is `record_state`
(`'draft'`/`'submitted'`, `server_default 'draft'`), server-controlled. Save
draft = the permissive create/`PUT`. **Submit** = `POST /{id}/submit`, runs the
full rule set (`submission_errors`, mirroring the frontend) and flips to
`'submitted'` only if complete, else `422` with the gaps. Rules are application
checks, never DB constraints (drafts + submitted share one table). Submit rule
set: branch_id, supplier_id, origin, currency present; ≥1 item; each item has
name, code, quantity, UoM, requisition_type + its conditional fields; payment
instrument+number, works, exchange rate, rate date, status present; eta ≥ etd.

The **closed lock** is separate: a consignment closes when its status reaches
"Arrived at Works"; `is_locked` (`server_default false`) is set on that update
and afterwards **no role** may edit — update/submit return `423`. Only an
**admin** reopens via `POST /{id}/reopen`. Submitting never locks; only closing
does. Loaded rows import unlocked. Logistics closes at "Delivered", trucking when
all vehicles are delivered.

**9. Status list (ordered — do not reorder).** TT/LC in Process, Under
Production, Ready Awaiting Sailing, In Transit, Arrived at Port, Under Custom
Clearance, Under Examination, Under Assessment, Arrived at QFL, On Road, Arrived
at Works. The list groups these into six stages (Pre-shipment, Production, In
transit, Clearance, Inbound, Closed). "Arrived at Works" is closed and hidden
from the list by default. **Enum values are Title Case and must match the frontend.**

**10. Free text is banned for anything reported on** — masters instead (except
`works`, which is deliberately free text on the consignment).

**11. ELC and ALC are manual, per-item, never calculated.** Goods value, bank
charges and demurrage are reference figures only, never summed into them. Record
who entered each figure and when, **separately** (they're entered weeks apart).

**12. Item master carries defaults; the line stores its own copy.** Changing the
master later never rewrites past consignments.

**13. Inline creation** — Supplier/Item/Port/ClearingAgent only, `verified=False`
→ review queue. Branch/Works never inline.

---

# Frontend integration (imports, wired)

The imports module is wired end-to-end (the pattern to follow for the others):

- `lib/api/imports.ts` — one typed function per endpoint, unwrapping
  `{status_code, detail, data, pagination?}`.
- `lib/api/masters.ts` — fetches master lists and builds name→id maps (the
  wizard picks masters by name; the backend wants ids).
- `lib/api/importsMap.ts` — `apiToRow` / `apiToDraft` / `draftToPayload`, bridging
  camelCase↔snake_case, names↔ids, and gating enum values against the backend
  sets so an unmapped value is omitted, not 422'd.
- `lib/api/useImports.ts` — React Query hooks; mutations invalidate the list + record.
- List/detail/wizard are wired; the wizard creates on first save then `PUT`s,
  and the final Submit calls `/submit`.

Visual language (unchanged): dense, flat, navy `#0F1B2D` + brass `#B8873B`
accent, 4px radius, tabular numerals. Colour = meaning — green complete/on-time,
amber pending/approaching, red late/overdue.

---

# Working agreement

Backend by an intern, frontend by the project owner. Neither invents a field
name, URL name or status value alone — write it here first, then implement, and
add it in the same change if it's missing.

## When to stop and ask

Business rules around imports, LCs, customs, duty, stock and purchasing are
domain knowledge, not something to infer. If a rule is unclear or a requested
change contradicts something above, raise it rather than resolving it silently.
