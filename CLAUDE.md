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

- **imports** `GET /dashboard/imports` — **every consignment in the window, at
  every status.** It used to hide "Arrived at Works" as an operational view,
  which is why it reported Rs 210m where the overview reported Rs 262m over the
  same window: the Rs 52.7m gap was four arrived consignments and nothing else.
  `population` now splits the set into **In Process / Arrived / Cancelled**, each
  carrying **count AND value**, so "what is still moving" is a tile rather than a
  hidden filter. Takes `date_field` (`eta_works` | `required_date`), `search`
  (payment ref, GD, origin, supplier, item) and `shafts_only`.
- **logistics** — **three tab endpoints**, each its own data source + filters:
  `GET /dashboard/logistics/shipments` (`LogisticsConsignment`), `/packing`
  (`LogisticsPackage` + its order), and `/transport` (**`TruckingConsignment`** —
  export trucking; `customer`/`city`/`province` resolved from the linked
  logistics order via `source_ref`). The Documentation tab is **not** built —
  its per-document status data was never loaded.
- **purchases** `GET /dashboard/purchases` and **inventory**
  `GET /dashboard/inventory` — the flat loaded stores tables (`purchases_data`,
  `stock`, `issuance`, `store_requisition`). Purchases derives an order status
  (Pending/On Time/Delayed) + overdue; inventory derives stock status,
  **reorder level** (from store requisitions) and **days-of-stock runway** (from
  issuance). Inventory takes `date_from`/`date_to` for its **issuance** figure
  only — stock itself is a snapshot with no date at all.
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
    what it asked for. Plus `dead_stock_days` (default **365** — shared with
    the Inventory dashboard's own fixed dead-stock window, see
    `app.dashboard.period.DEAD_STOCK_WINDOW_DAYS` and "One dead-stock
    definition too" below; the param itself stays adjustable).
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
    purchase-vs-issuance chart is deliberately **not** branch-filtered.
    A confirmed mapping for four of the seven codes now exists
    (`app.dashboard.inventory.helpers.PURCHASES_BRANCH_TO_STOCK_BRANCH`), given
    by the business rather than derived — see "One dead-stock definition too"
    below — but it is used only where dead stock needs it. This chart's own
    company-wide, unfiltered design is unchanged: filtering it would silently
    drop the three unmapped codes' spend rather than show it honestly.
### Imports money is counted in the month it ARRIVED

A consignment groups every sheet row sharing a payment reference, and **those
rows do not all arrive together** — 19 of 175 consignments carry lines with
different ETAs, one spanning seven dates, and 46 individual lines have an ETA
that is not their header's. The loader kept only the first line's ETA, so a
whole consignment was credited to one month: ref 65704 reported Rs 10.64m in
August when Rs 8.98m arrived on 6 August and Rs 1.25m had landed on 27 July.

So `consignment_items` now carries its **own `eta_works`** (loaded per row;
`python -m app.loading.scripts.backfill_line_eta_works` repairs an existing
database), and:

- **Value is summed over LINES**, each dated by its own ETA — falling back to
  its consignment's where the sheet gave the line none (9 of 450).
- **Window membership is by line**: a consignment belongs to a window if ANY of
  its lines arrives in it, so one straddling two months contributes to both.
- **Counts stay in consignments.** The tile says 1 consignment, the list says
  3 lines, and the panel states both.
- The **stored `pkr_total`** is still preferred for un-windowed consignment-level
  figures (`CONSIGNMENT_VALUE`); it cannot be used for a partial window because
  there is no stored per-line PKR to split it with. The two agree to within
  sheet rounding (0.05%) wherever a consignment sits wholly inside one window.
- **One money basis per screen.** The imports population tiles sum the same
  in-window lines the headline does; they used to sum consignment-level totals,
  putting Rs 29.27bn beside Rs 29.07bn on one page.

**The Overview's `imports.period_value` no longer follows this rule, by
instruction.** It used to (line-summed, same as this module), but the Imports
module screen's own "Total Value" hero and trend chart were ALWAYS
header-dated (`app.dashboard.imports.calculations.kpis` / `value_trend`,
never migrated to the line basis above), so the two screens' headline import
value disagreed. Rather than move the module's hero onto the line basis, the
Overview's `period_value` (`app/dashboard/whole/helpers.py`) was moved onto
the module's header basis instead — full `CONSIGNMENT_VALUE` per consignment,
dated by the consignment's own header field. The line-based helpers this
replaced there (`LINE_ETA`, `line_date_column`, `_line_select`) are deleted
from that file; this module's OWN `period_value` tile (line-based, per the
rule above) is unaffected — it was removed from the Imports screen entirely
instead, since showing it beside the header-based hero was what surfaced the
disagreement in the first place. Two different bases for "imports value" now
exist across the app on purpose: the Overview's headline (header) and this
module's `population`/`in_process`/`arrived` split (line, unchanged).

**Valuation basis and window MEMBERSHIP are two separate questions, and only
the first one moved.** Switching `period_value` onto header valuation also
briefly filtered its window on the header column alone — which changed which
consignments qualify, not just what they're worth. A consignment with no
header `eta_works` but a dated line dropped out of every Overview figure
(`period_value`, `population`, `in_process_by_stage`, `delay`, and their
`references` drill-downs) while the module still counted it: 10 consignments
on the module screen against 9 on the Overview for the same month, the
"arrived" bucket splitting 5-vs-4. Membership is now `_imports_window_membership`
in `app/dashboard/whole/helpers.py` — the same "any LINE dated inside the
window, falling back to the header where a line has none" test
`app.dashboard.imports.helpers.fetch_filtered_consigments` applies — so both
screens count the same consignments; only the per-consignment VALUE (and, by
construction, the arrived/in-process split of it) still differs by the header
-vs-line basis described above.

### A ZERO needs a reason beside it

The logistics Shipments tab and the Overview both split orders into export and
local, **windowed like every other figure**. Local reads **zero in every period
there has ever been** — and that is a fact about the DATA, not the business:
across port-in, ETD, CRO arrival, actual arrival, effective and gate-out, **not
one** of the 7 local orders (or the 392 that state no type) carries a date. Only
exports are dated.

**Local Orders is therefore an ALL-TIME tile, and its label says so** —
"Local Orders (all time)", beside a windowed Export Orders. Two bases in one
row is normally the thing to avoid; here the alternative is a tile that reads
zero for ever, so the bases are shown VISIBLY rather than reconciled silently.
The remaining undated orders stay in the payload (`order_types.undated`) and
explain the zero in the Orders tooltip, without a tile of their own.

The Local/Export FILTER was removed for the same reason. Filtering a windowed
screen by a type only one value of which is ever dated would have appeared to
work while always returning nothing for local.

The tab is named **Export Shipments** on the same evidence: since only exports
are dated, every windowed view of it contains exports and nothing else, so the
name describes what is actually on screen rather than what the table could in
principle hold.

### A DEFAULT is part of the metric

Two screens can share a formula, share a window, agree on every figure you check
by hand — and still disagree the moment somebody just opens them. Procurement
did: the Overview defaulted to **`po_date`** while the Purchases dashboard
defaulted to **`purchase`**, so one month read Rs 7.33bn over 5,036 orders on
one screen and Rs 7.40bn over 5,187 on the other. Forced onto the same date
field they matched to the rupee; nothing was wrong with either calculation.

Both dates are real and the caller still picks between them. What cannot be two
values is the DEFAULT, so it lives in `app/dashboard/period.PURCHASES_DATE_DEFAULT`
and both screens import it. It is **`purchase`**: "procurement value this month"
normally means money spent rather than money committed, and every other Overview
section dates on when something HAPPENED (goods landing, stock issuing) rather
than when it was promised.

The consistency suite now asserts the shared default, not only that the two
agree once you force them onto the same field.

**A related bug, on the same `po_date`/`purchase` choice, but WITHIN one
screen**: the Purchases dashboard's own trend chart could show fewer orders
than its `Orders` KPI, on the SAME page at the SAME `date_field`. The window
filter (`fetch_filtered_consignments`) already respects `date_field` — a
purchase LINE only qualifies if ITS OWN value of that field falls in the
window. But `value_trend` (`app/dashboard/purchases/calculations.py`) dated
each order by `line.purchase`, hardcoded, regardless of which field actually
let that order's lines through. Under `date_field='po_date'` an order's real
`purchase` date can sit outside the window even though its `po_date`
correctly put it inside — `build_trend` silently dropped that order from the
chart while `kpis.orders_count` kept counting it. `value_trend` now takes
`date_field` and dates on whichever field the filter used, falling back to
the other only when the primary is missing on a line.

### One metric, one definition (`app/dashboard/stock_runway.py`)

**A figure that appears on two screens is computed in ONE place.** The rule
exists because it was broken: Inventory divided stock value by twelve months'
issuance while the overview's Stores section divided it by ninety days' — and
printed the answer under a tile captioned "at the last 12 months' usage". The
same warehouse had 81 days of runway on one screen and 54 on the other, and
neither number was wrong for its own formula, which is what makes that class of
bug expensive: both screens looked right.

`stock_runway` is now the only definition of days of stock:

    days of stock = stock value / (value issued in the window / days)

- **Value, not quantity** — a store holds bolts and shafts; summing units is
  meaningless, summing rupees is not.
- **Twelve months**, which is what the tiles always claimed.
- The window ends at the **latest issuance in the data**, not today: the table is
  historical, and anchoring to today measures an empty window and reports
  infinite runway everywhere.
- **Issuance is matched to the stock it depletes**, on `(item_code, branch)`.
  Counting every issuance instead put Rs 1.75bn of consumption against items with
  no stock row at all — consumption that cannot deplete anything on hand. That
  single population difference was the whole 81-against-58 gap once the formulas
  were unified.
- No consumption in the window → **`None`**, never 0 and never "infinite".

### One dead-stock definition too (`app/dashboard/inventory/calculations.py::derive_movement`)

The same class of bug as stock runway, in the same two screens. The Inventory
dashboard's Dead bucket and the Overview's `stores.dead_stock` were computed
independently and disagreed — a different window length (Inventory's fixed
12 months vs. Overview's `dead_stock_days`, defaulting to 180), a different
gate (`stock_qty_amount > 0` vs `available_qty > 0`), and no purchase-recency
check on either. Overview's own tile and its drill-down reference list even
disagreed with **each other** — a bug found only while unifying the other one.

Dead now means, identically on both screens: no issuance in the trailing
**12 months** (shared default, `app.dashboard.period.DEAD_STOCK_WINDOW_DAYS`
— Overview's `dead_stock_days` param stays adjustable, only the DEFAULT had
to stop disagreeing), `available_qty > 0` (not `stock_qty` — nothing
available is nothing sitting idle, whether depleted or fully on hold),
**and** not purchased in that same trailing 12 months either — an item
bought last week has not had the chance to be issued yet, which is not the
same thing as stock nobody wants.

Two real bugs surfaced while unifying this, not just a definitional gap:

- **Issuance at a branch with no remaining stock row was invisible to the
  fold.** The Inventory dashboard folds stock onto item_code across every
  branch that holds it (an item still moving at one factory is not dead
  because it sat still at another), but the fold only ever summed a stock
  ROW's own attached issuance — 903 item codes had genuine issuance in the
  window at a branch with no stock row left, silently understating the
  item's issuance and sometimes calling it dead despite having moved. Fixed
  with `issuance_totals_by_item`, grouped by item_code alone rather than
  derived from the stock rows.
- **The purchase check had the identical bug in miniature.** Scoped first to
  only the branches the item's CURRENT stock snapshot lists, it undercounted
  for the same reason — a purchase can land before the next snapshot
  reflects it there. Checked against every branch purchases_data can be
  matched to at all, not just the ones this particular snapshot happens to
  show stock at.

**Purchases ARE matched by branch**, via a mapping confirmed by the business,
not derived: `QCL`→Qadcast, `QE`→Qadbros Engineering, `QEN`→Qadri Engineering,
`QB2`→Qadri Brothers (Unit-II). Cross-matching item codes the way the
AB-items branch map is (`load_05_stock.py`) does not work here — that
technique found ~100% agreement because AB items and stock are the same kind
of snapshot; purchases accumulate for years across items no longer in a
stock snapshot, a different population, and the best match found that way
was 41.7%. `QBL`, `QE-II` and `IOL` stay unmapped on purpose: `QBL` may be a
different Qadri Brothers site than the Unit-II we hold stock data for,
`QE-II` has no confirmed match, and `IOL` is not a branch at all. **A
purchase row under an unmapped code is filtered out of every cross-sheet
calculation against it, always** — a general rule for future work here, not
only for dead stock. The purchase-vs-issuance-by-category KPI chart is a
different calculation and stays deliberately branch-unfiltered by its own
design (see above) — the two should not be conflated.

### The records behind a figure (`app/dashboard/references.py`)

Every KPI can be opened to see the records it counted. Three rules:

- **The list is COMPLETE.** `total` is always the true count and every record is
  reachable by paging. A cap silently changes the question from "which records is
  this about" to "which did we feel like showing", and the reader cannot tell.
- **A list NEVER HIDES LINES.** Where a record has lines under it, the rows ARE
  the lines: a consignment carrying three shaft rows shows as three rows, each
  with its own arrival date and value. Folding them up looks tidy and destroys
  the only view that explains the number — it is what let payment ref 65704 show
  one row for seven lines arriving in two different months.
- **Both units are published, never one silently.** A line list carries `unit`,
  `groups` and `group_unit`, so the panel reads *"3 lines across 1 consignment"*
  and the tile's own count stays reconcilable. What is banned is a list that
  quietly reports a different number with nothing saying why — the Delayed tile
  reading 247 over a list reading 454.

Complete does not mean shipped at once: procurement alone stands over 8,731
orders (1.3 MB) on a screen that reloads whenever a filter moves. So the payload
carries the true total plus **page one**, and
**`GET /dashboard/{overview,imports,purchases,inventory}/references`** serves the
rest — same filters as the dashboard, plus `key`, `page`, `page_size`
(default 50, max 500). `key` is matched against a **fixed registry**; an unknown
key is a 400, never a way to reach a query the screen was not meant to run.

### The reporting window (`app/dashboard/period.py`)

**Every dashboard defaults to the CURRENT MONTH.** Both bounds omitted → the 1st
to today; either given → that custom range. The front end never computes the
default itself — it just omits both dates — so the two cannot disagree about
what "this month" means. `date_from`/`date_to` are the dashboard-wide window;
each screen's own older range filters (`po_from_date`, `from_date`) still exist
and are separate.

**Every time-based section ships `coverage`** — the four overview sections
included. Without it the shared period control's "All data" preset fell back to a
hardcoded `2000-01-01`, putting a date in the From box for a year the data has
never held, and there was nothing to drive the "jump to the latest month with
data" control the spec requires on every screen.

**Every period figure ships with `coverage`**, because the sources do not all
run to today: purchases stop **2026-01-23** while issuance runs to this morning.
Defaulting to the current month therefore leaves purchases legitimately empty,
and `is_empty` + `latest_month` let the screen say *"no purchases in August 2026
— latest data is 23 Jan 2026"* with a one-click jump, instead of a confident
Rs 0 that reads as a collapse in spend.

### Figures deliberately removed (they were duplicates or meaningless)

- overview `Stores holding stock` — a count of branches, which changes about once
  a year. Replaced by **issuance in the period** (value + items by item code).
- inventory `Issued (12m)` / `Issued (3m)` — one question at two arbitrary
  window lengths, neither chosen by anyone, and neither able to say what went out
  *this month*. Replaced by **one issuance tile with its own date filter**. The
  12-month figures still drive the movement split and the runway; they are just
  no longer tiles.
- inventory `Dead Stock` / `Items in Stock` — dead stock is a block in the
  movement card with its own drill-down, and the item count is on Stock Value.
- overview `Categories` — it counted the bars in the chart directly below it.

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
- **Related KPIs share one format.** Anything that is a SET of records reports
  **count and value in the same shape** (`{count, value, value_pct}`), so a row of
  tiles can be read across. In Process used to show a bare count beside a value —
  it said 30 consignments were moving without saying whether that was Rs 4m or
  Rs 400m.
- **Percentages are compared with percentages.** On-Time and Delayed both report
  a share of the same denominator (orders actually purchased) and sum to 100; the
  counts live in the sub-line and the drill-down.
- **The Shafts tab is a filter, not two tiles.** As tiles, "9 shafts in process"
  sat beside a 30 that counted everything and the two could not be compared. As a
  tab it narrows every figure, chart and reference list at once. The
  category-delay chart is withheld while it is active — with the set restricted
  to shafts, "delay by item category" is one bar pretending to be a comparison.
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
- **A workbook can SPILL onto a second sheet, and the loader must follow it.**
  The purchases export is an old-format `.xls`, capped at 65,536 rows per sheet:
  Sheet1 fills to 65,520 and the rest continues on **Sheet2 with no header of
  its own** (its first data row, Record No 65521, was being read AS the header).
  Reading only Sheet1 lost **13,411 purchase lines** — and Sheet1 stops at
  **2026-01-23** while Sheet2 runs to **2026-08-07**, so the purchases dashboard
  reporting "no data this month, latest is 23 Jan" was never a data-entry gap;
  it was seven months of purchases on a sheet nothing read.
  `read_purchases_frames` now loads every sheet, treating one whose header does
  not look like the first sheet's as a headerless continuation.
- **In-house companies are not suppliers.** `Qadbros Engineering Pvt Ltd` is a
  Qadri company, so a purchase booked against it is the group buying from
  itself. Its supplier is **NULLED AT LOAD** (7,238 of 78,931 rows) rather than
  filtered on the dashboards: the column should not claim a vendor that was
  never one, and a value nulled here cannot be missed by a screen that forgets
  to exclude it. The purchase itself is kept — the money is real, only the
  vendor attribution is not. `Import (IOL)` is the same idea one layer up, in
  `purchases.calculations.NON_SUPPLIERS`.
- **A loader keyed on column NAMES fails silently when a workbook is
  re-shaped.** The purchases export split its old `PPC/Store` column into two
  (`PPC`, a date; `Store`, a timestamp of the same event). The loader kept asking
  for the old name, `clean_date` was handed a missing key, and `ppc_store` went
  NULL on all 65,520 rows — taking the overview's "store demand to purchase"
  cycle time to a basis of zero and a blank tile. Nothing errored.
  `load_02_purchases_data` now reads whichever of the three names is present, and
  **`python -m app.loading.scripts.backfill_purchase_store_dates`** repairs a
  database already loaded (it verifies the sheet's row order against the stored
  PO + purchase date before writing, and aborts below 95% agreement).
- **Every reload ENDS BY CHECKING ITSELF** (`app/loading/scripts/post_load.py`,
  run automatically by both `load_all` and `reload_changed`). It reports on every
  column that has silently arrived empty before — purchase store-demand dates,
  import demand dates + PKR totals, stock ABC ranks, purchase/issuance item codes
  — and **repairs the ones that have a repair**, naming the rest. Repairs are
  CONDITIONAL, not unconditional: the loaders write these columns correctly now,
  so re-running a backfill on every load would re-read a 65,000-row workbook to
  write values already there. It runs only when the check finds the column empty
  — which is exactly when a workbook has been re-shaped again. Nothing to
  remember, and no cost when nothing is wrong.
- **`backfill_import_demand_dates` runs automatically** from both `load_all` and
  `reload_changed`, and the post-load check catches it if it did not. It is the
  only source of `requisition_date`, `required_date`, `pkr_total` and
  `foreign_total` on loaded consignments — the imports loader writes none of
  them — so when it was standalone, a reload silently wiped all four and every
  figure built on them (the overview's import value, the reports spend column)
  read zero without erroring. It can still be run on its own:
  **`python -m app.loading.scripts.backfill_import_demand_dates`**. The other
  backfills never had this problem — terminal flags, stock rank and the
  logistics/trucking close flags were folded into their loaders and survive a
  reload on their own.

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
