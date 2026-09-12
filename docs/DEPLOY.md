# Deploying the imports-batching release

**Read this whole file before starting.** It is written for someone who was not
part of building this, on a day when none of it is fresh.

This release is different from every previous one: it **changes the database
schema** and it **changes what the chatbot's views read**. A normal
`pull-latest.bat` and a service restart is NOT enough, and doing only that
leaves the server in a state the migration can no longer repair without manual
work. The order below is not a suggestion.

**Legend**

- 🔐 needs **Administrator** (an elevated PowerShell).
- ⚠️ **has never been run against production.** Everything in this file was
  rehearsed on a developer machine against a restored copy of the 9 September
  production backup. That rehearsal is described at the end.

---

## 0. Before the window — checks you can run while everything is still up

All read-only. Do these a day early if you can; two of them can change the plan.

### 0.1 Snapshot what production actually is 🔐

```powershell
powershell -ExecutionPolicy Bypass -File .\server-survey.ps1
```

Writes `server-survey-<date>.txt`. It changes nothing. You need it for the
service names in step 2 and the Python/venv paths in step 5.

### 0.2 The two pre-migration data checks the design doc asks for

Design doc §4.3 and §4.9. Both are questions, not fixes — but if either answers
differently from the rehearsal, **stop and ask before migrating.**

```sql
-- §4.3: lines with no quantity. `ordered_quantity` is NOT NULL and back-fills
-- as COALESCE(quantity, 0), so these become 0.000 rather than aborting the
-- migration. Rehearsal found 2. A much larger number means the workbook
-- changed shape and the back-fill is papering over something.
SELECT id, consignment_id, item_name
  FROM consignment_items
 WHERE quantity IS NULL AND is_deleted = false;

-- §4.9: drafts already sitting at the closing status. Rehearsal found ZERO.
-- Anything here gets locked by the new one-part close rule the moment it is
-- next saved, and whoever owns it should know first.
SELECT id, current_status, record_state, is_locked
  FROM consignments
 WHERE current_status = 'Arrived at Works'
   AND is_locked = false AND is_deleted = false;
```

### 0.3 Change history holding pre-enum values ⚠️

**Found during the rehearsal; this check is new and has never run on
production.** The enum migration normalises the *columns*. It does not touch
the *change-history JSON*, so a history row can still hold `'Sea'` as an
`old_value`. Reverting that row writes `'Sea'` back onto the consignment, and
the record then **cannot be saved at all** — a 422 on a field the operator
never touched.

```sql
SELECT h.id, h.consignment_id,
       h.history::json->'fields'->'mode_of_shipment'->>'old_value'  AS mos,
       h.history::json->'fields'->'payment_instrument'->>'old_value' AS pi,
       h.history::json->'fields'->'unit_of_measurement'->>'old_value' AS uom
  FROM consignment_change_history h
 WHERE (h.history::json->'fields'->'mode_of_shipment'->>'old_value')
         NOT IN ('Sea freight FCL','Sea freight LCL','Air freight','Land/courier')
    OR (h.history::json->'fields'->'payment_instrument'->>'old_value')
         NOT IN ('LC','Adv','DP','CAD');
```

The rehearsal found **one** such row. There is no fix in this release — record
the ids, and tell whoever uses that consignment not to revert past that entry.
It is not a reason to delay the deploy; it is a reason not to be surprised.

---

## 1. Take a backup 🔐 — and do not skip it

Everything after this point is reversible **only** because of this file.

```powershell
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
    -U postgres -h localhost -d supply_chain_erp `
    -f "C:\erp_backups\pre_batching_$stamp.sql"
```

- Put it somewhere that is **not** the repo folder. `C:\erp_backups\` is the
  convention used here; create it if it does not exist.
- Expect roughly **80 MB**. A file of a few hundred KB means it failed — check
  the output before continuing.
- **Do not delete it after a successful deploy.** Keep it until the release has
  run for a week.

---

## 2. Stop both services 🔐

There are two NSSM services: the ERP backend and the chatbot backend.

> **Names:** `________________` and `________________`
>
> Fill these in from the `NSSM-managed service names found:` line in
> `server-survey-<date>.txt` (step 0.1). They are not hardcoded here because
> this file has never been run on that machine and guessing a service name in a
> runbook is how someone stops the wrong thing.

```powershell
nssm stop <erp-service-name>
nssm stop <chatbot-service-name>
Get-CimInstance Win32_Service | Where-Object { $_.PathName -match 'nssm' } |
    Select-Object Name, State        # both should read Stopped
```

**Why before the migration:** see step 5. A running ERP service will create the
new tables behind Alembic's back and make the migration fail.

---

## 3. Pull the code

```
.\pull-latest.bat
```

**What it does:** aborts a half-finished merge, discards local edits to five
runtime files only (the chatbot's query cache, data profile and learned terms,
and the ERP's two logs), stashes anything else still modified, then
`git pull origin main`.

**What it does NOT do — every one of these is a separate step below:**

| It does not | Step |
|---|---|
| run Alembic | 5 |
| run `pip install` | 4 |
| build the frontend | 6 |
| apply the semantic views | 7 |
| restart anything | 8 |

If it prints `PULL FAILED`, stop. Nothing is lost — your work is committed or
in `git stash list`. Send the message on screen rather than forcing anything.

Confirm you have the right code before going on:

```powershell
git log --oneline -1          # expect the merge that brings in step 6 + the chatbot views
git status --short            # expect clean, or only untracked survey output
```

---

## 4. Python dependencies

**How to tell whether it is needed:** compare the file against the venv.

```powershell
git diff HEAD@{1} --stat -- requirements.txt     # did the pull change it?
```

If it changed — or if you are unsure — running it is harmless:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

`pytest` is **not** in `requirements.txt` (it is a dev-only dependency) and is
not needed on the server.

---

## 5. `alembic upgrade head` — BEFORE starting any service ⚠️

**This is the step with the trap in it.** Read the reason; it decides the order
of everything above.

`main.py` calls `Base.metadata.create_all()` at startup, gated on whether the
database carries an Alembic revision. Production **is** Alembic-managed, so the
gate is active and `create_all` is skipped — *but only for tables that already
exist*. Start the ERP service before migrating and `create_all` creates
`consignment_batch_groups` and `consignment_order_items` **empty**: no data
copied, no `alembic_version` row, and no ALTER of the tables the migration also
needed. `alembic upgrade head` then dies with

```
DuplicateTable: relation "consignment_batch_groups" already exists
```

and the database sits half-changed. Recovery is dropping those tables by hand
and migrating again. **So: services stopped (step 2), migrate, then start.**

```powershell
cd C:\path\to\supply_chain_erp_complete
.\venv\Scripts\python.exe -m alembic current          # expect: 3142a00a5b31
.\venv\Scripts\python.exe -m alembic upgrade head  | Tee-Object -FilePath "C:\erp_backups\alembic_$stamp.log"
```

**Never `alembic stamp`.** If a database is at the wrong revision, the fix is
restore-then-upgrade, not a stamp. A stamp tells Alembic a migration ran when
it did not, and the next upgrade then skips the work.

### 5.1 SAVE THE OUTPUT — it is the only record of what changed

The second migration (`d5e81b6a2c07`) **prints a table of every value it
rewrote** and that report exists nowhere else afterwards. The `Tee-Object`
above captures it; check the file is not empty. It looks like this (rehearsal
figures, from the restored 9 September backup):

```
  consignments.mode_of_shipment:      170 changed   ('Sea' -> 'Sea freight FCL', 92 rows; 'Air' -> 'Air freight', 23; ...)
  consignments.payment_instrument:     87 changed   ('Advance' -> 'Adv', 71 rows; 'FOC' -> NULL, 6; ...)
  consignment_batch_groups.payment_instrument: 87 changed
  consignment_items.unit_of_measurement:        59 changed   ('Kgs' -> 'Kg', 31; 'MT' -> 'Ton', 7; ...)
  consignment_order_items.unit_of_measurement:  59 changed
  462 cells changed in total. Originals are in enum_normalisation_audit and downgrade() restores from it.
  live consignments still holding an out-of-enum value ANYWHERE: 0 of 179
```

**Production's numbers will differ** — it has more rows than the 9 September
backup. What must match is the **last line: `0 of N`.** Anything other than
zero means a value the mapping does not cover, and the consignments holding it
cannot be saved. Stop and report the output rather than continuing.

### 5.2 Confirm the end state

```sql
SELECT (SELECT version_num FROM alembic_version)                 AS revision,     -- d5e81b6a2c07
       (SELECT count(*) FROM consignments)                       AS consignments,
       (SELECT count(*) FROM consignment_batch_groups)           AS groups,       -- = consignments
       (SELECT count(*) FROM consignment_order_items)            AS order_items,  -- = live item lines
       (SELECT count(*) FROM consignments WHERE batch_group_id IS NULL)  AS orphan_consignments,  -- 0
       (SELECT count(*) FROM consignment_items WHERE order_item_id IS NULL) AS orphan_lines;      -- 0
```

Both orphan counts **must** be zero.

---

## 6. Build the frontend

The server does not run Vite's dev server; it serves the built `dist/`.

```powershell
cd React_Frontend-main\frontend
npm ci                 # or npm install if ci complains about the lockfile
npm run build          # this is `tsc -b && vite build` — a type error fails it
```

**Confirm how the built files are actually served before you overwrite them** —
`server-survey.ps1` shows whether that is IIS, a static route in the ERP
service, or something else. If `dist/` is served directly from the repo folder,
the build above is all that is needed. If it is copied elsewhere, copy it.

A failing `tsc -b` here is a real failure. Do not work around it with
`vite build` alone — that skips type checking and ships the error.

---

## 7. The semantic views ⚠️ — expect this to fail, and know why

The chatbot reads two views (`v_import_shafts`, `v_item_demand_picture`) that
were built over columns this release moved. Muhtasham's branch repoints both.

```powershell
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost `
    -d supply_chain_erp -v ON_ERROR_STOP=1 `
    -f .\chatbot_backend\database\semantic_views.sql
```

**`-v ON_ERROR_STOP=1` is not optional.** Without it psql prints the error and
carries on, the run looks successful, and the view silently keeps its old
definition.

### What will happen, until Muhtasham's one-line fix lands

```
psql:chatbot_backend/database/semantic_views.sql:182: ERROR:
  cannot change data type of view column "unit_price" from numeric(14,4) to numeric(18,4)
```

Exit code **3**, and **everything after line 182 never runs.** `CREATE OR
REPLACE VIEW` cannot change a column's type, and `unit_price` widens when it
moves from `consignment_items` to `consignment_order_items`.

### The workaround — proven in the rehearsal

Drop that one view first, then run the file again:

```powershell
& "...\psql.exe" -U postgres -h localhost -d supply_chain_erp `
    -c "DROP VIEW IF EXISTS v_import_shafts CASCADE;"
& "...\psql.exe" -U postgres -h localhost -d supply_chain_erp `
    -v ON_ERROR_STOP=1 -f .\chatbot_backend\database\semantic_views.sql
```

That exits **0**. Verify no view still reads the moved columns — ask the
database, do not read the file:

```sql
SELECT v.relname AS view, t.relname AS reads, a.attname AS column
  FROM pg_depend d
  JOIN pg_rewrite r       ON r.oid = d.objid
  JOIN pg_class   v       ON v.oid = r.ev_class
  JOIN pg_attribute a     ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
  JOIN pg_class   t       ON t.oid = d.refobjid
 WHERE t.relname IN ('consignments','consignment_items')
   AND a.attname IN ('supplier_id','origin','item_code','item_name',
                     'specification','unit_price','unit_of_measurement');
```

**Zero rows is the pass.** Any row means a view is still reading a column the
app no longer maintains, and the chatbot will answer with values frozen at
whatever they were before this release — silently, with nothing to notice.

If the drop-first workaround is also refused, **stop and leave the old views in
place.** The chatbot returning slightly stale import answers is a much smaller
problem than a half-applied view file.

---

## 8. Start both services 🔐

```powershell
nssm start <erp-service-name>
nssm start <chatbot-service-name>
Start-Sleep -Seconds 20
Get-CimInstance Win32_Service | Where-Object { $_.PathName -match 'nssm' } |
    Select-Object Name, State
```

Then read the logs before touching the browser:

```powershell
Get-Content .\erp_backend.err.log -Tail 40
```

- The ERP log should show `Application startup complete.`
- It must **not** show any `CREATE TABLE` activity. If it does, `create_all`
  ran, which means step 5 was skipped or the gate did not fire — stop and
  check `alembic current`.
- The chatbot should print `[warmup] chat tables ready` and must **not** print
  `access_token cookie ... could not be verified`.

---

## 9. Smoke test — in a real browser, not with curl

Do these in order. Each one exercises something the release changed.

| # | Do this | Expect |
|---|---|---|
| 1 | Log in | Lands on the app, no 401s |
| 2 | Open the imports list | Rows render, total count looks right, filters populate |
| 3 | Open one loaded consignment | Branch, supplier, origin, currency, **Requisition date and Required date all show values** — these now come from the order lines, and blanks here mean the migration did not copy |
| 4 | Edit one field, save through the "Save and move" dialog, reload | The change stuck |
| 5 | Open that consignment's change history | The newest entry names the fields changed, old → new |
| 6 | Open the Overview dashboard | Tiles show money, not `Rs 0` and not blanks |
| 7 | Imports / Purchases / Inventory / Logistics dashboard tabs | All four render |
| 8 | Export the imports list to Excel | Downloads; Branch, Supplier, Currency, Exchange rate columns are populated |
| 9 | Ask the chatbot one import question, e.g. *"how many shaft consignments are in transit"* | Answers, and the numbers match the imports dashboard |

**Step 9 is the one that catches a bad step 7.** If the chatbot answers but the
numbers are stale or wrong, the views did not repoint.

---

## 10. If it goes wrong

**Which steps are reversible, and how:**

| Step | Reversible? | How |
|---|---|---|
| 1 backup | n/a | — |
| 2 stop services | yes | `nssm start` |
| 3 `pull-latest.bat` | yes | `git checkout <previous sha>`; anything it stashed is in `git stash list` |
| 4 pip install | yes, rarely needed | reinstall the previous `requirements.txt` |
| 5 **alembic upgrade** | **yes, but read below** | `alembic downgrade 3142a00a5b31` |
| 6 frontend build | yes | rebuild from the previous commit |
| 7 semantic views | yes | re-run the file from the previous commit |
| 8 start services | yes | `nssm stop` |

### Rolling back the migration

```powershell
.\venv\Scripts\python.exe -m alembic downgrade 3142a00a5b31
```

Both revisions have a real `downgrade()`:

- **Revision A** is purely additive — the downgrade drops what it added and
  nothing else. Genuinely reversible.
- **The enum migration** restores every overwritten value **row by row from the
  `enum_normalisation_audit` table**, not by rule. It has to: the mapping is
  many-to-one ('Sea', 'By Sea' and twelve container specifications all became
  'Sea freight FCL'), so nothing in the result says which one a row held. **Do
  not delete `enum_normalisation_audit`** — it is the only thing that makes the
  rollback possible.

### If the downgrade also fails

Restore the backup from step 1. This is the path that always works:

```powershell
& "...\psql.exe" -U postgres -h localhost -d postgres -c "DROP DATABASE supply_chain_erp;"
& "...\psql.exe" -U postgres -h localhost -d postgres -c "CREATE DATABASE supply_chain_erp;"
& "...\psql.exe" -U postgres -h localhost -d supply_chain_erp -v ON_ERROR_STOP=1 `
    -f "C:\erp_backups\pre_batching_<stamp>.sql"
```

Then `git checkout` the previous commit, rebuild the frontend, re-run the old
`semantic_views.sql`, and start the services. **Restore-then-upgrade is the
supported repair path for any Alembic confusion; `alembic stamp` never is.**

### Things that are NOT a rollback reason

- The `unit_price` view error in step 7 — expected, worked around in step 7.
- The chatbot returning 503 while its service is still starting.
- `logistics.export_orders` / `logistics.local_orders` drill-downs returning
  400 on the Overview — a pre-existing bug unrelated to this release.

---

## What this runbook is based on

Every step above except the ones marked ⚠️ was executed on a developer machine
on **12 September 2026**, against `supply_chain_erp` restored from
`erp_backup_live_20260909_0952.sql` — the same 183-consignment,
`3142a00a5b31` starting state production is in today.

The migration ran clean, 462 cells were normalised, and the full test suite
passed against the migrated database: dashboard consistency 79/0, the export
asserted column by column, the route sweep, 448 revert assertions over the
21 genuine pre-migration history rows, 91 pytest, `configure_mappers()`, and
`tsc -b`.

**What the rehearsal could not cover, and is therefore ⚠️ above:** the NSSM
services, the IIS/static serving of `dist/`, `pull-latest.bat` against the
server's actual working copy, and anything that depends on production's own row
counts. Those are the steps to go slowly on.
