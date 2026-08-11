# Chatbot assistant: integration, item demand picture, and correctness guards

Brings the supply-chain chatbot into the ERP as a proxied service, and adds the
machinery that keeps its answers correct as data is reloaded.

Merged `master` in three times along the way, so this is up to date with
`75e25b5 fixed purchases loader` and conflict-free.

## What this adds

**The chatbot as a service** (`chatbot_backend/`, `app/chatbot_proxy.py`)
Runs on `:8010` and is reverse-proxied through the ERP backend at `/chatbot/*`,
so the frontend never needs to know it exists. `start-all.bat` brings up all
three processes.

**A per-item position** (`v_item_demand_picture`)
One row per item carrying current stock, three-month issuance, days of cover,
open demand with the status of each requisition, inbound quantity and earliest
ETA, and the resulting shortfall. The assistant's four-lens answer reads that
one row instead of reassembling five tables per question — which had been
producing a different number on every run.

**A derived data profile** (`chatbot_backend/backend/metadata/data_profile.py`)
Value vocabularies and column fill rates read from the live database rather than
typed into a prompt. This matters: three status lists in the schema notes were
already wrong (they named the ERP's enum values, `Sailing` / `Gate Out`, while
the loaders write `On Water` / `Transportation`), so every in-transit query
matched zero rows and reported that as an answer. The profile is fingerprinted
against row counts and `MAX(updated_at)`, so a reload refreshes it with no code
change.

**Deterministic SQL guards** (`chatbot_backend/backend/tools/sql_guards.py`)
Checks that run before a query executes:

- filtering on a value the column does not contain (the silent killer — valid
  SQL, zero rows, confident wrong answer)
- a wrong-case value, which is invisible on screen and matches nothing
- `SELECT DISTINCT` while listing records, which silently merges genuinely
  different rows
- `SUM` over a barely-populated column

A tripped guard feeds the real values back through the existing retry loop, so
a caught mistake costs one extra call instead of a wrong answer. Suspect values
are confirmed against the live database before anything is blocked, so a stale
cache can never refuse a correct query.

**View rebuild on reload** (`app/loading/scripts/load_all.py`)
`drop_transaction_tables()` uses `DROP TABLE ... CASCADE`, which takes every
dependent view with it. `create_semantic_views()` now runs at the end of
`reset_and_load()`, after the post-load steps. This had bitten three times.

**ABC rank surfaced**
`stock.rank` (A/B/C rarity) is documented and carried into the per-item views.
Note it is recorded per item **per branch** — 103 items carry different ranks at
different sites — so the views expose the rarest class the item holds anywhere
plus the per-branch detail, and "how many A items" is answered as
`COUNT(DISTINCT item_code)` with that reading stated in the answer.

## Fixes

- **Broken build**: `AuthContext.tsx` imported `@/lib/mockAuth`, deleted
  upstream two commits earlier. Dead code — `mockLogin` was never referenced.
  Vite could not resolve it and the dev server would not start.
- **Frozen row counts removed from the prompt.** They had already rotted: the
  prompt claimed 1,424 logistics orders (there were 0 at the time), ~260k
  issuance rows (245,094), 206 consignments (178). The *distinctions* those
  numbers taught are kept — stock rows are item-branch pairs, issuance rows are
  lines — because those describe the shape of the data and do not go stale.

## Verified

Against the current database, after a full load:

| check | result |
|---|---|
| ERP + chatbot backends import | pass |
| frontend build | 3,103 modules, clean |
| broken `@/` imports | 0 |
| semantic views | 9 present |
| branch alias resolution | 0 unresolved across 5 tables |
| data profile | 49 vocabularies |

Answers checked against raw SQL: exports on water **50**, imports in transit
**13**, trucking jobs **1,369**, QEN purchases **19,148**, A-rank items out of
stock **2**, hard coke available **230,475 kg** — all exact.

## Notes for review

- `chatbot_backend/` has its own venv and `.env`; see its README.
- The chatbot reads the same database read-only. It writes nothing.
- Nothing in the ERP's own request path changed except `app/main.py` including
  the proxy router.
