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
  main.py            FastAPI app: create_all, seed roles+admin, CORS, include routers
  database.py        engine (json_serializer = json.dumps(..., default=str)), SessionLocal, Base
  models_mixins.py   TimestampMixin (created_at/updated_at, server_default now())
  enums.py           every fixed list as a (str, Enum), stored in String columns
  export_utils.py    xlsx_response(filename, headers, rows) → StreamingResponse
  cross_module.py    trucking ⇆ logistics/imports linkage (open requests + reverse lookup)
  accounts/          User, Role
  auth/              cookie login/logout, authenticate(), authorize()
  masters/           6 master lists (config-driven registry) + inline create + review queue
  imports/           consignments: header + item/payment children + history + revert
  logistics/         orders: header + item/package/container children + history + revert
  trucking/          jobs: header + vehicle children + history + revert
  logs/              activity-log middleware + admin live feed (WebSocket)
  dashboard/         imports · logistics · purchases · inventory · whole (overview)
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
`create_all` → seed the four roles and a default admin if absent → add CORS →
`include_router` for every module (data-entry, masters, auth, logs, and the five
dashboards).

Route files self-register by importing the shared `router` and decorating it;
`routes/__init__.py` imports every route file so one `include_router` wires the
whole module. **Ordering matters** where a literal path could be captured by a
param path: `GET /export`, `GET /open-requests` etc. are imported **before**
`get_consignment` (`GET /{consignment_id}`), or FastAPI 422s on the int param.

---

## Auth & authorization

- `POST /auth/login` verifies credentials and sets an httpOnly cookie; `POST /auth/logout` clears it.
- `authenticate(request)` reads the cookie and returns the user payload (401 if missing/invalid).
- `authorize(user_payload, [roles], db)` loads the user, checks their role name is in the allowed set (403 otherwise), and returns the user.
- **Entry-ownership**: `verify_entry_ownership` lets admin/manager touch any
  record but restricts an entry operator to records they created.
- Permissions are enforced **server-side** on every route. The frontend hiding
  something is UX, never the security boundary.

### Roles

| Role | Enter | Edit existing | Dashboards/Reports | Manage users |
|---|---|---|---|---|
| Admin | yes | yes | yes | yes |
| Manager | yes | yes | yes | no |
| Entry Operator | yes | own records only | yes | no |
| Viewer | no | no | read-only | no |

Viewers **can** see values, prices and PKR amounts — nothing financial is hidden
by role. Dashboards are read-only and open to all four roles. Masters are
managed by Manager/Admin.

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

Custom `User` (username, password hash, `role_id`) and `Role`. Roles + a default
admin are seeded at startup.

## masters

The dropdown source-of-truth tables: **Supplier, Branch, Works, Port,
ClearingAgent, Item** (+ `HsCode` under Item). Free text is banned for anything
reported on — three spellings of one supplier destroys supplier-wise reporting.

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
- **Inline creation** (Supplier, Item, Port, ClearingAgent only): type a name
  that matches nothing → appended with `verified=False`. Ports also capture a
  Sea/Air type at creation. **Branch and Works are never creatable inline.**
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

Endpoints mirror imports (`POST /`, `GET /`, `GET /export`, `GET /{id}`,
`GET /{id}/trucking-jobs`, `PUT`, `POST /{id}/submit`, `POST /{id}/reopen`,
`DELETE`, undo-delete, change-history, revert). Closes/locks at **"Delivered"**.

## trucking — `/trucking`

One job → many trucks (header + vehicle children), the same header/lines pattern
as imports.

**Tables:** `TruckingConsignment` (movement type, source + `source_ref` +
`taken_at` + `taken_snapshot` (JSON), execution/transport fields, freight +
`detention`, tracking) → `TruckingVehicle` (per-truck fields + `package_refs` /
`import_consignment_refs` as JSON) + `TruckingChangeHistory`. There is **no
stored job-level status** — the tracking status is per-vehicle, and the job
rollup is derived.

Endpoints mirror imports, plus **`GET /open-requests`** (see cross-module).
Closes/locks when **every vehicle is "Delivered"** (`helpers.is_closed`).

## cross-module linkage (`cross_module.py`)

The three modules are one flow; trucking work originates in the other two.

- **`GET /trucking/open-requests`** — the trucking inbox: logistics orders with
  `sent_to_trucking` + import consignments bought FOB, **minus** the ones a
  trucking job already took (matched by `(source, source_ref)`). Each carries a
  snapshot the "New Trucking Job" form pre-fills from.
- **`GET /consignments/{id}/trucking-jobs`** and
  **`GET /logistics/{id}/trucking-jobs`** — the reverse lookup (which jobs came
  from this consignment/order).

Record-level only; the per-vehicle `package_refs`/`import_consignment_refs` are
stored but not yet resolved.

## logs

An activity-log middleware records who did what; an **admin live feed** streams
new activity over a WebSocket.

## dashboards (`app/dashboard/*`)

Five read-only dashboards — **imports, logistics, purchases, inventory, whole
(overview)** — each at `GET /dashboard/<name>`. All figures are derived at
request time from the source tables; filter option lists are built dynamically
from the whole table; multi-select filters are repeated query params.

- imports/logistics read the operational tables; **purchases** and **inventory**
  read the flat loaded stores tables (`purchases_data`, `stock`, `issuance`,
  `store_requisition`) and return **aggregates + option lists only** (the
  per-row "view data" table was dropped, so no row list is shipped — keeps the
  payload in KBs).
- Purchases derives an order **status** (Pending/Completed/Delayed) and overdue;
  inventory derives **stock status**, **reorder level** (from store
  requisitions), and **days-of-stock runway** (from issuance).
- **All the formulas are in `calculations.md`.**

## loading

One-off Excel → DB migration loaders (pandas + raw `psycopg2`, not the ORM):
stores tables and the imports sheet. Keyed grouping, name→id resolution, explicit
ids + sequence bumping. `stores_schemas.py` defines the flat stores models
(`Stock`, `Issuance`, `StoreRequisition`, `PurchasesData`) that the purchases &
inventory dashboards read.

---

# Cross-cutting patterns

**Header + children create/update/revert.** create builds the header + child
objects and saves in one flush. update diffs: new lines (no id), field-level
changes on existing lines, and lines missing from the payload (soft-deleted) —
recording each in the change history so it can be undone.

**Change history + field-level revert.** Every update writes one
`*ChangeHistory` row whose `history` JSON holds the pre-change values (header
`fields`, plus per-collection `new_*` / `deleted_*` / updated diffs). Revert
(admin/manager, latest-first) writes the old values back, re-adds soft-deleted
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
