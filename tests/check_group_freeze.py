"""Drive the group freeze over HTTP, on a genuinely split order.

WHY THIS EXISTS AND WHY IT IS NOT A PYTEST FILE. `tests/test_group_freeze.py`
pins the rule over plain objects and needs no database. This drives the ROUTES,
which needs a running server, a real split order and two logins — so it lives
beside `check_batch_allocation.py` and `check_dashboard_consistency.py` and is
run by hand.

RUN IT AGAINST A FRESH CLONE. It MUTATES, and several checks depend on a field
not already holding the value they are about to set - a second run against its
own leavings reports failures that are the script's, not the product's.
Measured: re-running without recreating the database turned four passes into
failures, because the origin was already `Germany` from the first run, so the
save produced no diff, so there was nothing for the freeze to refuse.

IT ASSERTS VALUES, NEVER STATUS CODES ALONE. A freeze that returns 200 and
quietly drops the field is the exact failure it exists to prevent, so every
permitted case re-reads the record and checks the value MOVED, and every refused
case re-reads and checks it did NOT.

SAFETY: `_require_scratch` refuses any database whose name does not begin with
`scratch`, and there is no override — the same guard `batch_fixture` uses.
"""

import os
import sys

import httpx
import psycopg2


BASE_URL = os.getenv("ERP_BASE_URL", "http://127.0.0.1:8011")

ARRIVED = "Arrived at Works"
CLERK_USERNAME = "freeze_clerk"
CLERK_PASSWORD = "freeze_clerk_pw"

passed, failed = 0, 0


def check(label, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  [PASS] {label}" + (f"   {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  [FAIL] {label}" + (f"   {detail}" if detail else ""))


def _require_scratch(name):
    if not (name or "").startswith("scratch"):
        raise RuntimeError(
            f"refusing to run against {name!r}: this script MUTATES. "
            "Point DB_NAME at a scratch database."
        )
    return name


def connect():
    name = _require_scratch(os.getenv("DB_NAME"))
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
        dbname=name, user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
    )


def login(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    r.raise_for_status()
    return r.json()["data"]


def stored(conn, group_id, column):
    """Read a group column straight from the database.

    THE WHOLE POINT. The API's own echo could be telling us what it meant to do;
    the table says what it did.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {column} FROM consignment_batch_groups WHERE id = %s",  # noqa: S608
            (group_id,),
        )
        return cur.fetchone()[0]


def put(client, conn, cid, **fields):
    """A wizard-shaped PUT: the whole record back, with `fields` overridden.

    THE DRIVER HAS TO POST THE WHOLE DRAFT, because the update route soft-
    deletes any line missing from the payload (`delete_missing`) - that is the
    wizard's contract, and a fragment PUT silently empties the batch.

    Measured, and it cost a run: posting {"origin": "Japan"} on its own removed
    all three of batch 2's lines, so the allocation was empty by the time the
    new-batch section looked for something to allocate, and that section
    reported `skip` rather than failing. A driver that tests a shape the
    application never posts is testing something else.
    """
    record = client.get(f"/consignments/{cid}").json()["data"]
    body = {"items": [i for i in record["items"] if not i["is_deleted"]]}
    body.update(fields)
    r = client.put(f"/consignments/{cid}", json=body)
    conn.commit()
    return r


def main():
    conn = connect()

    admin = httpx.Client(base_url=BASE_URL, timeout=30)
    login(admin, os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD"))

    #-- the split order -----------------------------------------------------
    with conn.cursor() as cur:
        # THE LATER BATCH MUST CARRY LIVE LINES. A split whose second batch has
        # had its lines removed looks like a valid fixture - two batches, one
        # group - and silently skips every check that needs something to
        # allocate. Measured: the first split this picked had all three of its
        # lines soft-deleted, and the new-batch section reported `skip` rather
        # than failing, which is the quieter of the two bad outcomes.
        cur.execute("""
            SELECT g.id, min(c.id), max(c.id)
              FROM consignment_batch_groups g
              JOIN consignments c ON c.batch_group_id = g.id
             WHERE g.batches_ever > 1 AND g.is_deleted = false
               AND c.is_deleted = false
               AND EXISTS (SELECT 1 FROM consignment_items ci
                            WHERE ci.consignment_id = c.id
                              AND ci.is_deleted = false)
             GROUP BY g.id HAVING count(*) > 1
             ORDER BY g.id LIMIT 1
        """)
        row = cur.fetchone()
    if row is None:
        print("No split order. Build one: python -m tests.batch_fixture")
        return 1
    group_id, batch1, batch2 = row
    print(f"\n== Fixture ==\n  order {group_id}: batch 1 = {batch1}, batch 2 = {batch2}")

    #-- a NON-ADMIN with edit rights ----------------------------------------
    perms = ["can_view_imports_consignments", "can_add_imports_consignments",
             "can_edit_imports_consignments", "can_view_master"]
    r = admin.get("/users/")
    existing = {u["username"]: u["id"] for u in r.json().get("data", [])}
    if CLERK_USERNAME in existing:
        admin.put(f"/users/{existing[CLERK_USERNAME]}", json={
            "username": CLERK_USERNAME, "password": CLERK_PASSWORD,
            "is_admin": False, "permissions": perms})
    else:
        admin.post("/users/", json={
            "username": CLERK_USERNAME, "password": CLERK_PASSWORD,
            "is_admin": False, "permissions": perms})
    clerk = httpx.Client(base_url=BASE_URL, timeout=30)
    who = login(clerk, CLERK_USERNAME, CLERK_PASSWORD)
    check("a non-admin clerk exists to test Tier 2 against",
          who["is_admin"] is False, f"is_admin={who['is_admin']}")

    #-- BEFORE the freeze: everything is editable ---------------------------
    print("\n== Before any batch closes — the freeze must not be on ==")
    before = stored(conn, group_id, "origin")
    r = put(clerk, conn, batch2, origin="Japan")
    check("a clerk may change the origin while every batch is open",
          r.status_code == 200 and stored(conn, group_id, "origin") == "Japan",
          f"{r.status_code}, stored={stored(conn, group_id, 'origin')!r}")

    r = put(clerk, conn, batch2, exchange_rate=279.5)
    check("...and the exchange rate",
          r.status_code == 200 and float(stored(conn, group_id, "exchange_rate")) == 279.5,
          f"{r.status_code}, stored={stored(conn, group_id, 'exchange_rate')}")

    detail = admin.get(f"/consignments/{batch2}").json()["data"]
    check("group_frozen says not frozen",
          detail["group_frozen"]["is_frozen"] is False,
          str(detail["group_frozen"]))

    #-- close batch 1 -------------------------------------------------------
    print(f"\n== Closing batch {batch1} ==")
    r = put(admin, conn, batch1, current_status=ARRIVED)
    with conn.cursor() as cur:
        cur.execute("SELECT current_status, is_locked FROM consignments WHERE id = %s",
                    (batch1,))
        status, locked = cur.fetchone()
    check("batch 1 is closed and locked", status == ARRIVED and locked,
          f"status={status!r} is_locked={locked}")

    detail = admin.get(f"/consignments/{batch2}").json()["data"]
    gf = detail["group_frozen"]
    check("group_frozen now says frozen, and names the batch",
          gf["is_frozen"] and gf["frozen_by"]["consignment_id"] == batch1,
          f"frozen_by={gf['frozen_by']}")
    check("group_frozen publishes PAYLOAD keys, so branch_id not works_branch_id",
          "branch_id" in gf["admin"] and "works_branch_id" not in gf["admin"],
          f"admin={gf['admin']}")

    #-- TIER 1 --------------------------------------------------------------
    print("\n== Tier 1 — the rate. Nobody, including an admin ==")
    for who_name, client in (("clerk", clerk), ("ADMIN", admin)):
        was = float(stored(conn, group_id, "exchange_rate"))
        r = put(client, conn, batch2, exchange_rate=281.0)
        now = float(stored(conn, group_id, "exchange_rate"))
        check(f"{who_name}: changing the rate is REFUSED 423",
              r.status_code == 423, f"{r.status_code}")
        check(f"{who_name}: and the stored rate did NOT move",
              now == was, f"{was} -> {now}")
        check(f"{who_name}: the refusal names the field and the batch",
              "exchange rate" in r.text and str(batch1) in r.text,
              r.json().get("detail", "")[:110])

    was = stored(conn, group_id, "currency")
    r = put(admin, conn, batch2, currency="EUR")
    check("ADMIN: changing the currency is refused too",
          r.status_code == 423 and stored(conn, group_id, "currency") == was,
          f"{r.status_code}, stored={stored(conn, group_id, 'currency')!r}")

    #-- TIER 2 --------------------------------------------------------------
    print("\n== Tier 2 — commercial terms. Admin yes, clerk no ==")
    was = stored(conn, group_id, "origin")
    r = put(clerk, conn, batch2, origin="Germany")
    check("clerk: changing the origin is REFUSED 423",
          r.status_code == 423, f"{r.status_code}")
    check("clerk: and the stored origin did NOT move",
          stored(conn, group_id, "origin") == was,
          f"{was!r} -> {stored(conn, group_id, 'origin')!r}")
    check("clerk: the refusal says an admin can do it",
          "admin can still" in r.text.lower(), r.json().get("detail", "")[:110])

    r = put(admin, conn, batch2, origin="Germany")
    check("ADMIN: changing the origin is PERMITTED",
          r.status_code == 200, f"{r.status_code}")
    check("ADMIN: and the stored origin DID move",
          stored(conn, group_id, "origin") == "Germany",
          f"{was!r} -> {stored(conn, group_id, 'origin')!r}")

    #-- branch_id, the renamed key ------------------------------------------
    print("\n== branch_id -> works_branch_id, the key the rename could hide ==")
    was = stored(conn, group_id, "works_branch_id")
    other = None
    with conn.cursor() as cur:
        # `is_active`, not `is_deleted` - the master tables turn a row off
        # rather than deleting it (CLAUDE.md, masters).
        cur.execute("SELECT id FROM branches WHERE id IS DISTINCT FROM %s "
                    "AND is_active = true ORDER BY id LIMIT 1", (was,))
        got = cur.fetchone()
        other = got[0] if got else None
    r = put(clerk, conn, batch2, branch_id=other)
    check("clerk: changing the works/branch is REFUSED",
          r.status_code == 423, f"{r.status_code}")
    check("clerk: and works_branch_id did NOT move",
          stored(conn, group_id, "works_branch_id") == was,
          f"{was} -> {stored(conn, group_id, 'works_branch_id')}")

    #-- an UNFROZEN field on a frozen order ---------------------------------
    print("\n== The freeze is not a blanket lock ==")
    r = put(clerk, conn, batch2, eta="2026-12-01")
    with conn.cursor() as cur:
        cur.execute("SELECT eta FROM consignments WHERE id = %s", (batch2,))
        eta = cur.fetchone()[0]
    check("clerk may still edit the BATCH's own fields on a frozen order",
          r.status_code == 200 and str(eta) == "2026-12-01",
          f"{r.status_code}, eta={eta}")

    #-- a NEW batch on a frozen order ---------------------------------------
    print("\n== A batch created after batch 1 closed inherits the terms ==")
    # MAKE ROOM FOR ONE. A fully-allocated order has nothing to put in a third
    # batch, and `ordered_quantity` lives on the ORDER LINE, which is not a
    # group field and is therefore not frozen - raising it here doubles as a
    # check that the freeze did not over-reach onto the item rows.
    detail = admin.get(f"/consignments/{batch2}").json()["data"]
    item = next((i for i in detail["items"] if not i["is_deleted"]), None)
    if item is not None:
        whole = dict(item)
        whole["ordered_quantity"] = float(item.get("ordered_quantity") or 0) + 5
        # The WHOLE line back, not a fragment: for an ordinary field an absent
        # key means "clear it" (helpers.SERVER_RESOLVED_ITEM_FIELDS).
        r = admin.put(f"/consignments/{batch2}", json={"items": [whole]})
        conn.commit()
        check("the order quantity is NOT frozen - it is an order LINE field",
              r.status_code == 200, f"{r.status_code} {r.text[:90]}")

    lines = admin.get(f"/consignments/{batch2}").json()["data"]["allocation"]
    line = next((l for l in lines if (l["outstanding_quantity"] or 0) > 0), None)
    if line is None:
        print("  [skip] no outstanding quantity to allocate a new batch from")
    else:
        r = clerk.post(f"/consignments/{batch2}/batches", json={"allocations": [
            {"order_item_id": line["order_item_id"], "quantity": 1}]})
        check("creating the next batch is still allowed on a frozen order",
              r.status_code in (200, 201), f"{r.status_code} {r.text[:90]}")
        if r.status_code in (200, 201):
            new_id = r.json()["data"]["batch"]["id"]
            was = float(stored(conn, group_id, "exchange_rate"))
            r = put(clerk, conn, new_id, exchange_rate=290.0)
            check("...but it may NOT set the order's rate — it inherits them",
                  r.status_code == 423 and float(stored(conn, group_id, "exchange_rate")) == was,
                  f"{r.status_code}, stored={stored(conn, group_id, 'exchange_rate')}")

    #-- REVERT ---------------------------------------------------------------
    print("\n== Revert — restore what is permitted, report what is not ==")
    # An admin change that touches a Tier 1 field and an ordinary one together.
    put(admin, conn, batch2, remarks="before revert")
    r = put(admin, conn, batch2, remarks="after revert", origin="Italy")
    check("admin made a change mixing an ordinary field and a Tier 2 field",
          r.status_code == 200, f"{r.status_code}")

    hist = admin.get(f"/consignments/change-history/{batch2}").json()["data"]
    hid = hist[0]["id"] if hist else None

    # The clerk reverts it: `remarks` is theirs to restore, `origin` is not.
    r = clerk.put(f"/consignments/revert-update/{batch2}/{hid}")
    conn.commit()
    body = r.json() if r.status_code == 200 else {}
    with conn.cursor() as cur:
        cur.execute("SELECT remarks FROM consignments WHERE id = %s", (batch2,))
        remarks = cur.fetchone()[0]
    check("clerk's revert SUCCEEDS rather than refusing wholesale",
          r.status_code == 200, f"{r.status_code} {r.text[:90]}")
    check("...it restored the field it was allowed to",
          remarks == "before revert", f"remarks={remarks!r}")
    check("...it did NOT restore the frozen one",
          stored(conn, group_id, "origin") == "Italy",
          f"origin={stored(conn, group_id, 'origin')!r}")
    check("...and it REPORTED what it skipped, naming the field",
          "origin" in (body.get("skipped_fields") or []),
          f"skipped_fields={body.get('skipped_fields')}")
    check("...with a reason beside it, not a bare key",
          "settled" in str((body.get("skipped_detail") or {}).get("origin", "")),
          str((body.get("skipped_detail") or {}).get("origin"))[:100])
    check("...and the sentence the operator reads says so",
          "origin" in body.get("detail", ""), body.get("detail", "")[:130])

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.exit(main())
