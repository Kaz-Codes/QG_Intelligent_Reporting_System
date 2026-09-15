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
- `Base.metadata.create_all()` runs on startup **only on a database Alembic
  does not manage**, and even then only creates missing tables — it never
  adds/drops/alters a column on a table that already exists. **Alembic**
  (`alembic/`) is the source of truth for schema changes now — see
  **Database migrations** below.

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

## Database migrations

`create_all()` only ever creates a table that doesn't exist yet — it silently
does nothing for a new column, a changed type, or a dropped column on a table
that's already there. **Alembic** closes that gap and is the source of truth for
schema changes going forward; `create_all()` stays only so a brand-new empty
database still boots.

### `create_all()` is GATED, and the gate is `alembic_version`

**`main.py::create_tables` skips `create_all` entirely when the database carries
an Alembic revision** (`main.py::schema_is_alembic_managed`). It used to run on
every start against every database, and on an Alembic-managed one that is not a
harmless no-op — it is a schema change made behind the migration's back, once
per service start.

**The failure it prevents, which was measured rather than imagined.** Start the
service *before* running a migration that adds a table, and `create_all` creates
that table **empty**: no back-fill, no ALTER of the existing tables the migration
also needed, and no row in `alembic_version`. `alembic upgrade head` then dies
with `DuplicateTable: relation "..." already exists`, and the database sits
half-changed. Recovery is dropping the empty tables by hand and migrating again.

- **A revision in `alembic_version` is the gate**, not a guess from whether some
  sentinel table happens to exist. The table with no row in it does not count:
  that is a database Alembic has touched but never applied anything to.
- **A brand-new empty database still boots** — it has no `alembic_version`, so
  `create_all` builds the schema and the admin seed runs, exactly as before.
- **A fresh database stays ungated until it is stamped.** `alembic stamp head`
  on it (see below) is the same manual step it always was; from then on the gate
  holds and `create_all` never runs against that database again.
- The check sits **inside** the startup retry loop, so a Postgres that is still
  waking up backs off and retries exactly as `create_all` used to.

- `alembic/env.py` imports `Base` from `app.database` plus every model module
  (`accounts`, `masters`, `imports`, `logistics`, `trucking`, `logs`,
  `reports`, `loading.schemas.stores_schemas` — the same set `app/main.py`
  imports) so autogenerate sees the whole schema, and builds the connection
  URL from the same `DB_HOST`/`DB_PORT`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` env
  vars `app/database.py` reads — the URL is never hardcoded in `alembic.ini`.
- **chatbot_backend's tables are deliberately excluded.** `chatbot_messages` /
  `chatbot_conversations` live in the same Postgres database but are owned and
  migrated by the separate chatbot service (its own `.env`, its own code), not
  by this app's models. `env.py`'s `include_object` filter skips any reflected
  table that has no counterpart in `Base.metadata`, so autogenerate never
  proposes dropping them.
- The first revision (`baseline`) is deliberately **empty** — `pass` in both
  `upgrade()` and `downgrade()`. The production database already has this
  schema (built by `create_all()` and loaded from Excel), and autogenerate
  confirmed zero drift against the models, so there is nothing to create.
  It exists only to give every environment a shared starting point.

**Workflow:**
```
# after changing a model:
alembic revision --autogenerate -m "describe the change"
# review the generated file — autogenerate is a first draft, not a fact —
# then apply it:
alembic upgrade head
```

A database that already has the schema (e.g. anything migrated from before
Alembic existed) should be stamped rather than migrated the first time:
`alembic stamp head`. **Running the pending migrations is now a required
deploy step** — a code change that adds/renames/drops a column is not fully
deployed until `alembic upgrade head` has run against that environment.

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
- `require_admin(user_payload, db)` — admin-only routes: **account management, the activity-log feed, deleting/undoing a delete, and reopening a closed record**. No permission grants these.
- **Edit permissions are record-agnostic.** Holding `can_edit_*` lets a user
  edit, submit or revert ANY record in that module, not only ones they
  created — there used to be an additional ownership check
  (`verify_entry_ownership`) restricting this to a user's own records, removed
  because it broke the shared operational workflow this system supports and
  hard-locked any record whose creator had since been deactivated.
  `created_by_id` is still recorded on create (audit trail only).
- Enforced **server-side** on every route. The frontend hiding something is UX, never the security boundary.

### The permission catalogue

`can_{view,add,edit,delete}_{imports,logistics,trucking}_consignments` ·
`can_view_{overview,imports,logistics,purchases,inventory}_dashboard` ·
`can_{view,add,edit}_master` · `can_make_reports` · `can_use_assistant`.

Mapping: create→`can_add_*`, list/get/export/history→`can_view_*`,
update→`can_edit_*`, delete/undo-delete→`can_delete_*`,
submit→`can_add_*|can_edit_*`, reopen→admin-only. Masters read→
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
  - **A STRING COLUMN DOES NOT ENFORCE THE ENUM, AND THE LOADERS GO ROUND IT.**
    The only thing that validates these values is the Pydantic request schema,
    which the loaders never touch — so a workbook can put anything in an
    enum-backed column and nothing objects until somebody tries to SAVE that
    record, at which point the `PUT` 422s on a field they never touched. Imports
    was in exactly that state on 96.6% of its rows (`mode_of_shipment`,
    `payment_instrument`, `unit_of_measurement`), repaired by Alembic revision
    `d5e81b6a2c07`.
  - **Trucking and logistics are still in it.** Measured, not fixed:
    trucking `payment_status` (`Paid` 210, `To pay` 91, `Topay` 2),
    `trucking_vehicles.container_type` (`20 FT` 94, `40 FT` 11),
    `tracking_status` (`On Road` 23, `Planned` 4) — **309 of 1369 jobs cannot be
    saved**; logistics `department` (`G.I Floor Mills` 1) — **1 of 745 orders**.
    `logistics_containers.container_type` holds `LCL`/`AIR` but its schema types
    that field as a plain `str`, so it does not reject.
  - **So a loader writing an enum-backed column must normalise onto the enum**,
    the way `load_06_logistics` already does for its status vocabulary. A
    `post_load` check for out-of-enum values in every such column is the
    durable fix and does not exist yet.
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

**Endpoints:** `POST /`, **`POST /{id}/batches`**, `GET /` (paged + filtered),
`GET /export` (xlsx of the filtered set), `GET /{id}`,
`GET /{id}/trucking-jobs`, `PUT /{id}`, `POST /{id}/submit`,
`POST /{id}/reopen`, `DELETE /{id}`, `POST /undo-delete/{id}`,
`GET /change-history/{id}`, `GET /change-history/{id}/{hid}`,
`PUT /revert-update/{id}/{hid}`.

### A consignment is a BATCH of an order

One LC arriving in two shipments is **two consignments sharing one order**.
`ConsignmentBatchGroup` is the order (supplier, origin, currency, type,
incoterm, payment instrument + number, exchange rate + booking + source,
`works_branch_id`); `ConsignmentOrderItem` is what the order BOUGHT, and each
batch's `ConsignmentItem` rows are **allocations against it**. Full design in
`docs/imports-batching-design.md`.

**`POST /consignments/{id}/batches`** adds an arrival to an existing order —
`{"allocations": [{"order_item_id", "quantity"}]}` and nothing else. Route,
schedule, clearance and status start EMPTY and are entered afterwards through
the ordinary `PUT`. **There is deliberately no `is_locked` guard on it:** a
closed batch means one shipment arrived, which says nothing about the rest of
the order, and requiring an admin reopen before the next arrival can be
recorded would make the normal case the exceptional one.

**Allocation (`app/imports/allocation.py`) — the invariant and its one writer.**

```
allocated_quantity = SUM(quantity) over every LIVE line on every LIVE batch
                     of this order, per order line;  never > ordered_quantity
```

- **`reconcile_allocation` is the ONLY writer** of `allocated_quantity` and of
  an order line's `is_deleted`. **Six write paths end at it** — create, update,
  batch creation, delete, undo-delete and **revert**. A route that enforces the
  rule while an ordinary edit walks round it is worth nothing.
- **A CHECK cannot express this** (the sum spans rows of another table under
  other consignments), so enforcement is the server, with
  `SELECT ... FOR UPDATE` on the order's lines. **Flush → lock → read the sum
  from SQL**, in that order: locking first matched nothing on a create, because
  the rows did not exist yet, and left `allocated_quantity` at 0 on every new
  order. Never read the sum from `consignment.items` — that is one batch's
  lines and can never see a sibling's.
- **Lock order is fixed: the group row, then the order lines** (ascending id).
  Every path that touches the group row — `claim_batch_sequence`,
  `apply_group_updates` — does so before calling this, so the flush inside it
  lands their UPDATE first. Reversing that deadlocks two concurrent saves.
- `ck_allocation_within_order` + the two lower bounds
  (`ordered_quantity >= 0`, `allocated_quantity >= 0`, revision `c7b210d4e9f3`)
  are the **backstop**, not the enforcement. The lower bounds exist because the
  upper one bounds a SUM, and a negative term satisfies it while the
  quantities do not.
- **Deleting a batch RELEASES its allocation; undoing the delete re-claims it
  and can be REFUSED** if the quantity has since gone to a replacement batch.
- `ordered_quantity` **follows the line while an order holds ONE batch** (which
  is every existing record, and is what lets the wizard work unchanged) and
  **stops following once it splits** — `helpers.resolve_ordered_quantity`. So
  **after a split, posting `quantity` alone can never change what was ordered**;
  a client that wants to must send `ordered_quantity`. Both are optional fields
  on `ConsignmentItemSchema` and both are published per item.
- **A line that allocates against something the order already bought MUST send
  `order_item_id`.** Without it the server reads the line as a NEW item on the
  order — correct on the founding batch, wrong on a later one — and **silently
  creates a second order line**. Measured: adding `{"item_name": "Probe A",
  "quantity": 5}` to batch 2 of an order for 100 of Probe A returns 200 and
  leaves the order claiming it bought **105**, with no error and nothing the
  over-allocation check can see, because each line is within its own order line.
  The id is validated against the order (`UnknownOrderLine`); an id that is
  never sent cannot be.

**Numbering — `177` and `177-2`, and neither is the primary key.**

- A single-batch order shows the **plain** number; a split suffixes **every**
  batch. So **creating a second batch renumbers the first**, `177` → `177-1`.
  No row is written to do it (the number is derived from
  `founding_consignment_id` + `batches_ever` + `batch_sequence`), which matters
  because 142 of 179 consignments are locked. The route's response states the
  renumbering; the user-facing warning is the front end's.
- **Numbers are permanent. Nothing ever renumbers backwards.** Delete `177-2`
  and `177-3` stays `177-3`; an order that splits and then loses a batch keeps
  `177-1` and does **not** revert to `177`. `batches_ever` is incremented and
  never decremented, which is what implements this.
- `claim_batch_sequence` takes the next number with
  `UPDATE ... batches_ever = batches_ever + 1 ... RETURNING` — atomically, not
  read-modify-write. `uq_consignments_group_sequence` is the backstop; a fire
  is a bug report, not something to retry around.
- **Never derive a display number from `consignment.id`.** On batch 2 they are
  different integers and the id belongs to no number anyone can look up. Use
  `order_view.consignment_number()`; the serializer publishes it, the imports
  list and detail header render it, and the wizard's own header does too. The
  id stays the link target and the React key — that distinction is the whole
  point, and collapsing it is how this drifts back.
- **`reference_label()`'s `IMP-{id}` fallback is GONE — step 8.** A row with no
  instrument number now prints the **consignment number**. The fallback was
  meant to disappear entirely once the number was on screen, but none of its
  callers is an imports screen: they are the dashboard drill-downs, the
  notification payloads, the activity log and the reports `ref` column, each
  rendering ONE string with no field beside it, so blanking would have left
  them with no identifier. `reference_label_from` now takes the three numbering
  values instead of a consignment id, so a caller that was not updated raises a
  `TypeError` rather than silently passing the id back in.

**`consignment_batch_groups.is_deleted` is derived from the live batches**
(`helpers.sync_group_deleted_state`, called by delete and undo-delete). It had
no writer at all before step 7, which is how undo-delete could produce a live
batch under a deleted order.

**THE GROUP FREEZE IS BUILT** (design §3.9). A closed batch settles the whole
ORDER, in two tiers, because money has already moved against its terms —
`helpers.assert_group_writable`, raising `GroupFrozenError` → **423**, the same
status the row lock returns.

- **Tier 1 — `HARD_FROZEN`: `exchange_rate`, `rate_booked_on`, `rate_source`,
  `currency`. NOBODY, INCLUDING AN ADMIN.** The valuation inputs; changing one
  restates a stored, reported `pkr_total` (rule 4). **This is the only rule in
  the application `is_admin` does not pass** — every other check in
  `authorize()` lets an admin through unconditionally. Deliberate, and
  commented at both the definition and the raise site.
- **Tier 2 — `ADMIN_FROZEN`: `supplier_id`, `origin`, `consignment_type`,
  `incoterm`, `instrument_number`, `payment_instrument`, `branch_id`
  (→`works_branch_id`). Frozen for normal users, an admin may still write
  them.** Commercial facts, not valuation inputs; correcting one on a
  three-batch LC is normal work, not an exceptional recovery. **Not a guard
  against typos** and must not be documented as one.
- **The two tiers cover EVERY payload-reachable group column — all eleven, no
  gap, no overlap** (asserted in `tests/test_group_freeze.py`). So for a normal
  user a frozen order is entirely read-only, and the tiers diverge only for an
  admin. `insurance_amount` is deliberately in neither: §3.9 exempts the payment
  process, and step 9 wires that column up.
- **The field sets are COLUMN names; callers route payload keys through
  `PAYLOAD_TO_GROUP` first.** `branch_id` is posted, `works_branch_id` is
  stored — comparing the posted key against column names would leave the works
  field editable on a closed order while every other Tier 2 field refused.
- **Closed is `is_closed()` — "Arrived at Works" and nothing else** (rule 8). A
  soft-deleted batch does not freeze. **Whether `Order Cancelled` should is an
  open question**, recorded in §3.9, deliberately not decided.
- **Two write paths reach it, and both check**: `PUT /{id}` (before the
  change-history row, not between it and the apply) and `revert_local_fields`.
  `apply_group_updates` **re-derives the same answer before each setattr** as a
  second line of defence, and **raises rather than skipping** — a silent drop is
  the failure this rule exists to prevent. Create is exempt because it always
  makes a fresh group; batch-create, delete and undo-delete touch only
  bookkeeping columns.
- **Revert is PARTIAL, not all-or-nothing.** It restores what it may and reports
  what it could not, through the same `skipped` channel `RETIRED_HISTORY_KEYS`
  uses — the reason now travels *with* the key (`skipped_detail`), because a
  frozen field is not a retired column and the route used to look each key up in
  `RETIRED_HISTORY_KEYS`, which would `KeyError` inside the success path. A
  frozen key is skipped **whole**, every destination it has: `branch_id` has
  two, and half-restoring it would leave the header and its lines disagreeing.
- **`serialize_consignment` publishes `group_frozen`** (detail only, beside
  `allocation`, for the same N+1 reason): `is_frozen`, `frozen_by`, and the
  `hard` / `admin` field lists **in payload-key form**, so the wizard can
  disable exactly the inputs it has.

**A new batch lands as a `draft` at "TT/LC in Process" with no dates, no ports
and no clearing agent** — `add_batch` copies none of the founding batch's
shipping, because the requirements say a later batch's shipping section starts
empty. So it shows in the list at once, the `drafts_only` filter catches it, and
**it is absent from every windowed dashboard figure until somebody gives it an
ETA**. That last one also bites the test fixtures: an undated split cannot
discriminate rows from orders, which is why `batch_fixture.ensure_split` demands
a dated one.

## logistics — `/logistics`

Export/local orders, restructured to header + children (the frontend redesign
turned it from a flat order into a 5-step wizard: Order, **Packing**, Shipping,
Expenditures, Status).

**Tables:** `LogisticsConsignment` (header: department, order type, origin,
customer, MO/batch, incoterm, shipping, the named expenditure columns +
`container_detention`, status, `gate_out_date`, `sent_to_trucking`) →
`LogisticsItem`, `LogisticsPackage`, `LogisticsContainer` children, plus
`LogisticsStatusHistory` and `LogisticsChangeHistory`.

`sent_to_trucking` (bool) is **deprecated in favour of `sent_to_trucking_at`**
(nullable timestamp, indexed) — a bool alone can't say how long logistics held
an order before handing it off, the same gap imports' own `sent_to_logistics_at`
/ `sent_to_trucking_at` exist to close. `helpers.stamp_trucking_handoff` sets
the timestamp alongside the bool whenever it turns true (on create or update);
the bool is kept and still set too, so nothing reading it breaks. Unchecking the
hand-off does not clear the timestamp — it records when it was last sent, not
whether it is currently sent. The open-requests query (`cross_module.py`) still
filters on the bool, unchanged, for now.

FE-driven nested collections that are always written whole are stored as **JSON**
rather than their own tables: per-item `rfd_history`, per-package `allocations`
(cross-batch: `{item_id, source_order_id, quantity}`), and the header
`remarks_log` feed. MO/batch numbering and cross-batch resolution are
frontend-driven — the backend stores what it's given.

**System remarks are generated server-side** (`serializers.build_system_remarks`,
mirroring imports rule 6) from `status_updates`, the `sent_to_trucking` hand-off
and every item's `rfd_history` — derived on read, never stored, never accepted
from the client. `remarks_log` holds user entries only going forward; the front
end used to synthesize `system: true` rows into it in-memory on every render
(never actually persisting one), so that generation is gone from
`buildRemarksFeed`. Any `system: true` rows an order already has from before
this change are real historical data and are shown **alongside** the generated
`system_remarks`, not replaced by it.

Endpoints mirror imports (`POST /`, `GET /`, `GET /export`, `GET /filter-options`,
`GET /{id}`, `GET /{id}/trucking-jobs`, `PUT`, `POST /{id}/submit`,
`POST /{id}/reopen`, `DELETE`, undo-delete, change-history, revert).

**Closes/locks at "Delivered" AND submitted** — the two-part rule, not status
alone. Only `POST /{id}/submit` sets `is_locked`; the update route never closes
an order, so a draft may sit at "Delivered" and stay editable.
`serialize_consignment` returns `missing_fields` (from `submission_errors`,
imported inside the function to dodge the helpers cycle) so a disabled Submit
and a failed submit can't disagree.

**Logistics NO LONGER MATCHES IMPORTS on either of these.** Imports moved to a
one-part close test and deleted its rule set (rule 8); logistics and trucking
kept both. Do not "fix" this file's two-part wording to match imports — the
divergence is deliberate and imports-only.

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
submitted** — the two-part rule, as in logistics (**not** imports, which moved
to the status alone — rule 8), not the vehicles alone. Only
`POST /{id}/submit` sets `is_locked`; the update route never closes a job. `serialize_consignment` returns `missing_fields`, and the history
serializer returns `changed_at` (both imported inside the function to dodge the
helpers cycle).

**System remarks** are generated server-side too (`serializers.build_system_remarks`,
mirroring imports rule 6 and logistics), but trucking has neither an
ETA-revision nor a status-history table to chain — there is no stored
job-level status at all (above). So instead of a dated narrative, it states
where the job was taken from (`source`/`source_ref`/`taken_at`) and a
same-instant rollup of the vehicles' CURRENT tracking statuses, the only
"status" data this module keeps.

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
  form pre-fills from, plus **`payment_reference`** — the queue used to print
  `instrument_number` raw and call one consignment `6222` where every other
  screen said `lc6222`.
- **`GET /logistics/import-fob-jobs`** — the logistics side: consignments with
  `sent_to_logistics_at`. Never consumed; logistics has no "take" step. Carries
  **`consignment_number`** and **`payment_reference`**: the Service Jobs row
  held a front-end copy of the display rule, `IMP-{consignment_id}` fallback
  and all, which after step 8 would have been the last place in the app still
  printing `IMP-`.
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
`ref/item/supplier/branch/category/status/value/date` + ~80 type-specific keys;
a key a type has no value for is null, and every row carries its `type`).
Unlike the dashboards this **does** return rows (a report is a table you
download), so it is **paginated**. Reuses the dashboard derivations (purchase
status, stock status + reorder level, logistics cost/kg + stage) — a figure in
a report matches the same figure on its dashboard. Wired end-to-end: front end
(`Reports.tsx`, `reportBuilder.tsx`) talks to the live endpoints below, not
mock data; `savedReports.ts`'s old localStorage list was replaced by the
`SavedReport` table.

**Imports and logistics are ONE ROW PER LINE item, not per consignment/order —
purchases and inventory stay one row per source record.** Per-line fields
(HS code, quantity, unit price, ELC/ALC, RFD dates, ...) exist only on the
child table (`ConsignmentItem` / `LogisticsItem`); folding them onto one header
row per consignment either drops them or forces an arbitrary aggregate, so
`app/reports/helpers.py::_MODEL` queries the LINE table for these two types and
joins back to the header (`_JOINS`) for everything header-level, which then
simply repeats on every line of the same consignment/order — normal for a flat
export. One consequence: filters that used to mean "does ANY line of this
consignment match" (shaft, category) now mean "does THIS line match" — more
precise, since a consignment with one shaft line and four other items used to
hand back all five rows under the shaft filter.

- **`value` follows the same line-vs-header split as valuation elsewhere in
  the app.** Imports gets a genuine per-LINE PKR figure (quantity × unit price
  × the consignment's booked rate, `serializers._line_value_pkr`) — repeating
  the whole consignment's `pkr_total` on every one of its rows would multiply
  it the moment someone sums the column, the same trap the dashboards avoid
  (see "Imports money is counted in the month it ARRIVED"). Logistics has no
  per-item cost breakdown at all, so `value` stays the ORDER's total cost
  (`total_logistics_cost`), repeated per line — the individual freight/packing/
  etc. columns are the real per-order figures either way, `value` is just
  their sum, same as before this change.
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
  **shared** (everyone who can reach Reports sees all templates). `GET/POST
  /reports/saved`, `GET/PUT/DELETE /reports/saved/{id}`. All of reports is
  gated by `can_make_reports`; a saved template may be edited/deleted only by
  its creator or an admin.
- **Dropped for want of a backend source** (by decision): imports `customer`
  (no such concept on a consignment) / `shipping line` / `bank` (Payment is its
  own one-to-many child table, not folded in) / `documentation status`
  (the Documentation dashboard tab was never built either); inventory
  `last_restocked`; purchases `material`. Imports `ref` is the payment
  reference, falling back to the **consignment number** (`177`, `177-2`) — it
  was `IMP-{id}` until step 8; `ppc_store` stays a date.

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

**AN ABSENT PAYLOAD KEY MEANS "CLEAR IT" — except for the columns the SERVER
resolves.** The request schemas default every optional field to `None` and
`model_dump()` cannot tell a null the client sent from a key it never
mentioned, so the diff reads both as a change to null. That is correct and
relied upon: the wizard clears a field by OMITTING it (`draftToPayload` sends
`undefined`, not `""`). It is wrong for a NOT-NULL column nobody types, and it
was a **500 on every edit of an existing consignment** — the imports wizard
sends neither `ordered_quantity` nor `order_item_id`, the diff wrote NULL over
both, and the next autoflush hit the constraint before `sync_order_items` could
resolve them. `imports.helpers.SERVER_RESOLVED_ITEM_FIELDS` names the two, and
`updated_items` skips a field in it that the client did not actually set
(`model_fields_set`). **`exclude_unset=True` on the whole payload is the wrong
fix** — it would make clearing any field silently stop working. Add a name to
that set only for a column a server function owns; `item_id` deliberately is
NOT in it (see `tests/test_item_diff.py`).

**Change history + field-level revert.** Every update writes one
`*ChangeHistory` row whose `history` JSON holds the pre-change values (header
`fields`, plus per-collection `new_*` / `deleted_*` / updated diffs). Revert
(`can_edit_*`, latest-first) writes the old values back, re-adds soft-deleted
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
  `drafts_only` (= `record_state == 'draft'`; **renamed** from `missing_only`,
  which promised a completeness check that no longer exists — see rule 8),
  `etd_from`/`etd_to`, `include_closed` (default false hides "Arrived at Works"
  and "Order Cancelled"), `include_deleted`, `q`, `page`, `page_size`.
  **NO `batch_group_id` FILTER YET, and there needs to be one** — there is
  currently no way to fetch an order's sibling batches, which the batching UI
  needs to show an earlier batch's route locked above a later one. Worse than
  missing: FastAPI drops an undeclared query param, so `?batch_group_id=21`
  returns a full unfiltered page and *looks like it worked*. `?q=<instrument
  number>` happens to return the siblings (it is on the group, so they share
  it) but is not a substitute — it fails for an order with no number and
  matches other orders containing the same substring.
  **Nor a pending-allocation flag**, which the list's blue highlight needs; the
  `allocation` block is detail-only on purpose (it reads `group.order_items`,
  which the list does not load). Add a boolean computed in SQL, not the block.
  Design §3.7b has both, measured.
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

**8. Draft vs submitted + the closed lock. IMPORTS HAS NO SUBMIT RULE SET.**

`record_state` (`'draft'`/`'submitted'`, `server_default 'draft'`) means only
**"a user has marked this record finished. Nothing verifies that claim."** Save
draft = the permissive create/`PUT`. **Submit** = `POST /{id}/submit`, which
sets `record_state` and does nothing else: it runs no rules, cannot `422`, and
never locks. It drives exactly one thing, the `drafts_only` list filter, and is
otherwise informational and a column in the export (headed "Marked finished").

`submission_errors()`, `missing_fields`, `REQUISITION_REQUIRED` and the three
front-end mirrors (the zod submit schema, `submitRequirements`, the requirements
banner) are **deleted**. Data quality moves to the input layer — dropdowns,
masters, required-at-entry. The rule set encoded the same requirements three
times in two languages, and the three could disagree.

**This is an imports-only divergence, deliberately.** `app/logistics/helpers.py`
and `app/trucking/helpers.py` keep their own `submission_errors()`, still block
submit, still publish `missing_fields` and still use the shared
`SubmitRequirements` component. A user working across all three modules will
find imports behaves differently. That is a cost of the decision, not an
oversight. Nothing replaces imports' "N fields missing" tag, row highlight,
disabled Submit or pending-information banner.

The **closed lock** is separate and is the **status alone**:
`helpers.is_closed(c)` is `c.current_status == "Arrived at Works"` —
`record_state` is *not* half of it, so a draft at that status is closed too.
Closing is a statement about the world (the goods are at the factory), not
about an administrative gesture.

**`is_locked` is written by `update_consignment.py`, on the transition into
that status, and nowhere else.** It used to be written by
`submit_consignment.py` and nowhere else — CLAUDE.md previously claimed the
update route set it and that was wrong, which is why all 142 locked rows in
production were locked by the Excel loader rather than by anyone using the app.
The two writes are only safe to change together: deleting one without adding
the other removes the closed lock from the system silently. The write sits
*after* the `423` guard and *after* the status is applied, or the request that
closes the consignment would reject itself.

Once locked, **no role** may edit — update/submit return `423`. Only an
**admin** reopens via `POST /{id}/reopen`. The confirmation dialog is on the
**status change**, not on submit; it warns about permanence but **cannot say
what is missing**, because `missing_fields` is gone. `helpers.py`'s list-side
`is_truly_closed` is the same one-part test in SQL and must move with
`is_closed` — left as the two-part test it would match almost nothing and
`include_closed=False` (the default) would quietly stop hiding closed rows.

Loaded rows import unlocked. Logistics closes at "Delivered", trucking when
all vehicles are delivered — **both keep their two-part test and their rule
sets**; only imports changed.

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
  camelCase↔snake_case and names↔ids.

  **IT DOES NOT GATE ENUM VALUES. This file used to claim it did, and that claim
  is why a live bug went unnoticed for months.** `apiToDraft` casts with
  `as ConsignmentDraft['modeOfShipment']` — a compile-time assertion with **no
  runtime effect** — and `draftToPayload` passes the raw string straight back
  through `strOrUndef`. The only field with a real gate is `consignment_type`
  (`CONSIGNMENT_TYPE_TO_API`).

  The consequence: **a loaded consignment could not be saved.** The detail route
  returned `mode_of_shipment: "Sea"`, the wizard posted the whole draft back, and
  `ConsignmentSchema` rejected it — a 422 on a field the operator never touched,
  on 172 of 178 live records (96.6%). Fixed in the data by Alembic revision
  `d5e81b6a2c07`, not in the map; the map still does not gate, so **anything
  reaching these columns from outside the app must already be canonical.**
  **`consignmentNumber` is separate from `systemId`, and that is load-bearing.**
  `systemId` is `String(c.id)` — a route target and a React key. What the list,
  the detail header and the wizard header SHOW is `consignmentNumber`, straight
  off the payload. It does not fall back to the id: on a later batch the id is
  a number belonging to no consignment (design 0.4), so a blank is the honest
  rendering of a missing number and a dash is what appears.

  **`works` is gone from the draft and from the payload.** It was free text on
  the Finance step that the server discards (`RETIRED_PAYLOAD_FIELDS`); Works
  and Branch are one field, and Step 1's **"Works / Branch"** dropdown — which
  writes `branch_id` → the order's `works_branch_id` — is the dropdown the
  requirements asked for. The backend still accepts the key, for an old client
  and for a revert across an old history row.

  **`origin` is a `SearchableSelect` over ISO 3166 (`lib/countries.ts`), with
  free text OFF.** It replaced an eight-option `<select>` that rendered BLANK
  for any stored value outside those eight — 76 of the 174 consignments that
  state an origin — while the value itself was intact. A non-ISO stored value
  is DISPLAYED, SURVIVES a save it was not edited in, and is flagged beside the
  field. That behaviour stays whatever the data looks like; it is what protects
  the next workbook that invents a spelling.

  **The stored data is ISO too, and is corrected in TWO places.** Alembic
  `f3a91c60d28b` mapped 11 spellings across 59 rows (`Turkey`→`Türkiye`,
  `UAE`→`United Arab Emirates`, `SA`/`KSA`→`Saudi Arabia`, `USA`, `Korea`/
  `South Korea`, `Taiwan`, `Tanzania`, two misspellings of the Philippines),
  and `load_05_consignments.map_country` applies the same mapping at load time
  so a reload cannot undo it. **`SA`→Saudi Arabia was a business decision**,
  not an inference — the column also holds `South Africa` and `KSA`.
  - **It updates BOTH `consignment_batch_groups.origin` and the orphaned
    `consignments.origin`**, because the chatbot's `v_import_shafts` reads the
    second one (see "Database migrations" — those views are invisible to
    `create_all`, autogenerate and `configure_mappers()`). Updating one would
    have split what the ERP says from what the chatbot says.
  - **The downgrade is a documented no-op**: the mapping is many-to-one, so
    reversing it would write a spelling onto records that never carried it.
  - A country `map_country` does not recognise is **kept and reported**, never
    dropped, against an 18-name allow-list of what this data holds —
    deliberately not a second copy of all 249 names.
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

## Verifying a change

Each part of the system is proved differently, and the commands are not
interchangeable:

- **ERP backend** —

  ```
  python -c "import app.main; import sqlalchemy.orm as o; o.configure_mappers(); print('ok')"
  ```

  Imports every model, route and router, so a bad import, a broken decorator
  or a route that shadows another shows up here.

  **`configure_mappers()` is not optional, and `import app.main` ALONE IS NOT
  A CHECK.** `main.py` builds its tables inside a retry loop that catches and
  logs whatever startup raises, so a broken MAPPER — a relationship whose join
  column no longer exists, which is what removing a mapped attribute does —
  is written to the log and swallowed. The bare import **exits 0** on a tree
  where every query in the app would 500. Measured, on a tree with two of
  `Consignment`'s foreign keys deleted: bare import exit 0, the command above
  exit 1 naming the relationship. `configure_mappers()` forces the
  configuration the import defers and re-raises the cached failure.

  **It connects to whatever `DB_NAME` says, and `create_all` runs at import.**
  So running it after adding a model CREATES that model's tables in the
  database it points at. Point it at a scratch database when the change adds
  a table, or the "verification" quietly applies half a migration outside
  Alembic:

  ```
  DB_NAME=scratch_something python -c "import app.main; import sqlalchemy.orm as o; o.configure_mappers()"
  ```
- **Frontend** — an esbuild bundle of `src/main.tsx`. Note esbuild strips
  types without checking them, so it catches a broken import or a syntax
  error but NOT a type error; `tsc -b` is what the real build runs.

**THE CHATBOT IS A SEPARATE SERVICE, AND `import app.main` PROVES NOTHING
ABOUT IT.** Nothing under `chatbot_backend/` is loaded by the ERP app — it has
its own code and its own `.env` (the same reason its tables are excluded from
Alembic, see "Database migrations" above). A chatbot change that breaks on
import will sail past the ERP check looking perfectly healthy.

So for anything under `chatbot_backend/`, import the changed module directly
and exercise the functions you touched:

```
cd chatbot_backend
../venv/Scripts/python.exe -c "from backend.database import conversation_store as cs; ..."
```

It runs on the **ERP venv** — there is no separate one — but the package root
is `chatbot_backend/`, so `backend.*` imports only resolve from inside that
directory.

## Running tests

```
pip install pytest          # not in requirements.txt — a dev-only dependency
python -m pytest tests/ -q
```

**The pytest suite is pure and needs no database.** Every function it covers
takes objects and returns or mutates values, so the tests build plain Python
stand-ins (`tests/conftest.py`) rather than ORM rows. It passes with the
database unreachable, which is the property that keeps it honest about the
CLAUDE.md rule above — there is nothing for it to write to.

What it covers, chosen for consequence rather than coverage percentage:

- `test_derived_totals.py` — `recompute_derived`. The money totals are
  STORED, so an error here is written once and then read back for ever by
  every dashboard, report and export, all agreeing because they all read the
  same wrong number. Pins Decimal exactness, the null-vs-zero rules
  (a missing rate leaves `pkr_total` NULL, never 0) and idempotence.
- `test_closed_lock.py` — `is_closed` and the transition that writes the lock.
  It exists because **no existing data exercises this path**: every locked row
  in production was locked by the Excel loader, so the app-side lock has never
  run in anger, and a regression shows up as a consignment quietly staying
  editable after its goods arrived rather than as an error. Pins the one-part
  test (status alone, `record_state` irrelevant), that cancelling does not
  lock, and that submitting has no side effect.
  **It replaces `test_submission_rules.py`, which was deleted with
  `submission_errors()`** — recorded here rather than left to look accidental.
- `test_notification_transitions.py` — the crossing rule, the hysteresis
  band, the rank filter and the stockout movement gate. A regression here is
  not an error message, it is a flood.
- `test_packing_costs.py` — `packing_cost_kpis`, where a missing cost must
  not read as a zero cost.
- `test_batch_numbering.py` — the A1/A3 numbering rules,
  `resolve_ordered_quantity` and the allocation refusal messages. A numbering
  error renames 179 live records at once, or makes a number that has been on
  an invoice resolve to a **different** shipment.
- `test_list_filter_joins.py` — every query naming two tables must say how they
  join. It reads the **compiled SQL** for a FROM clause listing two tables with
  no `ON`, because a cartesian product returns 200 with a full page of real
  rows in it and no assertion on the response body can see it. Its own detector
  is tested both ways: each of the three historical broken statements is
  reconstructed and must be caught.

**The integration scripts are NOT part of the pytest run.** Each needs a live
app, a real database and a login, and each **mutates**, so all three are
guarded to scratch databases (`tests/batch_fixture._require_scratch`, which has
no override). Run them by hand:

```
DB_NAME=scratch_x python -m uvicorn app.main:app --port 8011
DB_NAME=scratch_x python tests/check_dashboard_consistency.py   # after any dashboard change
DB_NAME=scratch_x python tests/check_batch_allocation.py        # after any allocation change
DB_NAME=scratch_x python tests/check_allocation_concurrency.py  # after touching the lock
```

- **`check_dashboard_consistency.py`** asserts the same metric reads the same
  on every screen. Its batches-vs-orders section needs a **split order** to say
  anything — with one batch per group, rows and orders are the same number and
  every assertion passes whichever unit the code uses. Build one first with
  `DB_NAME=scratch_x python -m tests.batch_fixture`, which splits through the
  real routes.
- **`check_allocation_concurrency.py` reproduces the race against unlocked
  code before testing the lock.** Part 1 reconstructs the pre-lock shape
  locally and must end with 300 allocated against an order for 250, both saves
  committed and nothing raised; if it stops reproducing that, the script stops
  rather than reporting a pass. **There is no `use_lock=False` flag** — a
  parameter that exists only for a test is one production code can pass.

## Test scripts never touch the live database

**A test or verification script must NEVER delete from or write to an
operational table.** No such script may contain `DELETE FROM` or `TRUNCATE`
against one. Use one of:

- a transaction that is **always rolled back**;
- a **separate scratch database**;
- **assertions against existing data, with no mutation at all** — usually
  enough, since most checks are questions about what is already there.

The rule exists because it was broken. A round of notification tests each ended
in a `finally:` block that ran `DELETE FROM notification_deliveries` and
`DELETE FROM notification_events` to leave a clean slate. It emptied the real
tables, and the panel went blank.

The cleanup is what made it expensive rather than merely careless. Notification
events are re-raised by the scanner only on a **crossing** (see the threshold
scanner note above), and `notification_state` still recorded every threshold as
already alerting — so the deleted events could not come back on their own, and
recovery meant clearing that state as well. **Deleting rows can destroy state
that no longer regenerates itself**, and which rows those are is rarely obvious
from the script.

**The loaders are a different category and are not covered by this.**
`app/loading/scripts/` exists to mutate — `load_all` drops and rebuilds,
`add_customer_master` and `add_transporter_master` merge duplicate rows,
`retire_delete_permissions` removes retired permission rows. Those are
deliberate, reviewed, explicitly-invoked data migrations, and their `DELETE
FROM`s are the point of them. The rule is about scripts written to CHECK
something, which have no business changing anything in order to do it.

Read-only diagnosis is the same rule seen from the other side: prefer a
question the database can answer over an experiment it has to be changed for.
`recipients_for()`, `is_closed()` and every serializer are pure reads
and can be called freely against production data. Where a check genuinely needs
a mutation, it needs a scratch database, not a `finally:` block.

## When to stop and ask

Business rules around imports, LCs, customs, duty, stock and purchasing are
domain knowledge, not something to infer. If a rule is unclear or a requested
change contradicts something above, raise it rather than resolving it silently.
