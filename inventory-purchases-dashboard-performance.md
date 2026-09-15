# Inventory & Purchases Dashboard Performance — Implementation Spec

## Hard constraint — read this first

**The database is live in production. No schema changes of any kind in this
spec** — no new columns, no new indexes, no `ALTER TABLE`, nothing that touches
`alembic` or `create_all`. Everything here is an **application-code-only**
change: how queries are shaped, how many round trips happen, and what runs
concurrently. If an idea in this doc would need a schema change to be fully
effective, it is noted as a **known limitation carried forward**, not solved
here — do not reach for an index as a workaround, and do not add one "just this
once."

---

## Goal

Two independent, unrelated fixes:

1. **Inventory** — `reorder_level_map()` currently loads the entire
   `store_requisition` table into Python and aggregates it by hand. Rewrite it
   as SQL aggregate queries instead. This is the largest win available and
   requires no schema change — it's a query-shape problem, not an index
   problem.
2. **Both dashboards** — collapse redundant round trips and run genuinely
   independent queries concurrently, the same pattern already used for the
   Overview dashboard (session-per-thread, `ThreadPoolExecutor`).

---

## Files involved

| File | Role |
|---|---|
| `app/dashboard/inventory/routes/inventory_dashboard.py` | Route. Calls 11 helper functions, mostly sequentially. |
| `app/dashboard/inventory/helpers.py` | All inventory dashboard queries, including `reorder_level_map`. |
| `app/dashboard/inventory/serializers.py` | Assembles the response dict from already-fetched data. No DB calls — not touched by this spec. |
| `app/dashboard/purchases/routes/purchases_dashboard.py` | Route. |
| `app/dashboard/purchases/helpers.py` | `option_lists`, `fetch_filtered_consignments`, `source_coverage`. |
| `app/database.py` | `SessionLocal` / engine, `pool_size=10, max_overflow=20`. Relevant to the concurrency work in Part 3. |

---

## Non-negotiables

- **No schema changes.** Said above, said again because it's the one rule most
  likely to be quietly violated by "just adding one index" once a query is
  slow even after the rewrite. If a rewritten query is still slow purely
  because of a missing index, that is an accepted, documented limitation for
  this pass — not something to route around by touching the schema anyway.
- **Every business rule encoded in the existing comments must survive.**
  Notably: `reorder_level_map`'s formula (`avg daily demand × lead time × (1 +
  safety factor)`), the demand-window definition (`DEMAND_WINDOW_DAYS = 180`,
  ending at the latest `prepare_date` in the data, not today), the lead-time
  fallback to `DEFAULT_LEAD_TIME_DAYS` when no completed cycle exists, and the
  "items with no requisition demand are absent, caller falls back to the
  stored `reorder_level` column" contract. A rewrite that changes any of these
  numbers for any (item, branch) pair is a bug, not a successful optimization.
- **Output shape is a contract** — `reorder_level_map` returns `{(item_code,
  branch): Decimal}`; the rewritten version must return the exact same shape,
  keys, and values (within `Decimal` precision) for the same input data.
- **Nothing here writes to the database.** Read-only throughout.

---

## Part 1 — Rewrite `reorder_level_map` as SQL aggregates

### Current implementation (`app/dashboard/inventory/helpers.py`)

```python
def reorder_level_map(db):
    latest = db.execute(select(func.max(StoreRequisition.prepare_date))).scalar()
    if latest is None:
        return {}

    window_start = latest - timedelta(days=DEMAND_WINDOW_DAYS)

    rows = db.execute(
        select(
            StoreRequisition.item_code, StoreRequisition.branch,
            StoreRequisition.prepare_date, StoreRequisition.stock_in_date,
            StoreRequisition.req_quantity,
        )
    ).all()  # <-- every row in the table, no WHERE clause at all

    demand, lead_sum, lead_count = {}, {}, {}
    for item_code, branch, prepare_date, stock_in_date, req_quantity in rows:
        key = (item_code, branch)
        if prepare_date and window_start <= prepare_date <= latest and req_quantity:
            demand[key] = demand.get(key, Decimal("0")) + req_quantity
        if prepare_date and stock_in_date and stock_in_date >= prepare_date:
            lead_sum[key] = lead_sum.get(key, 0) + (stock_in_date - prepare_date).days
            lead_count[key] = lead_count.get(key, 0) + 1

    window = Decimal(DEMAND_WINDOW_DAYS)
    default_lead = Decimal(DEFAULT_LEAD_TIME_DAYS)
    buffer_multiplier = Decimal("1") + SAFETY_FACTOR

    result = {}
    for key, total in demand.items():
        if total <= 0:
            continue
        avg_daily = total / window
        lead = (Decimal(lead_sum[key]) / Decimal(lead_count[key])) if lead_count.get(key) else default_lead
        result[key] = (avg_daily * lead * buffer_multiplier).quantize(Decimal("0.001"))

    return result
```

Two independent quantities are being computed by hand in Python:
1. **Demand** — sum of `req_quantity` per `(item_code, branch)`, restricted to
   rows where `prepare_date` falls in `[window_start, latest]`.
2. **Lead time** — average of `(stock_in_date - prepare_date).days` per
   `(item_code, branch)`, restricted to rows where both dates exist and
   `stock_in_date >= prepare_date` (a completed cycle) — **not** restricted to
   the demand window; any completed cycle counts, ever.

These have **different WHERE clauses**, so they need to be two separate
queries (do not try to force them into one `GROUP BY` with conditional
`FILTER`/`CASE` unless you've very carefully confirmed the two filters can
coexist in one row-scan without double-restricting either — see Edge Cases
below for why this is riskier than it looks).

### Target implementation

```python
def reorder_level_map(db):
    latest = db.execute(select(func.max(StoreRequisition.prepare_date))).scalar()
    if latest is None:
        return {}

    window_start = latest - timedelta(days=DEMAND_WINDOW_DAYS)

    # Demand: SUM(req_quantity), grouped by (item_code, branch), restricted to
    # the demand window. Mirrors consumption_map's pattern in this same file.
    demand_rows = db.execute(
        select(
            StoreRequisition.item_code,
            StoreRequisition.branch,
            func.sum(StoreRequisition.req_quantity),
        )
        .where(StoreRequisition.prepare_date.between(window_start, latest))
        .where(StoreRequisition.req_quantity.isnot(None))
        .group_by(StoreRequisition.item_code, StoreRequisition.branch)
    ).all()

    # Lead time: AVG(stock_in_date - prepare_date), grouped the same way,
    # restricted to completed cycles ONLY — no date-window restriction, by
    # design (see docstring: "average of stock_in_date - prepare_date, per
    # item"). Postgres can average a date subtraction (an integer number of
    # days) directly with func.avg — confirm the compiled SQL casts this the
    # way you expect (see Edge Cases).
    lead_rows = db.execute(
        select(
            StoreRequisition.item_code,
            StoreRequisition.branch,
            func.avg(StoreRequisition.stock_in_date - StoreRequisition.prepare_date),
            func.count(StoreRequisition.id),
        )
        .where(StoreRequisition.prepare_date.isnot(None))
        .where(StoreRequisition.stock_in_date.isnot(None))
        .where(StoreRequisition.stock_in_date >= StoreRequisition.prepare_date)
        .group_by(StoreRequisition.item_code, StoreRequisition.branch)
    ).all()

    demand = {(item_code, branch): total for item_code, branch, total in demand_rows if total}
    lead = {(item_code, branch): avg_days for item_code, branch, avg_days, count in lead_rows if count}

    window = Decimal(DEMAND_WINDOW_DAYS)
    default_lead = Decimal(DEFAULT_LEAD_TIME_DAYS)
    buffer_multiplier = Decimal("1") + SAFETY_FACTOR

    result = {}
    for key, total in demand.items():
        if total <= 0:
            continue
        avg_daily = Decimal(str(total)) / window
        lead_days = Decimal(str(lead[key])) if key in lead else default_lead
        result[key] = (avg_daily * lead_days * buffer_multiplier).quantize(Decimal("0.001"))

    return result
```

This keeps two round trips (down from one — but that one round trip was
transferring and Python-aggregating the *entire table*; two small `GROUP BY`
aggregate queries that only return as many rows as there are distinct
`(item_code, branch)` pairs is a large net win even without an index, because
the aggregation happens inside Postgres instead of after shipping every row
over the wire and looping in the app process).

### Edge cases — go through every one before considering this done

1. **`func.sum` / `func.avg` return type.** `req_quantity` is `Numeric(14, 3)`
   — `func.sum` over it returns a `Decimal` via the driver, same as today.
   Confirm this with a real query against a row that has a non-integer
   quantity; don't assume based on the column type alone.

2. **`stock_in_date - prepare_date` inside `func.avg`.** In Postgres, `date -
   date` yields an `integer` (days), so `AVG(integer)` yields a `numeric`
   (fractional days) — this is *not* automatically the same as the original
   Python code's `Decimal(lead_sum[key]) / Decimal(lead_count[key])`, which
   also produces a fractional average. **Compile and print the SQL**
   (`str(query.compile(compile_kwargs={"literal_binds": True}))`) and run it
   directly against a copy of production data (or a representative subset) to
   confirm the numeric average Postgres returns matches, to the precision that
   matters (`.quantize(Decimal("0.001"))` at the end), what the old Python loop
   produced for the same `(item_code, branch)` keys. If SQLAlchemy maps the
   date subtraction to something unexpected (e.g. an `interval` type instead
   of `integer` on some backend nuance), the `func.avg` will still produce a
   sensible number, but explicitly verify the type before trusting it.

3. **Filtered-out rows must match exactly.** The original loop's demand
   condition is `if prepare_date and window_start <= prepare_date <= latest
   and req_quantity:` — note `req_quantity` is checked for truthiness (so a
   `req_quantity` of `Decimal("0")` was **excluded** in the original code,
   same as `None`). The rewritten query's `.where(StoreRequisition.req_quantity.isnot(None))`
   does **not** exclude zero — only `NULL`. If any row can legitimately have
   `req_quantity == 0`, decide deliberately whether to add `.where(StoreRequisition.req_quantity != 0)`
   to match the original behavior exactly, or whether the original's
   truthiness check on `Decimal("0")` was actually an accidental side effect
   nobody intended. **Do not silently pick one — check the data for zero-quantity
   rows first, then match whichever behavior is correct, not whichever is convenient.**

4. **The lead-time query has no date-window restriction, by design** — re-read
   the original docstring: *"lead time = average of stock_in_date -
   prepare_date, per item; falls back to a default when no completed cycle
   exists."* This is deliberately **all-time**, not scoped to
   `DEMAND_WINDOW_DAYS`. Do not accidentally add a `prepare_date.between(...)`
   filter to the lead-time query to "be consistent" with the demand query —
   that would silently change the lead-time figure and is exactly the kind of
   quiet behavior change this spec's non-negotiables forbid.

5. **Keys present in `demand` but absent from `lead`, and vice versa.** The
   original code only computes `result[key]` for keys present in `demand`
   (the `for key, total in demand.items():` loop), and falls back to
   `default_lead` when `lead_count.get(key)` is falsy. The rewritten version
   must preserve this exactly: iterate `demand`, look up `lead` with a
   default, never iterate `lead` on its own (a key with lead-time data but no
   demand in the window must **not** appear in the result — same as today).

6. **`Decimal(str(total))` vs `Decimal(total)`.** The original code does
   `Decimal(str(total)) / window` for demand (the codebase's established
   convention for converting a DB-returned numeric into `Decimal` without
   float rounding artifacts) — the rewritten version does the same. Do **not**
   simplify this to `Decimal(total)` directly; check how the existing
   `consumption_map` function in this same file does it (`Decimal(str(total))
   / window`) and match that convention exactly, since it's already the
   established pattern for this exact situation two functions above.

7. **`quantize` at the very end only, not on intermediate values** — confirm
   the rewrite still quantizes only the final `result[key]`, not `avg_daily`
   or `lead_days` individually, to avoid compounding rounding differently than
   the original.

### Part 1 — testing / validation

1. Before changing anything, run the **current** `reorder_level_map(db)`
   against a snapshot of production-like data and dump the full result dict
   (`{(item_code, branch): Decimal(...)}`) to a file.
2. Implement the rewrite behind the same function name (or a new name with the
   old one temporarily kept alongside — same revert-safety approach as the
   Overview spec).
3. Run the rewrite against the same data snapshot, dump its result dict.
4. **Diff the two dicts key-by-key.** Every key must be present in both with
   the identical `Decimal` value (not just numerically equal after float
   conversion — compare `Decimal` to `Decimal`). Any mismatch is a bug in the
   rewrite, not an acceptable rounding difference — trace it back to one of
   the edge cases above.
5. Specifically construct or find test rows that exercise: a zero
   `req_quantity`, a `stock_in_date` equal to `prepare_date` (zero lead time,
   should count as a completed cycle per `>=`), an item with demand but no
   completed cycle (must fall back to `DEFAULT_LEAD_TIME_DAYS`), and an item
   with a completed cycle but zero demand in the window (must be **absent**
   from the result, not present with `avg_daily = 0`).
6. Only once the dicts match exactly across a real dataset, replace the old
   function's callers and remove the old implementation in a follow-up commit.

---

## Part 2 — Collapse the redundant "latest issuance date" queries

### Current state

Three functions in `app/dashboard/inventory/helpers.py` each independently run:

```python
latest = db.execute(select(func.max(Issuance.from_date))).scalar()
```

- `consumption_map(db)`
- `issuance_windows(db)`
- `issuance_totals_by_item(db, branch=None)`

All three are called from `inventory_dashboard` in the same request, so this
is the same scalar computed three times, three round trips, for a value that
cannot have changed between them within one request.

### Target

Compute it once in the route and pass it down as a parameter, rather than
having each function re-derive it:

```python
# In inventory_dashboard.py, before calling the three functions:
latest_issuance = latest_issuance_date(db)   # new tiny helper, one query

consumption = consumption_map(db, latest=latest_issuance)
...
issuance, windows = issuance_windows(db, latest=latest_issuance)
...
item_issuance = issuance_totals_by_item(db, branch, latest=latest_issuance)
```

Each of the three functions gets a new optional `latest=None` parameter; if
provided, skip the internal `SELECT max(...)` and use it directly; if not
provided (so any other caller of these functions elsewhere continues to work
unchanged), fall back to computing it internally exactly as today.

### Edge cases

1. **Check for other callers first.** Before adding the parameter, grep for
   every call site of `consumption_map`, `issuance_windows`, and
   `issuance_totals_by_item` across the codebase (not just
   `inventory_dashboard.py` — check the Overview dashboard's imports too,
   since `app/dashboard/whole/helpers.py` may reference inventory helpers
   indirectly). Any caller not updated to pass `latest` must keep working via
   the fallback — verify this explicitly, don't assume.
2. **`None` is a valid value for `latest`**, not just "not provided" — if
   `Issuance.from_date` is `NULL` for every row (empty table), `latest` is
   legitimately `None`, and each function already has an explicit `if latest
   is None: return {}` (or equivalent) branch. Make sure passing `latest=None`
   explicitly still triggers that early-return branch correctly, and isn't
   confused with the sentinel meaning "not provided, please compute it
   yourself." (Using a distinct sentinel like `_UNSET = object()` as the
   default instead of `None` is the safer way to disambiguate these two
   different meanings of "no value given" — consider that rather than
   overloading `None`.)
3. **This is a pure round-trip reduction, not a behavior change** — the value
   computed is identical either way; the only difference is how many times
   it's fetched. If the diff-testing in Part 1's style turns up any
   difference at all after this change, it means something about *when* the
   value is computed changed relative to another concurrent write — which
   shouldn't be possible in a read-only dashboard request, but is worth
   explicitly ruling out rather than assuming away.

---

## Part 3 — Run independent query groups concurrently

Same pattern as the Overview dashboard fix: open a private `SessionLocal()`
per worker thread, never share a session across threads, use
`ThreadPoolExecutor` + `as_completed`, preserve existing exception → 500
behavior exactly. **Do this only after Parts 1 and 2 are merged and verified**
— parallelizing a query that's still doing unnecessary work just means it
blocks its thread for longer instead of blocking the whole request; fix the
query shape first.

### Inventory — two independent groups

```
Group A (the stock-row pipeline, sequential internally — each step feeds the next):
    latest_issuance_date
      -> consumption_map
      -> reorder_level_map
      -> issuance_windows
      -> latest_purchase_map
      -> issuance_totals_by_item
      -> fetch_filtered_stock
      -> serialize_rows

Group B (fully independent of Group A and of each other):
    purchase_vs_issuance_by_category
    issuance_coverage
    issuance_in_period
    issuance_item_references
    option_lists
```

Group A must stay sequential internally (each function's output feeds the
next, and `serialize_rows` needs several of them together) — the
concurrency win here is running **all of Group A on one thread** while **all
of Group B's five calls run on a second thread** (or, if you want finer
granularity, each of Group B's five independent calls on its own thread — five
workers instead of two; either is valid, start with two and only go finer if
profiling shows Group B itself is now the bottleneck).

```python
def _run_with_own_session(fn, *args, **kwargs):
    db = SessionLocal()
    try:
        return fn(db, *args, **kwargs)
    finally:
        db.close()

def _build_stock_rows(branch, item, category, search):
    """Group A, run as one unit on one worker thread."""
    db = SessionLocal()
    try:
        latest = latest_issuance_date(db)
        consumption = consumption_map(db, latest=latest)
        reorder_levels = reorder_level_map(db)
        issuance, windows = issuance_windows(db, latest=latest)
        purchase_map = latest_purchase_map(db)
        item_issuance = issuance_totals_by_item(db, branch, latest=latest)
        stocks = fetch_filtered_stock(db, branch, item, category, search)
        rows = serialize_rows(stocks, consumption, reorder_levels, issuance,
                              purchase_map, windows["from_12m"])
        return rows, windows, purchase_map, item_issuance
    finally:
        db.close()
```

### Purchases — smaller, but still has independent pieces

```
Independent of each other:
    fetch_filtered_consignments
    source_coverage
    option_lists
```

`status` filtering happens in Python *after* `fetch_filtered_consignments`
returns, in the route — that stays sequential relative to the fetch (it can't
run before the fetch exists), but `source_coverage` and `option_lists` don't
depend on the fetch or on each other at all and can run on their own threads
concurrently with it.

### Edge cases (same category as the Overview spec — go through all of these again for this module specifically, do not assume they transfer automatically)

1. **Never share a session across threads.** Same rule as before — every
   worker opens and closes its own `SessionLocal()`.
2. **Exception behavior must be unchanged.** An error in any thread must still
   produce the same 500 response the sequential version produces today — call
   `.result()` on every future, don't swallow exceptions to degrade
   gracefully unless that's an explicit, separately-approved product decision.
3. **Connection pool headroom.** Inventory's route would now briefly hold up
   to 3 connections (route's own + Group A worker + Group B worker, or more if
   Group B is split finer); purchases up to 4 (route's own + 3 independent
   calls). At `pool_size=10, max_overflow=20`, this is comfortable at this
   app's scale, but re-verify under a small concurrent-load test rather than
   assuming, same as the Overview spec required.
4. **`option_lists` (inventory and purchases both) issues several small
   `DISTINCT` queries internally already** — when parallelized alongside
   other groups, confirm none of those internal `DISTINCT` calls are
   accidentally issued against the wrong session if you refactor
   `option_lists` itself in the process. Keep this function's internals
   untouched in this pass; only change *which thread calls it*, not what it
   does internally.
5. **`serialize_rows` (inventory) must run inside Group A's own thread**, not
   after rejoining on the main thread — it needs the ORM-loaded `stocks`
   objects (from `fetch_filtered_stock`) to still be attached to a live
   session if it lazy-loads anything off them (e.g. `Stock.item`). Check
   whether `serialize_rows` accesses any relationship not already
   eager-loaded by `fetch_filtered_stock`'s `joinedload(Stock.item)` — if it
   does, that access must happen before the Group A session closes, i.e.
   inside `_build_stock_rows`, exactly as sketched above. Don't return raw
   `stocks` ORM objects out of the thread and try to serialize them on the
   main thread after the worker's session has already closed.
6. **Test with a deliberately slow group** (temporary `time.sleep(1)` in one
   branch locally) to confirm real concurrency is happening, same
   verification method as the Overview spec.

### Part 3 — testing / validation

1. Before/after JSON-diff on both `/inventory` and `/purchases`, across a
   handful of representative filter combinations (some with `branch`/`item`
   filters active, at least one with `status`/`reorder_status`/`movement`
   filters active on inventory, at least one with `search` active on both).
2. Wall-clock latency measured before and after, under both single-request and
   small-concurrent-load conditions.
3. Connection pool usage watched during the concurrent-load test.
4. Deliberate error injection in one thread group, confirm the route still
   returns the same 500 behavior as before this change.

---

## Known limitation carried forward (not solved in this spec)

`PurchasesData.po_date` and `StoreRequisition`'s filter/join columns have no
index. Part 1 and Part 3's query-shape improvements reduce how much data is
moved and how many round trips happen, but a query that filters on `po_date`
or `store_requisition`'s columns will still involve a sequential scan at the
database level — no application-code change can fully fix that. This is
explicitly out of scope here because of the no-schema-changes constraint; note
it as a candidate for the next planned maintenance window, but do not work
around it with an application-level index-like structure (e.g. hand-rolling a
cache table) as part of this spec — that's a schema change in spirit even if
not in name, and should go through the same review a real migration would.

---

## Definition of done

- [ ] Part 1: `reorder_level_map` rewritten as two SQL `GROUP BY` aggregate
      queries; old implementation kept alongside until verified, then removed.
- [ ] Part 1: dict-diff verified identical against a real data snapshot,
      including the specific edge-case rows called out above (zero quantity,
      zero lead time, demand-without-completed-cycle,
      completed-cycle-without-demand).
- [ ] Part 2: `latest_issuance_date` computed once per request, passed into
      `consumption_map`, `issuance_windows`, `issuance_totals_by_item`; all
      other call sites of these three functions verified still work via the
      fallback.
- [ ] Part 3: inventory's Group A / Group B running concurrently, each with
      its own session; deliberate-slow-group test confirms real concurrency.
- [ ] Part 3: purchases' three independent calls running concurrently, same
      verification.
- [ ] Both dashboards: exception-in-one-group still produces the same 500
      behavior as before.
- [ ] Both dashboards: JSON-diff verified identical, pre- vs. post-change,
      across representative filter combinations.
- [ ] No schema changes anywhere in the diff — confirm with `git diff` against
      `alembic/` and every `models.py`/`stores_schemas.py` before merging.
