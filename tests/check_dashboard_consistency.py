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
check("total value matches", float(o["period_value"]["value"]) == float(i["period_value"]["value"]),
      f'{float(o["period_value"]["value"]):,.0f}')
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
check("undated list matches the undated tile",
      lg["references"]["undated"]["total"] == t["undated"]["total"])

ol = get("/dashboard/overview")["logistics"]
check("overview and the tab agree on the export count",
      ol["order_types"]["export"] == t["export"], str(t["export"]))
check("overview and the tab agree on the undated count",
      ol["order_types"]["undated"]["total"] == t["undated"]["total"])
check("overview order tiles have lists behind them",
      ol["references"]["export_orders"]["total"] == ol["order_types"]["export"]
      and ol["references"]["undated_orders"]["total"]
      == ol["order_types"]["undated"]["total"])

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

print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
if FAILS:
    print("FAILED:\n  " + "\n  ".join(FAILS))
raise SystemExit(1 if FAILS else 0)
