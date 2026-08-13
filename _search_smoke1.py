import warnings; warnings.filterwarnings('ignore')
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
assert c.post("/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 200

def get_ref(**params):
    r = c.get("/dashboard/overview/references", params=params)
    assert r.status_code == 200, (params, r.status_code, r.text[:300])
    return r.json()["data"]

# baseline (no search) for imports.period_value
base = get_ref(key="imports.period_value", page=1, page_size=5)
print("baseline imports.period_value total:", base["total"])
if base["items"]:
    sample_ref = base["items"][0]["reference"]
    print("sample reference to search for:", sample_ref)
    hit = get_ref(key="imports.period_value", page=1, page_size=5, search=sample_ref)
    print("search by exact reference -> total:", hit["total"], "| first item ref:", hit["items"][0]["reference"] if hit["items"] else None)
    assert hit["total"] >= 1
    assert any(sample_ref in (it["reference"] or "") for it in hit["items"])

gibberish = get_ref(key="imports.period_value", page=1, page_size=5, search="zzznonexistentqqq")
print("gibberish search -> total:", gibberish["total"], "items:", len(gibberish["items"]))
assert gibberish["total"] == 0

# procurement (grouped PO query) - search should keep full order value, not truncate
base_p = get_ref(key="procurement.period_value", page=1, page_size=200,
                  date_from="2026-01-01", date_to="2026-08-31")
print("\nprocurement baseline total:", base_p["total"])
if base_p["items"]:
    po = base_p["items"][0]["reference"]
    full_value = base_p["items"][0]["badge"]
    hit_p = get_ref(key="procurement.period_value", page=1, page_size=5, search=po,
                     date_from="2026-01-01", date_to="2026-08-31")
    matched = [it for it in hit_p["items"] if it["reference"] == po]
    print(f"search for PO {po}: total={hit_p['total']}, found={len(matched)}, badge={matched[0]['badge'] if matched else None} (expected {full_value})")
    assert matched, "matched PO not found by its own PO number"
    assert matched[0]["badge"] == full_value, "search truncated the aggregate value!"

# stock (search on item_code)
base_s = get_ref(key="stores.stock_value", page=1, page_size=5)
if base_s["items"]:
    code = base_s["items"][0]["reference"]
    hit_s = get_ref(key="stores.stock_value", page=1, page_size=5, search=code)
    print(f"\nstock search for {code}: total={hit_s['total']}")
    assert hit_s["total"] >= 1

print("\nALL OVERVIEW SEARCH SMOKE TESTS PASSED")
