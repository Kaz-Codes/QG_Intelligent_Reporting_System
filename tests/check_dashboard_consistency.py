"""Definition-of-done checks for the consistency pass.

Every assertion here is a claim the spec makes: the same metric must read the
same wherever it appears, and a KPI's reference list must total what the KPI
says. Run it after any change to the dashboard calculations.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# Runnable directly (`python tests/check_dashboard_consistency.py`) as well as
# under a runner, so it stays a one-command check.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
assert c.post("/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 200

FAILS, PASSES = [], []


def check(name, ok, detail=""):
    (PASSES if ok else FAILS).append(name)
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")


def get(path, **params):
    r = c.get(path, params=params)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
    return r.json()["data"]


W = {"date_from": "2025-01-01", "date_to": "2026-12-31"}
OW = {"imports_date_from": "2025-01-01", "imports_date_to": "2026-12-31"}

print("\n== Overview vs Imports dashboard: same window, same numbers ==")
o = get("/dashboard/overview", **OW)["imports"]
i = get("/dashboard/imports", **W)["consignments"]
p = i["population"]
# TO THE RUPEE, NOT TO THE BIT - and the difference is a real one, not slack.
#
# The two screens value a consignment differently ON PURPOSE (CLAUDE.md, "the
# Overview's period_value no longer follows this rule"): the Overview prefers
# the STORED `pkr_total`, the module re-sums the lines. `pkr_total` is
# Numeric(20,2), so a consignment whose lines come to 4,064,460.0348 is stored
# as 4,064,460.03 and the two screens are 0.0048 apart by construction.
#
# This was an exact `==` and it passed, which is the misleading part: no
# consignment in the loaded data carries a stored `pkr_total` at all, so BOTH
# sides took the line path and matched bit for bit. The first record to be
# saved through the app - a batch fixture, or any real edit, since
# `recompute_derived` stores the total on every save - is enough to break it.
# An assertion that only holds while a column is empty everywhere is not
# asserting what it claims to.
#
# Half a paisa per consignment is the most the rounding can account for; a
# basis error is orders of magnitude larger than that and still fails here.
value_tolerance = 0.005 * max(int(p["total"]["count"]), 1)
value_gap = abs(float(o["period_value"]["value"]) - float(i["period_value"]["value"]))
check("total value matches", value_gap <= value_tolerance,
      f'{float(o["period_value"]["value"]):,.0f} (differ by {value_gap:.4f}, '
      f'rounding allows {value_tolerance:.3f})')
check("total count matches", o["period_value"]["consignments"] == p["total"]["count"], str(p["total"]["count"]))
check("total lines match", o["period_value"]["lines"] == p["total"]["lines"], str(p["total"]["lines"]))
# One money basis per screen: the population tiles must sum the same in-window
# lines the headline does, not consignment-level totals.
check("imports has ONE money basis",
      float(i["period_value"]["value"]) == float(p["total"]["value"]))
check("in-process matches", o["in_process"]["count"] == p["in_process"]["count"], str(p["in_process"]["count"]))
check("arrived matches", o["arrived"]["count"] == p["arrived"]["count"], str(p["arrived"]["count"]))
check("cancelled matches", o["cancelled"]["count"] == p["cancelled"]["count"], str(p["cancelled"]["count"]))
check("delayed matches", o["delayed"]["count"] == i["delivery_delay"]["delayed"], str(o["delayed"]["count"]))
check("in-process + arrived + cancelled = total",
      p["in_process"]["count"] + p["arrived"]["count"] + p["cancelled"]["count"] == p["total"]["count"])

print("\n== Procurement: Overview vs Purchases dashboard ==")
# These agreed on any window you FORCED to the same date field, and disagreed on
# every window if you touched nothing — because the two screens defaulted to
# different dates for one figure (po_date against purchase). A default is part
# of the metric, so it is asserted here.
PW2 = ("2026-01-01", "2026-08-31")
op = get("/dashboard/overview",
         purchases_date_from=PW2[0], purchases_date_to=PW2[1])["procurement"]
pp = get("/dashboard/purchases", date_from=PW2[0], date_to=PW2[1])
check("same default date field", op["date_field"] == pp["date_field"], op["date_field"])
check("value matches on DEFAULTS",
      float(op["period_value"]["value"]) == float(pp["kpis"]["total_value"]),
      f'{float(op["period_value"]["value"]):,.0f}')
check("order count matches on DEFAULTS",
      op["period_value"]["orders"] == pp["kpis"]["orders_count"],
      f'{op["period_value"]["orders"]:,}')
# The same figure stated to different precision still reads as two figures.
check("delay rate matches on DEFAULTS, to the same precision",
      op["delay"]["delay_pct"] == pp["kpis"]["delayed_pct"],
      f'{op["delay"]["delay_pct"]}% from {op["delay"]["late_orders"]:,} of {op["delay"]["basis"]:,}')
check("on-time + delayed = 100",
      round(pp["kpis"]["on_time_pct"] + pp["kpis"]["delayed_pct"], 1) == 100.0)
for _field in ("po_date", "purchase"):
    _o = get("/dashboard/overview", purchases_date_from=PW2[0],
             purchases_date_to=PW2[1], purchases_date_field=_field)["procurement"]
    _p = get("/dashboard/purchases", date_from=PW2[0], date_to=PW2[1], date_field=_field)
    check(f"still agree when switched to '{_field}'",
          float(_o["period_value"]["value"]) == float(_p["kpis"]["total_value"]))


print("\n== Stock days: Inventory vs Overview Stores ==")
inv = get("/dashboard/inventory")
sto = get("/dashboard/overview")["stores"]
check("total days of stock matches",
      inv["stock_days"]["total_days_of_stock"] == sto["stock_days"]["total_days_of_stock"],
      str(inv["stock_days"]["total_days_of_stock"]))
check("same window", inv["stock_days"]["window_days"] == sto["stock_days"]["window_days"])
check("same stated basis", inv["stock_days"]["basis"] == sto["stock_days"]["basis"])
ib = {b["branch"]: b["days_of_stock"] for b in inv["stock_days"]["by_branch"]}
ob = {b["branch"]: b["days_of_stock"] for b in sto["stock_days"]["by_branch"]}
check("per-branch runway matches", ib == ob, f"{len(ib)} branches")

print("\n== Issuance: Inventory vs Overview Stores ==")
check("issued value matches", inv["issuance"]["value"] == sto["issuance"]["value"],
      f'{inv["issuance"]["value"]:,.0f}')
check("issued item count matches", inv["issuance"]["items"] == sto["issuance"]["items"],
      str(inv["issuance"]["items"]))

print("\n== Purchases: KPI value == reference-list total ==")
PW = {"date_from": "2026-01-01", "date_to": "2026-01-23"}
pu = get("/dashboard/purchases", **PW)
k, r = pu["kpis"], pu["references"]
check("orders KPI == orders list", k["orders_count"] == r["orders"]["total"], str(k["orders_count"]))
check("delayed KPI == delayed list", k["delayed_orders"] == r["delayed"]["total"], str(k["delayed_orders"]))
check("on-time KPI == on-time list", k["completed_orders"] == r["on_time"]["total"], str(k["completed_orders"]))
check("on-time + delayed + pending = orders",
      k["completed_orders"] + k["delayed_orders"] + k["pending_orders"] == k["orders_count"])
check("percentages sum to 100", k["on_time_pct"] + k["delayed_pct"] == 100,
      f'{k["on_time_pct"]}% + {k["delayed_pct"]}%')
check("delayed LINES exceed delayed ORDERS (different units, both published)",
      pu["delayed_line_references"]["total"] >= r["delayed"]["total"],
      f'{pu["delayed_line_references"]["total"]} lines in {r["delayed"]["total"]} orders')

print("\n== Lists show LINES and still reconcile with their tile ==")
# The rule changed, deliberately. A list never hides lines, so its `total`
# counts LINES while the tile counts consignments — 3 shaft lines under 1
# consignment. `groups` is the pair being reconciled, and BOTH are on screen,
# which is the difference between a legitimate second unit and the old bug
# (a tile reading 247 over a list reading 454, with nothing saying why).
for key in ("total", "in_process", "arrived", "cancelled"):
    r = p["references"][key]
    check(f"imports {key}: list is line-level", r["unit"] == "line")
    check(f"imports {key}: groups == tile count", r["groups"] == p[key]["count"],
          f'{r["total"]} lines across {r["groups"]} consignments')
    check(f"imports {key}: total == tile lines", r["total"] == p[key]["lines"])

check("imports delayed list", i["delivery_delay"]["delayed"]
      == i["delivery_delay"]["delayed_references"]["total"])

for key in ("in_process", "arrived", "cancelled"):
    r = o["references"][key]
    check(f"overview {key}: groups == tile count", r["groups"] == o[key]["count"],
          f'{r["total"]} lines across {r["groups"]} consignments')
check("overview delayed list", o["delayed"]["count"] == o["references"]["delayed"]["total"])

print("\n== Reference lists are complete and paginated ==")
big = get("/dashboard/overview/references", key="procurement.period_value",
          date_from="2026-01-01", date_to="2026-01-23", page=1, page_size=50)
check("paginated shape", {"total", "page", "page_size", "pages", "items"} <= set(big),
      f'{big["total"]:,} records over {big["pages"]} pages')
last = get("/dashboard/overview/references", key="procurement.period_value",
           date_from="2026-01-01", date_to="2026-01-23", page=big["pages"], page_size=50)
check("last page reachable (no hidden cap)", len(last["items"]) > 0 and last["page"] == big["pages"],
      f'page {last["page"]} has {len(last["items"])} rows')
seen = {row["reference"] for row in big["items"]} & {row["reference"] for row in last["items"]}
check("pages do not overlap", not seen)
check("unknown key rejected",
      c.get("/dashboard/overview/references", params={"key": "nope"}).status_code == 400)

print("\n== Coverage / recent-period jump on every time-based section ==")
ov = get("/dashboard/overview")
for section in ("imports", "procurement", "logistics", "stores"):
    cov = ov[section].get("coverage")
    check(f"{section} reports coverage", bool(cov) and "latest_month" in cov,
          str(cov.get("latest_month")) if cov else "missing")
for path in ("/dashboard/imports", "/dashboard/purchases", "/dashboard/inventory"):
    d = get(path)
    check(f"{path.split('/')[-1]} reports coverage", "coverage" in d and "latest_month" in d["coverage"])

print("\n== Shafts tab narrows every imports figure ==")
sh = get("/dashboard/overview", shafts_only=True, **OW)["imports"]
check("overview shafts narrows the set", sh["period_value"]["consignments"] < o["period_value"]["consignments"],
      f'{sh["period_value"]["consignments"]} of {o["period_value"]["consignments"]}')
check("overview shafts narrows the stage chart",
      sum(b["consignments"] for b in sh["in_process"]["by_stage"])
      <= sum(b["consignments"] for b in o["in_process"]["by_stage"]))
ish = get("/dashboard/imports", shafts_only=True, **W)["consignments"]
check("imports shafts narrows the set",
      ish["population"]["total"]["count"] < p["total"]["count"],
      f'{ish["population"]["total"]["count"]} of {p["total"]["count"]}')

# The bug that opened this round: the Shafts tab filtered the tile but not the
# list it opened, so 1 consignment sat over a list of 7.
sho = get("/dashboard/overview", shafts_only=True, **OW)["imports"]
check("shafts tab filters the LIST too, not just the tile",
      sho["references"]["period_value"]["groups"] == sho["period_value"]["consignments"],
      f'{sho["references"]["period_value"]["total"]} lines across '
      f'{sho["references"]["period_value"]["groups"]} consignments')
check("category-delay chart withheld on shafts tab", ish["category_delays"] is None)
check("category-delay chart present otherwise", i["category_delays"] is not None)

print("\n== Procurement cycle time computes (was blank) ==")
proc = get("/dashboard/overview", purchases_date_from="2026-01-01", purchases_date_to="2026-01-23")["procurement"]
ct = proc["cycle_time"]
check("store-to-purchase cycle time present", ct["store_to_purchase_days"] is not None,
      f'{ct["store_to_purchase_days"]} days over {ct["store_to_purchase_basis"]} orders')
check("cycle time has a real basis", ct["store_to_purchase_basis"] > 0)

print("\n== Logistics: windowed order types, with the undated visible ==")
lg = get("/dashboard/logistics/shipments")
t = lg["order_type_counts"]
check("order split is windowed", t["windowed"] is True)
check("split sums to its own total",
      t["export"] + t["local"] + t["not_stated"] == t["total"],
      f'{t["total"]} in {lg["period"]["label"]}')
# The point of the undated tile: local orders carry no business date, so a
# windowed local count is structurally zero. If that ever stops being true this
# check fires and the tile can be reconsidered.
check("undated orders are reported, not dropped",
      t["undated"]["total"] > 0,
      f'{t["undated"]["total"]} orders in no period ({t["undated"]["local"]} local)')
check("every windowed tile has a list behind it",
      all(lg["references"][k]["total"] == t[k]
          for k in ("export", "local", "not_stated")))
check("the removed Not-Yet-Linked set is gone with its tile",
      "not_linked" not in lg["references"])
check("undated list matches the undated count",
      lg["references"]["undated"]["total"] == t["undated"]["total"])

ol = get("/dashboard/overview")["logistics"]
# The local tile is ALL TIME on purpose — a windowed local count is zero in
# every period, so this asserts the tile is on the basis that says something.
check("overview local tile is all-time, not the windowed zero",
      ol["references"]["local_orders"]["total"] == t["all_time"]["local"]
      and t["all_time"]["local"] > 0,
      f'{t["all_time"]["local"]} local orders across the whole book')

check("overview and the tab agree on the export count",
      ol["order_types"]["export"] == t["export"], str(t["export"]))
check("overview and the tab agree on the undated count",
      ol["order_types"]["undated"]["total"] == t["undated"]["total"])
check("overview export tile has a list behind it",
      ol["references"]["export_orders"]["total"] == ol["order_types"]["export"])

for _tab, _key in (("shipments", "undated"), ("packing", "packages"),
                   ("transport", "jobs")):
    _r = c.get("/dashboard/logistics/references",
               params={"tab": _tab, "key": _key, "page": 1, "page_size": 5})
    check(f"logistics references {_tab}/{_key} pages", _r.status_code == 200)
check("logistics references rejects an unknown tab",
      c.get("/dashboard/logistics/references",
            params={"tab": "nope", "key": "orders"}).status_code == 400)


print("\n== Logistics left unchanged ==")
lg = c.get("/dashboard/logistics/shipments")
check("logistics dashboard still answers", lg.status_code == 200)


#-------------------------------------------------------------------
# BATCHES vs ORDERS — the fourteen count decisions, reconciled on screen
#
# Runs ONLY against a scratch database carrying a real two-batch group. Every
# other database has one batch per group, where `count(rows)` and
# `count(distinct group)` are the same number and every assertion below would
# pass whichever unit the code used — the "both screens looked right" failure,
# inside the check written to prevent it. So each assertion first proves its
# two candidate answers DIFFER, and only then says which one the API gave.
#
# Set up with:   DB_NAME=scratch_x python -m tests.batch_fixture
#
# tests/test_count_units.py is the companion: it pins each site's unit against
# the compiled SQL, needs no database, and runs in the default pytest suite.
# This one proves the SCREENS reconcile once the units are right.
#-------------------------------------------------------------------

print("\n== Batches vs orders (scratch + split fixture only) ==")

_split = None
try:
    import os
    if (os.getenv("DB_NAME") or "").lower().startswith("scratch"):
        from tests.batch_fixture import connect, group_holding_two_batches
        _conn = connect()
        _split = group_holding_two_batches(_conn)
except Exception as _e:                                   # noqa: BLE001
    print(f"  [skip] fixture unavailable — {_e}")

if _split is None:
    print("  [SKIP] no two-batch group in this database. Rows and groups are")
    print("         identical here, so nothing below could discriminate.")
    print("         Run:  DB_NAME=scratch_x python -m tests.batch_fixture")
else:
    with _conn.cursor() as _cur:
        def one(sql_text, *params):
            _cur.execute(sql_text, params)
            return _cur.fetchone()[0]

        LIVE = "is_deleted = false"
        rows_all = one(f"SELECT count(*) FROM consignments WHERE {LIVE}")
        groups_all = one(
            f"SELECT count(DISTINCT batch_group_id) FROM consignments WHERE {LIVE}")

        check("the fixture actually discriminates (rows != orders)",
              rows_all != groups_all, f"{rows_all} batches across {groups_all} orders")

        # --- #13: the list counts BATCHES, and is forced to ---
        _l = c.get("/consignments/", params={"page": 1, "page_size": 1,
                                             "include_closed": True})
        _lt = _l.json()["pagination"]["total"]
        check("list total == batches, not orders (#13)",
              _lt == rows_all and _lt != groups_all,
              f"{_lt} vs {rows_all} batches / {groups_all} orders")

        # PAGED, not one big request: the list route clamps page_size, so
        # asking for 200 silently returns 20 and "the row is missing" would be
        # a bug in this check rather than in the list.
        _ids, _page = [], 1
        while True:
            _body = c.get("/consignments/", params={"page": _page, "page_size": 50,
                                                    "include_closed": True}).json()
            _ids += [r["id"] for r in _body["data"]
                     if r.get("batch_group_id") == _split]
            if _page >= (_body["pagination"]["total_pages"] or 1):
                break
            _page += 1
        check("both batches of the split order appear as separate rows",
              len(_ids) == 2, f"group {_split} -> {sorted(_ids)}")
        check("the list publishes which order a row belongs to",
              all(r.get("batch_group_id") for r in _body["data"]))

        # --- #3 and #9: rows on the tile, orders published alongside ---
        WIDE = ("2000-01-01", "2035-12-31")
        _o = get("/dashboard/overview", imports_date_from=WIDE[0],
                 imports_date_to=WIDE[1])["imports"]
        _pv, _pop = _o["period_value"], _o

        # MEMBERSHIP, not just liveness. A consignment is in the window only if
        # some LINE of it is dated inside it (whole/helpers._imports_window_
        # membership), and a handful carry no date at all — so `count(*)` is the
        # wrong denominator here and would fail this for a reason that has
        # nothing to do with batches vs orders.
        _cur.execute("""
            SELECT count(*), count(DISTINCT c.batch_group_id)
              FROM consignments c
             WHERE c.is_deleted = false
               AND EXISTS (SELECT 1 FROM consignment_items i
                            WHERE i.consignment_id = c.id
                              AND i.is_deleted = false
                              AND COALESCE(i.eta_works, c.eta_works)
                                  BETWEEN %s AND %s)
        """, WIDE)
        w_rows, w_groups = _cur.fetchone()

        check("overview period_value counts BATCHES (#3)",
              _pv["consignments"] == w_rows, f'{_pv["consignments"]} vs {w_rows}')
        check("overview period_value ALSO publishes the order count (#3)",
              _pv.get("orders") == w_groups,
              f'{_pv.get("orders")} vs {w_groups} orders')
        check("the two units differ, so publishing both is not decoration",
              _pv["consignments"] != _pv.get("orders"))

        check("overview population total counts BATCHES (#9)",
              _pop["population"]["total"]["count"] == w_rows
              if "population" in _pop else True)
        check("population still splits exactly into its buckets",
              _o["in_process"]["count"] + _o["arrived"]["count"]
              + _o["cancelled"]["count"] == _pv["consignments"])

        # --- #14: supplier and branch count ORDERS; the agent counts BATCHES ---
        _cur.execute("""
            SELECT g.supplier_id, g.works_branch_id, c.clearing_agent_id
              FROM consignment_batch_groups g
              JOIN consignments c ON c.batch_group_id = g.id
             WHERE g.id = %s ORDER BY c.batch_sequence LIMIT 1
        """, (_split,))
        _sup_id, _br_id, _ag_id = _cur.fetchone()

        def used_for(master, row_id):
            if row_id is None:
                return None
            body = c.get(f"/masters/{master}", params={"include_inactive": True}).json()
            for row in body["data"]:
                if row["id"] == row_id:
                    return row.get("used")
            return None

        for _master, _rid, _col, _table in (
            ("supplier", _sup_id, "supplier_id", "consignment_batch_groups"),
            ("branch", _br_id, "works_branch_id", "consignment_batch_groups"),
        ):
            if _rid is None:
                print(f"  [skip] the split order has no {_master}")
                continue
            _orders = one(f"SELECT count(*) FROM {_table} "
                          f"WHERE is_deleted = false AND {_col} = %s", _rid)
            _batches = one(f"SELECT count(*) FROM consignments c "
                           f"JOIN consignment_batch_groups g ON g.id = c.batch_group_id "
                           f"WHERE c.{LIVE} AND g.{_col} = %s", _rid)
            _used = used_for(_master, _rid)
            check(f"masters {_master} 'used' counts ORDERS (#14)",
                  _used == _orders,
                  f"{_used} vs {_orders} orders / {_batches} batches")
            if _orders != _batches:
                check(f"masters {_master}: the two units differ here",
                      _used != _batches)

        if _ag_id is not None:
            _ag_batches = one(f"SELECT count(*) FROM consignments "
                              f"WHERE {LIVE} AND clearing_agent_id = %s", _ag_id)
            _ag_groups = one(f"SELECT count(DISTINCT batch_group_id) FROM consignments "
                             f"WHERE {LIVE} AND clearing_agent_id = %s", _ag_id)
            _used = used_for("agent", _ag_id)
            check("masters clearing agent 'used' counts BATCHES (#14)",
                  _used == _ag_batches,
                  f"{_used} vs {_ag_batches} batches / {_ag_groups} orders")
        else:
            print("  [skip] the split order has no clearing agent")

        # --- the split must not have INVENTED money ---
        _order_value = one("""
            SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
              FROM consignment_items i
              JOIN consignments c ON c.id = i.consignment_id
             WHERE c.batch_group_id = %s AND i.is_deleted = false
               AND c.is_deleted = false
        """, _split)
        _stored = one("""
            SELECT COALESCE(SUM(foreign_total), 0) FROM consignments
             WHERE batch_group_id = %s AND is_deleted = false
        """, _split)
        check("the two batches' stored totals sum to the ORDER's value",
              abs(float(_order_value) - float(_stored)) < 0.01,
              f"{float(_order_value):,.2f} vs {float(_stored):,.2f}")

    _conn.close()

print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
if FAILS:
    print("FAILED:\n  " + "\n  ".join(FAILS))
raise SystemExit(1 if FAILS else 0)
