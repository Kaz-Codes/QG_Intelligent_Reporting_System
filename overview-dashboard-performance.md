# Overview Dashboard Performance — Implementation Spec

## Goal

The `/overview` endpoint (`app/dashboard/whole/routes/overview_dashboard.py`) is slow
because `serialize_overview` runs ~57 separate, sequential `db.execute()` calls across
`app/dashboard/whole/helpers.py` (36 calls) and `app/dashboard/whole/references.py`
(21 calls) before returning. Total latency today is roughly the **sum** of every
query's round-trip time.

Two independent levers, to be implemented **in this order**:

1. **Lever 1 — consolidate same-scope queries** inside each section, so fewer round
   trips happen per section. Pure SQL change, no concurrency.
2. **Lever 2 — run the four sections concurrently** on separate DB sessions, so total
   latency becomes roughly the slowest section instead of the sum of all four.

Do **not** start Lever 2 until Lever 1 is merged, measured, and verified correct.
They are independent and separately revertible; mixing them in one change makes it
hard to tell which one caused a regression if something breaks.

---

## Files involved

| File | Role |
|---|---|
| `app/dashboard/whole/routes/overview_dashboard.py` | The route. Calls `serialize_overview`. |
| `app/dashboard/whole/serializers.py` | Four section builders — `serialize_imports`, `serialize_procurement`, `serialize_logistics`, `serialize_stores` — plus `serialize_overview`, which calls all four sequentially on one shared `db` session. |
| `app/dashboard/whole/helpers.py` | ~36 query functions, grouped by section (imports, procurement, logistics, stores) under clearly labeled comment blocks. |
| `app/dashboard/whole/references.py` | ~21 bounded `LIMIT` queries backing each section's `references` block (drill-down lists). Called from inside each `serialize_*` function — Lever 2 parallelizes these automatically as a side effect of parallelizing the section functions. |
| `app/dashboard/whole/calculations.py` | Pure Python — no DB calls (verified: `grep db.execute app/dashboard/whole/calculations.py` returns nothing). Not touched by either lever. |
| `app/database.py` | `SessionLocal` / engine. Pool: `pool_size=10, max_overflow=20` (30 max connections). Relevant to Lever 2's connection budget. |

**Verified before writing this spec:** `app/dashboard/whole/helpers.py`'s functions
are imported nowhere outside `app/dashboard/whole/` (`grep -rn "from app.dashboard.whole.helpers import\|dashboard.whole.helpers" app` outside that directory returns nothing).
Safe to add/change function signatures in this file without touching other dashboards.
**Re-verify this yourself before editing** in case it's changed since this spec was written.

---

## Non-negotiables (read before touching anything)

- **Every business rule encoded in the existing comments must survive.** This
  codebase's dashboard helpers carry hard-won domain rules in their docstrings —
  e.g. `imports_period_value`'s header-dating-not-line-dating reversal (so the
  Overview's imports value agrees with the Imports module's own hero number),
  `imports_value_undated`'s definition of "reachable by no window", the
  shaft-matching-by-item-name convention, the "stores has no date column, it's a
  snapshot" framing. **Do not silently change what a number means while
  optimizing how it's fetched.** If a consolidation would change a result (even
  a boundary case), stop and flag it — don't guess which behavior is "more
  correct."
- **Output shape is a contract.** The dict keys returned by each `serialize_*`
  function are consumed by the frontend. Lever 1 and Lever 2 must both produce
  **byte-identical JSON** for the same request, before and after.
- **`Numeric`/`Decimal` precision must not change.** Don't let a consolidated
  query introduce float casts or change rounding on money/weight columns.
- **Nothing here should start writing to the database.** These are all read
  endpoints; if a "consolidation" ever seems to require a mutation (e.g. a temp
  table), stop — that's the wrong approach for this codebase's philosophy of
  keeping dashboards read-only.

---

## Lever 1 — Consolidate same-scope queries

### Where the duplication is

Several functions in `app/dashboard/whole/helpers.py` filter on the exact same
base predicate and only differ in what they aggregate:

**Imports section** — all of these filter on `_imports_scope(shafts_only)`:
- `imports_period_value` (2 queries: header aggregate + line count)
- `imports_value_undated` (1 query, same scope + `NOT IN (dated_ids)`)
- `imports_date_coverage` (1 query, same scope)
- `imports_in_process_by_stage` (1 query, same scope + `GROUP BY current_status`)
- `imports_shaft_counts` (independent shaft-matching subquery — see note below)

**Procurement section** — scan the same PO-level scope:
- `procurement_period_totals`, `procurement_delay`, `procurement_category_totals`,
  `procurement_cycle_times`

**Logistics section** — scan overlapping trucking/shipment scopes:
- `shipments_handled`, `trucking_cost_by_movement`, `trucking_date_coverage`

### Approach: `FILTER`, not more Python-side joins

Postgres supports `FILTER (WHERE ...)` on aggregate functions, letting one query
compute several differently-scoped aggregates over one scan. SQLAlchemy exposes
this as `.filter()` on a `func.*` construct (not to be confused with `Query.filter`):

```python
func.count(Consignment.id).filter(some_boolean_clause)
```

### Step 1: Consolidate the imports section (do this one first — it's the model for the rest)

Write a **new** function `imports_overview_metrics(db, date_from, date_to,
date_field=None, shafts_only=False)` in `app/dashboard/whole/helpers.py` that
replaces the *combinable* parts of `imports_period_value`,
`imports_value_undated`, and `imports_date_coverage`:

```python
def imports_overview_metrics(db, date_from, date_to, date_field=None, shafts_only=False):
    """One-query version of imports_period_value + imports_value_undated +
    imports_date_coverage. Same scope (_imports_scope), different FILTERed
    aggregates instead of three separate round trips.

    Returns a dict, not a tuple — positional tuples get confusing past 4-5
    fields and this replaces three functions' worth of return values.
    """
    scope = _imports_scope(shafts_only)
    window = and_(*[_imports_window_membership(date_field, date_from, date_to)])
    dated_col = imports_date_column(date_field)
    undated_ids = ~Consignment.id.in_(_imports_dated_ids(date_field))

    row = db.execute(
        select(
            func.coalesce(func.sum(CONSIGNMENT_VALUE).filter(window), 0),
            func.count(Consignment.id).filter(window),
            func.count(Consignment.batch_group_id.distinct()).filter(window),
            func.count(Consignment.id).filter(undated_ids),
            func.coalesce(func.sum(CONSIGNMENT_VALUE).filter(undated_ids), 0),
            func.count(dated_col),
            func.count(Consignment.id),
        )
        .where(*scope)
    ).one()

    return {
        "period_value": row[0], "period_consignments": row[1], "period_orders": row[2],
        "undated_rows": row[3], "undated_value": row[4],
        "dated": row[5], "all_live": row[6],
    }
```

- **`lines` (line count) does NOT fold in here.** It needs a join to
  `ConsignmentItem`, which changes the `FROM`/row multiplication of the whole
  query — keep it as `imports_period_value`'s existing second query (the join
  count), or give it its own tiny function. Don't try to force it into the
  `FILTER` pattern; that's how a `FILTER` count silently turns into a row-multiplied
  count and produces a wrong number nobody notices until someone cross-checks it
  against the Imports module screen.
- **`imports_in_process_by_stage` stays separate.** It's a `GROUP BY
  current_status`, structurally different from a flat aggregate row — don't
  contort it into more `FILTER` clauses per stage unless you've confirmed the
  stage grouping (`STAGE_GROUPS`) is static enough to hardcode into SQL. Safer
  to leave as its own single query; it was already only 1 round trip.
- **`imports_shaft_counts` stays separate too.** It re-derives its own shaft
  subquery independent of the `shafts_only` param on the outer scope (it counts
  shaft items *within whatever scope*, which is a different question from "is
  this whole section restricted to shafts"). Don't merge it into the general
  scope query — the predicate isn't the same thing, just superficially similar.

**Edge cases to verify with real data before replacing the call sites:**
- `undated_ids` and `window` must be **mutually exclusive** in the data (a
  consignment counted in `period_value` should never also count as `undated`) —
  confirm this holds; if a row can somehow satisfy both (it shouldn't, by
  definition, but verify), the two `FILTER`s just both apply independently, which
  is fine — they're not `CASE`/mutually-exclusive by construction, each `FILTER`
  is evaluated independently per row.
- `func.count(Consignment.batch_group_id.distinct()).filter(window)` — confirm
  SQLAlchemy renders this as `count(DISTINCT batch_group_id) FILTER (WHERE ...)`
  and not `count(DISTINCT (batch_group_id) FILTER (...))` or similar malformed
  SQL. **Print the compiled SQL (`str(query.compile(compile_kwargs={"literal_binds": True}))`)
  and eyeball it** before trusting the result.
- `shafts_only=True` changes `_imports_scope` itself (adds the shaft-id filter to
  the base scope) — confirm the consolidated query still respects that when
  `shafts_only=True`, since `scope` is applied via `.where(*scope)` same as before.

### Step 2: Update the one call site

In `app/dashboard/whole/serializers.py`, `serialize_imports` currently does:

```python
total, rows, orders, lines = helpers.imports_period_value(db, date_from, date_to, date_field, shafts_only)
undated_rows, undated_value = helpers.imports_value_undated(db, date_field, shafts_only)
...
dated, all_live = helpers.imports_date_coverage(db, date_field, shafts_only)
```

Replace with:

```python
metrics = helpers.imports_overview_metrics(db, date_from, date_to, date_field, shafts_only)
_, _, lines = helpers.imports_period_value_lines_only(db, date_from, date_to, date_field, shafts_only)  # or whatever you name the surviving line-count function
total, rows, orders = metrics["period_value"], metrics["period_consignments"], metrics["period_orders"]
undated_rows, undated_value = metrics["undated_rows"], metrics["undated_value"]
dated, all_live = metrics["dated"], metrics["all_live"]
```

**Do not delete the old `imports_period_value` / `imports_value_undated` /
`imports_date_coverage` functions in the same change.** Leave them in place
(even if now unused by `serialize_imports`), run the test/diff comparison below,
and only remove them once the consolidated version is verified byte-identical in
production-like data. This keeps the revert trivial (swap the call site back) if
something's off.

### Step 3: Repeat the same pattern for procurement and logistics

Same recipe: identify the functions sharing one scope, write one new
`*_overview_metrics` function using `FILTER`, leave old functions in place, swap
one call site, verify, then clean up. Do procurement and logistics as **separate
commits**, each independently verifiable — don't batch all three sections into
one giant diff.

### Lever 1 — testing / validation

1. Pick 5–8 representative query-param combinations for `/overview` (different
   date ranges, `shafts_only=true/false`, at least one empty-period case, at
   least one case spanning a month boundary).
2. Before any change: hit the live endpoint (or call `serialize_overview`
   directly in a script) for each combination, save the JSON response.
3. After each section's consolidation: re-run the same combinations, diff
   against the saved JSON. **Any difference is a bug**, not an "acceptable
   rounding difference" — money/weight fields are `Numeric`, and this is a
   pure refactor, not a semantics change.
4. If this codebase's existing integration script (referenced in
   `CLAUDE.md` as checking live dashboard consistency) covers the Overview page,
   run it too.
5. Only after all combinations match exactly, remove the now-unused old helper
   functions in a follow-up cleanup commit.

---

## Lever 2 — Run the four sections concurrently

### Precondition

Lever 1 is merged and verified. Measure the Overview's response time again
before starting Lever 2, so you have a real "before" number for this lever
specifically.

### What's independent

`serialize_overview` (bottom of `app/dashboard/whole/serializers.py`) calls four
functions, each self-contained and reading only its own tables:

```python
def serialize_overview(db, sections, dead_stock_days, shafts_only=False):
    imports = sections["imports"]
    procurement = sections["procurement"]
    logistics = sections["logistics"]
    stores = sections.get("stores", {})

    return {
        "imports": serialize_imports(db, imports["from"], imports["to"], imports["field"], imports["kind"], shafts_only),
        "procurement": serialize_procurement(db, procurement["from"], procurement["to"], procurement["field"], procurement["kind"]),
        "logistics": serialize_logistics(db, logistics["from"], logistics["to"], logistics["field"], logistics["kind"]),
        "stores": serialize_stores(db, dead_stock_days, stores.get("from"), stores.get("to")),
    }
```

Each `serialize_*` function already returns a **plain dict of primitives/lists**
(confirmed by reading them — no raw ORM objects escape these functions). This
matters: it means results can safely cross a thread boundary and be used after
the worker's session is closed, with no lazy-load-after-close errors.

### The one hard rule: never share a `Session` across threads

SQLAlchemy's `Session` is not thread-safe. Each concurrent worker **must** open
its own `SessionLocal()` and close it when done — never pass the route's `db`
into a worker thread.

### Implementation

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.database import SessionLocal

def _run_with_own_session(fn, *args, **kwargs):
    """Open a private session for one section, run it, close it.

    Never share a session across threads — SQLAlchemy Session is not
    thread-safe, and this is the one rule this function exists to enforce.
    """
    db = SessionLocal()
    try:
        return fn(db, *args, **kwargs)
    finally:
        db.close()


def serialize_overview(db, sections, dead_stock_days, shafts_only=False):
    """`db` (the route's own session) is now UNUSED by the four sections below
    — each opens its own session via _run_with_own_session. Kept as a
    parameter so the route doesn't need to change, and in case a future
    caller needs a pre-flight check on the shared session before fanning out.
    """
    imports = sections["imports"]
    procurement = sections["procurement"]
    logistics = sections["logistics"]
    stores = sections.get("stores", {})

    jobs = {
        "imports": (serialize_imports, (imports["from"], imports["to"], imports["field"], imports["kind"], shafts_only), {}),
        "procurement": (serialize_procurement, (procurement["from"], procurement["to"], procurement["field"], procurement["kind"]), {}),
        "logistics": (serialize_logistics, (logistics["from"], logistics["to"], logistics["field"], logistics["kind"]), {}),
        "stores": (serialize_stores, (dead_stock_days, stores.get("from"), stores.get("to")), {}),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_run_with_own_session, fn, *args, **kwargs): name
            for name, (fn, args, kwargs) in jobs.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            # .result() re-raises whatever the worker raised, in THIS thread —
            # the route's existing `except Exception` still catches it and
            # still does db.rollback() / returns 500, unchanged behavior.
            results[name] = future.result()

    # Preserve original key order for anything downstream that might rely on
    # dict ordering (unlikely, but free to keep).
    return {k: results[k] for k in ("imports", "procurement", "logistics", "stores")}
```

### Edge cases — go through every one of these before calling this done

1. **Exception in one section must still fail the whole request the same way
   it does today.** Today, an exception anywhere in the sequential chain
   propagates up to the route's `except Exception` → `db.rollback()` → 500.
   `future.result()` re-raises inside the main thread when iterated, so this
   is preserved automatically — **but only if you call `.result()` on every
   future**, including ones that finished without error. Don't wrap individual
   `.result()` calls in their own try/except that swallows errors to "degrade
   gracefully" — that's a behavior change nobody asked for. If partial-failure
   degradation (show 3 sections, mark the 4th as unavailable) is ever wanted,
   that's a deliberate product decision to raise with whoever owns this
   feature — not something to sneak in as a side effect of parallelizing.

2. **A worker's session must always close, even on exception.** The `finally:
   db.close()` in `_run_with_own_session` handles this — verify it actually
   runs (it will; `finally` always runs) and that no exception during
   `fn(db, ...)` leaves a connection checked out of the pool.

3. **Connection pool headroom.** One `/overview` request now holds up to 5
   connections briefly (the route's own, unused-but-open `db` + 4 workers)
   instead of 1. At `pool_size=10, max_overflow=20` (30 max), this comfortably
   supports several concurrent Overview loads, but it's worth actually watching
   pool usage under real traffic after this ships — if the route's own `db`
   session truly goes unused by the parallel path, consider not opening it at
   all in the route for this endpoint, to give back that one connection. Don't
   pre-optimize this without checking whether `db` is used for anything else in
   `overview_dashboard.py` first (e.g. `authorize()` uses it).

4. **`ThreadPoolExecutor(max_workers=4)` is created per-request here.**
   Spinning up 4 OS threads per request is cheap but not free. If profiling
   later shows thread-creation overhead matters (unlikely at this app's ~10-30
   user scale), consider a module-level, reused executor — but don't add that
   complexity preemptively; measure first.

5. **No `asyncio` involved, no conflict with FastAPI's own threading.** This
   route is a plain `def` (sync), which Starlette already runs in its own
   worker thread. The `ThreadPoolExecutor` here spawns independent OS threads
   for the 4 sections — this does not touch or depend on Starlette's internal
   thread pool or an event loop. Confirm the route stays a sync `def` (not
   converted to `async def`) — mixing sync ThreadPoolExecutor.result() blocking
   calls inside an `async def` route would block the event loop and defeat the
   purpose.

6. **Verify no section's `serialize_*` function mutates shared state** outside
   its own session — e.g. a module-level cache, a global counter, or anything
   written to `db` (there shouldn't be any writes on a read-only dashboard, but
   grep for `.add(`, `.commit()`, `.flush()` inside `serialize_imports`,
   `serialize_procurement`, `serialize_logistics`, `serialize_stores` and
   everything they call, to be certain).

7. **`references.py` calls inside each section are now running on that
   section's own worker session** — confirm none of those reference-list
   queries were relying on some earlier query's result being visible in the
   *same* transaction in a way that matters (they're all independent reads, so
   this should be a non-issue, but check `refs.imports_value_references` etc.
   don't take a `db` from a different scope than the one passed in).

8. **Test with a deliberately slow section** (e.g. temporarily add
   `time.sleep(1)` inside one `serialize_*` in a local branch) to confirm the
   other three genuinely don't wait on it — i.e. confirm real concurrency is
   happening, not just four sequential calls dressed up in a `ThreadPoolExecutor`
   that isn't actually achieving parallelism (a common mistake if, say, all four
   somehow ended up sharing one session or one connection under the hood).

### Lever 2 — testing / validation

1. Repeat the same before/after JSON-diff process as Lever 1, on the same
   representative query-param combinations — output must still be byte-identical.
2. Measure wall-clock latency for `/overview` before and after, ideally under
   something closer to real concurrent load (2-3 simultaneous requests), not
   just one request at a time.
3. Watch the DB connection pool (`pool_size`/`max_overflow` usage) during that
   load test — confirm it doesn't approach exhaustion (30 connections) under
   realistic concurrent Overview traffic for this app's actual user count
   (~10-30 users).
4. Deliberately trigger an error in one section locally (e.g. temporarily break
   a query) and confirm the route still returns a 500 with the existing error
   handling — not a partial 200 with a missing section, unless that's been
   explicitly decided as desired behavior.

---

## Definition of done

- [ ] Lever 1: imports section consolidated, old functions still present but
      unused, JSON-diff verified across all test combinations.
- [ ] Lever 1: procurement section consolidated, same verification.
- [ ] Lever 1: logistics section consolidated, same verification.
- [ ] Lever 1: unused old helper functions removed in a follow-up cleanup
      commit, once all three sections are verified stable.
- [ ] Lever 1: measured `/overview` latency before vs. after, recorded
      somewhere (commit message, PR description, or a comment).
- [ ] Lever 2: `serialize_overview` fans out to 4 threads, each with its own
      `SessionLocal()`, verified via the deliberate-slow-section test that real
      concurrency is happening.
- [ ] Lever 2: exception-in-one-section still produces the same 500 behavior
      as before.
- [ ] Lever 2: JSON-diff verified identical to pre-Lever-2 output.
- [ ] Lever 2: connection pool usage checked under a small concurrent-load test.
- [ ] Both levers: no change to any business-rule comment's underlying meaning
      — if a consolidation would've changed what a number means, it was
      flagged and resolved with a human, not silently decided.
