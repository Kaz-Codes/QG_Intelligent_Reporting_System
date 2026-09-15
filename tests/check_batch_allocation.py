"""Allocation, batch creation and numbering, driven through the real routes.

WHY THIS IS A SCRIPT AND NOT PYTEST. Like `check_dashboard_consistency.py`, it
needs a live app, a real database and a login. The pure suite
(`tests/test_batch_numbering.py`) pins the rules that can be checked without
one; this proves the routes actually behave that way end to end.

    DB_NAME=scratch_x python -m uvicorn app.main:app --port 8011
    DB_NAME=scratch_x python tests/check_batch_allocation.py

EVERY ASSERTION IS ON A VALUE, NEVER ON A STATUS CODE. A 200 says a request was
handled, not that it did the right thing - and this whole area is one where the
wrong behaviour returns a perfectly good response. So the numbers come back out
of SQL and are compared.

AND THE OVER-ALLOCATION CHECKS ASSERT THE REFUSAL, NOT THE ABSENCE OF ONE.
`ck_allocation_within_order` has never rejected anything in the life of this
database, for a structural reason: until this change the only writers set
`allocated_quantity` and `ordered_quantity` to the same value, so it evaluated
`q <= q` on every row. A test that only checks the happy path would leave that
exactly as it was - a constraint nobody has ever seen fire.

SAFETY: scratch databases only, enforced by `batch_fixture._require_scratch`
before the first request. It creates and deletes records, so it must not be
pointed anywhere else.
"""

import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.batch_fixture import _require_scratch, client, connect  # noqa: E402

_require_scratch(os.getenv("DB_NAME"))

conn = connect()
conn.autocommit = True
cur = conn.cursor()
c = client()

PASSES, FAILS = [], []


def check(label, ok, detail=""):
    (PASSES if ok else FAILS).append(label)
    print(("  [PASS] " if ok else "  [FAIL] ") + label + (f"   {detail}" if detail else ""))


def one(sql, *params):
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def rows(sql, *params):
    cur.execute(sql, params)
    return cur.fetchall()


def detail_of(consignment_id):
    r = c.get(f"/consignments/{consignment_id}")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def draft_from(d):
    from tests.batch_fixture import _draft_from
    return _draft_from(d)


def create_batch(consignment_id, allocations):
    return c.post(f"/consignments/{consignment_id}/batches",
                  json={"allocations": allocations})


def body_code(r):
    try:
        return r.json().get("status_code")
    except Exception:
        return None


def detail_message(r):
    try:
        return str(r.json().get("detail"))
    except Exception:
        return r.text[:200]


#===========================================================================
# A FRESH ORDER, MADE THROUGH THE REAL CREATE ROUTE
#
# Built rather than borrowed from the loaded data, so the quantities are known
# exactly and an assertion can say "250" instead of "whatever was in the sheet".
#===========================================================================

print("\n== Setting up: a new order for 250 and 60 of two items ==")

supplier_id = one("SELECT id FROM suppliers WHERE is_active ORDER BY id LIMIT 1")
branch_id = one("SELECT id FROM branches WHERE is_active ORDER BY id LIMIT 1")

r = c.post("/consignments/", json={
    "supplier_id": supplier_id,
    "branch_id": branch_id,
    "instrument_number": "ALLOC-TEST-1",
    "payment_instrument": "LC",
    "currency": "USD",
    "exchange_rate": 280,
    "current_status": "TT/LC in Process",
    "items": [
        {"item_name": "Widget A", "quantity": 250, "unit_price": 10,
         "unit_of_measurement": "Pcs"},
        {"item_name": "Widget B", "quantity": 60, "unit_price": 5,
         "unit_of_measurement": "Kg"},
    ],
    "payments": [],
})
assert body_code(r) == 201, r.text
order = r.json()["data"]
first_id = order["id"]
group_id = order["batch_group_id"]

alloc = {a["item"]: a for a in order["allocation"]}
check("a new order is fully allocated to its only batch",
      all(Decimal(str(a["outstanding_quantity"])) == 0 for a in order["allocation"]),
      str([(a["item"], a["ordered_quantity"], a["allocated_quantity"]) for a in order["allocation"]]))
check("ordered_quantity followed the line on a single-batch order",
      Decimal(str(alloc["Widget A"]["ordered_quantity"])) == 250,
      f'{alloc["Widget A"]["ordered_quantity"]}')
check("a single batch has the plain number, no suffix",
      order["consignment_number"] == str(first_id), order["consignment_number"])

widget_a = alloc["Widget A"]["order_item_id"]
widget_b = alloc["Widget B"]["order_item_id"]


#===========================================================================
# 1. OVER-ALLOCATION IS REFUSED - driven until it actually refuses
#===========================================================================

print("\n== 1. Over-allocation ==")

# Nothing is outstanding yet, so ANY second batch is over-allocation.
r = create_batch(first_id, [{"order_item_id": widget_a, "quantity": 1}])
check("a batch against a fully-allocated order is refused",
      r.status_code == 422, f"{r.status_code}: {detail_message(r)}")
check("the refusal names the item and the overage",
      "Widget A" in detail_message(r) and "251" in detail_message(r),
      detail_message(r))
check("nothing was written by the refused request",
      one("SELECT count(*) FROM consignments WHERE batch_group_id = %s", group_id) == 1
      and one("SELECT batches_ever FROM consignment_batch_groups WHERE id = %s", group_id) == 1,
      f'batches={one("SELECT count(*) FROM consignments WHERE batch_group_id = %s", group_id)}, '
      f'batches_ever={one("SELECT batches_ever FROM consignment_batch_groups WHERE id = %s", group_id)}')

# Free 150 of Widget A and 20 of Widget B by lowering batch 1.
d = detail_from = detail_of(first_id)
payload = draft_from(d)
for item in payload["items"]:
    item["quantity"] = 100 if item["item_name"] == "Widget A" else 40
r = c.put(f"/consignments/{first_id}", json=payload)
assert body_code(r) == 200, r.text

after = {a["item"]: a for a in r.json()["data"]["allocation"]}
check("lowering a line frees the difference as outstanding",
      Decimal(str(after["Widget A"]["outstanding_quantity"])) == 150
      and Decimal(str(after["Widget B"]["outstanding_quantity"])) == 20,
      f'A outstanding {after["Widget A"]["outstanding_quantity"]}, '
      f'B outstanding {after["Widget B"]["outstanding_quantity"]}')
check("but the ORDER quantity did not move with it",
      Decimal(str(after["Widget A"]["ordered_quantity"])) == 250,
      str(after["Widget A"]["ordered_quantity"]))

# One more than is outstanding.
r = create_batch(first_id, [{"order_item_id": widget_a, "quantity": 151}])
check("one unit past the outstanding quantity is refused",
      r.status_code == 422, f"{r.status_code}: {detail_message(r)}")
check("the refusal states the overage as 1",
      "over by 1" in detail_message(r), detail_message(r))

# Exactly the outstanding quantity is accepted - the boundary from below.
r = create_batch(first_id, [
    {"order_item_id": widget_a, "quantity": 150},
    {"order_item_id": widget_b, "quantity": 20},
])
check("exactly the outstanding quantity IS accepted",
      body_code(r) == 201, f"{r.status_code}: {detail_message(r)}")
created = r.json()["data"]
second_id = created["batch"]["id"]

check("the order is now fully allocated again",
      one("""SELECT count(*) FROM consignment_order_items
              WHERE batch_group_id = %s AND allocated_quantity <> ordered_quantity""",
          group_id) == 0)
check("allocated_quantity equals the SUM of the live lines across both batches",
      one("""SELECT count(*) FROM consignment_order_items o
               LEFT JOIN (SELECT i.order_item_id, SUM(i.quantity) s
                            FROM consignment_items i
                            JOIN consignments cc ON cc.id = i.consignment_id
                           WHERE i.is_deleted = false AND cc.is_deleted = false
                           GROUP BY 1) x ON x.order_item_id = o.id
              WHERE o.batch_group_id = %s
                AND o.allocated_quantity <> COALESCE(x.s, 0)""", group_id) == 0)


#===========================================================================
# 2. AN ORDER LINE THAT ORDERED NOTHING - ruling 1
#===========================================================================

print("\n== 2. A line with no ordered quantity ==")

# THE TWO REAL ROWS IN THIS STATE are the migration's COALESCE rows - sheet
# lines that carried no quantity. Both sit under consignments that were
# soft-deleted, so the batch route cannot be pointed at them until one is
# restored. Restoring it through the real undo-delete route is itself worth
# doing: it is the one path that re-claims allocation, and a line ordering
# nothing allocates nothing, so it must succeed.
zero_line, zero_group = (rows("""
    SELECT o.id, o.batch_group_id FROM consignment_order_items o
     WHERE o.ordered_quantity = 0 AND o.is_deleted = false
     ORDER BY o.id LIMIT 1""") or [(None, None)])[0]

if zero_line is None:
    print("  [skip] no zero-quantity order line in this database")
else:
    owner = one("""SELECT id FROM consignments WHERE batch_group_id = %s
                    ORDER BY id LIMIT 1""", zero_group)

    if one("SELECT is_deleted FROM consignments WHERE id = %s", owner):
        r = c.post(f"/consignments/undo-delete/{owner}")
        check("a batch whose lines order nothing can be undeleted",
              body_code(r) == 200, detail_message(r))

    r = create_batch(owner, [{"order_item_id": zero_line, "quantity": 1}])
    check("allocating against a line that ordered nothing is refused",
          r.status_code == 422, f"{r.status_code}: {detail_message(r)}")
    check("the refusal NAMES THE FIX rather than just saying no",
          "Set the ordered quantity" in detail_message(r), detail_message(r))

    # RULING 1 SAYS THE FIX IS REACHABLE, so the fix is exercised: set the
    # order quantity through the ordinary edit, then allocate.
    d = detail_of(owner)
    payload = draft_from(d)
    for item in payload["items"]:
        if item.get("order_item_id") == zero_line:
            item["ordered_quantity"] = 5
            item["quantity"] = item.get("quantity") or 1
    r = c.put(f"/consignments/{owner}", json=payload)
    check("the ordered quantity can be set through the ordinary edit",
          body_code(r) == 200, detail_message(r))
    check("and the order line now records it",
          one("SELECT ordered_quantity FROM consignment_order_items WHERE id = %s",
              zero_line) == Decimal("5.000"),
          str(one("SELECT ordered_quantity FROM consignment_order_items WHERE id = %s", zero_line)))

    r = create_batch(owner, [{"order_item_id": zero_line, "quantity": 1}])
    check("allocation against that line is then accepted",
          body_code(r) == 201, detail_message(r))


#===========================================================================
# 3. AN ORDER LINE FROM ANOTHER ORDER
#===========================================================================

print("\n== 3. Allocating across orders ==")

foreign_line = one("""SELECT id FROM consignment_order_items
                       WHERE batch_group_id <> %s AND is_deleted = false
                       ORDER BY id LIMIT 1""", group_id)
r = create_batch(first_id, [{"order_item_id": foreign_line, "quantity": 1}])
check("an order line belonging to another order is refused",
      r.status_code == 422, f"{r.status_code}: {detail_message(r)}")
check("the refusal says why",
      "does not belong to this order" in detail_message(r), detail_message(r))

r = create_batch(first_id, [
    {"order_item_id": widget_a, "quantity": 1},
    {"order_item_id": widget_a, "quantity": 1},
])
check("the same item twice in one batch is refused",
      r.status_code == 422, f"{r.status_code}: {detail_message(r)}")


#===========================================================================
# 4. NUMBERING - A1, A2, A3
#===========================================================================

print("\n== 4. Numbering ==")

first = detail_of(first_id)
second = detail_of(second_id)

check("A1: the founding batch was RENUMBERED by the split",
      first["consignment_number"] == f"{first_id}-1", first["consignment_number"])
check("A1: the new batch is -2",
      second["consignment_number"] == f"{first_id}-2", second["consignment_number"])
check("A1: the renumbering was reported by the route that caused it",
      created["numbering"]["siblings_renumbered"] is True
      and any(b["previous_consignment_number"] == str(first_id)
              and b["consignment_number"] == f"{first_id}-1"
              for b in created["numbering"]["batches"]),
      str(created["numbering"]["batches"]))
check("the renumbering wrote NOTHING to the founding batch",
      one("SELECT batch_sequence FROM consignments WHERE id = %s", first_id) == 1)
check("both batches share the order's payment reference",
      first["payment_reference"] == second["payment_reference"]
      and first["payment_reference"] == "lcALLOC-TEST-1",
      f'{first["payment_reference"]} / {second["payment_reference"]}')
check("A2: no phantom third batch was created for the remainder",
      one("SELECT count(*) FROM consignments WHERE batch_group_id = %s", group_id) == 2)

# A third batch, to make a gap worth seeing.
d = detail_of(first_id)
payload = draft_from(d)
for item in payload["items"]:
    if item["item_name"] == "Widget A":
        item["quantity"] = 60
r = c.put(f"/consignments/{first_id}", json=payload)
assert body_code(r) == 200, r.text

r = create_batch(first_id, [{"order_item_id": widget_a, "quantity": 40}])
check("a third batch is accepted from the freed quantity", body_code(r) == 201,
      detail_message(r))
third_id = r.json()["data"]["batch"]["id"]
check("the third batch is -3", detail_of(third_id)["consignment_number"] == f"{first_id}-3",
      detail_of(third_id)["consignment_number"])
check("adding a THIRD batch renumbers nobody",
      r.json()["data"]["numbering"]["siblings_renumbered"] is False)


#===========================================================================
# 5. DELETE RELEASES THE ALLOCATION; THE NUMBER IS NOT RELEASED
#===========================================================================

print("\n== 5. Delete and undo-delete ==")

before_alloc = one("""SELECT allocated_quantity FROM consignment_order_items
                       WHERE id = %s""", widget_a)

r = c.delete(f"/consignments/{second_id}")
check("deleting a batch succeeds", body_code(r) == 200, detail_message(r))

after_alloc = one("""SELECT allocated_quantity FROM consignment_order_items
                      WHERE id = %s""", widget_a)
check("deleting a batch RELEASES its allocation",
      after_alloc == before_alloc - Decimal("150"),
      f"{before_alloc} -> {after_alloc}")

check("A3: the surviving batches keep their numbers, gap and all",
      detail_of(first_id)["consignment_number"] == f"{first_id}-1"
      and detail_of(third_id)["consignment_number"] == f"{first_id}-3",
      f'{detail_of(first_id)["consignment_number"]}, {detail_of(third_id)["consignment_number"]}')
check("A3: batches_ever was NOT decremented",
      one("SELECT batches_ever FROM consignment_batch_groups WHERE id = %s", group_id) == 3)

# Take the freed quantity with a new batch, then try to undo the delete.
r = create_batch(first_id, [{"order_item_id": widget_a, "quantity": 150}])
check("the released quantity can be given to a replacement batch",
      body_code(r) == 201, detail_message(r))
fourth_id = r.json()["data"]["batch"]["id"]
check("the replacement is -4, not -2: a number is never reused",
      detail_of(fourth_id)["consignment_number"] == f"{first_id}-4",
      detail_of(fourth_id)["consignment_number"])

before_undo = one("SELECT allocated_quantity FROM consignment_order_items "
                  "WHERE id = %s", widget_a)
r = c.post(f"/consignments/undo-delete/{second_id}")
check("undoing a delete whose quantity was re-allocated is REFUSED",
      r.status_code == 422, f"{r.status_code}: {detail_message(r)}")
check("the refusal names the overage",
      "Widget A" in detail_message(r) and "over by 150" in detail_message(r),
      detail_message(r))
check("the refused undo left the batch deleted",
      one("SELECT is_deleted FROM consignments WHERE id = %s", second_id) is True)
check("and left the allocation exactly as it was before the attempt",
      one("SELECT allocated_quantity FROM consignment_order_items WHERE id = %s",
          widget_a) == before_undo,
      f'{one("SELECT allocated_quantity FROM consignment_order_items WHERE id = %s", widget_a)} '
      f'vs {before_undo}')

# Make room, then the undo must succeed.
r = c.delete(f"/consignments/{fourth_id}")
assert body_code(r) == 200, r.text
r = c.post(f"/consignments/undo-delete/{second_id}")
check("undoing a delete succeeds once the quantity is free again",
      body_code(r) == 200, detail_message(r))
check("the restored batch's allocation is counted again",
      one("SELECT allocated_quantity FROM consignment_order_items WHERE id = %s",
          widget_a) == before_alloc,
      f"{one('SELECT allocated_quantity FROM consignment_order_items WHERE id = %s', widget_a)} "
      f"vs {before_alloc}")


#===========================================================================
# 6. THE ORDER LINE OUTLIVES ANY ONE BATCH'S LINE
#===========================================================================

print("\n== 6. The shared order line ==")

check("Widget B's order line is carried by two batches",
      one("""SELECT count(*) FROM consignment_items i
               JOIN consignments cc ON cc.id = i.consignment_id
              WHERE i.order_item_id = %s AND i.is_deleted = false
                AND cc.is_deleted = false""", widget_b) == 2,
      str(one("""SELECT count(*) FROM consignment_items i
                   JOIN consignments cc ON cc.id = i.consignment_id
                  WHERE i.order_item_id = %s AND i.is_deleted = false
                    AND cc.is_deleted = false""", widget_b)))

# Drop Widget B from batch 1 by leaving it out of the payload.
d = detail_of(first_id)
payload = draft_from(d)
payload["items"] = [i for i in payload["items"] if i["item_name"] != "Widget B"]
r = c.put(f"/consignments/{first_id}", json=payload)
check("a batch can drop a line it shares with a sibling", body_code(r) == 200,
      detail_message(r))
check("the ORDER LINE survives, because the sibling still carries it",
      one("SELECT is_deleted FROM consignment_order_items WHERE id = %s", widget_b) is False)
check("and the allocation fell to the sibling's share alone",
      one("SELECT allocated_quantity FROM consignment_order_items WHERE id = %s",
          widget_b) == Decimal("20.000"),
      str(one("SELECT allocated_quantity FROM consignment_order_items WHERE id = %s", widget_b)))
check("editing batch 1 did not disturb the sibling's line",
      one("""SELECT quantity FROM consignment_items
              WHERE consignment_id = %s AND order_item_id = %s
                AND is_deleted = false""", second_id, widget_b) == Decimal("20.000"))


#===========================================================================
# 7. THE LOWER BOUNDS
#===========================================================================

print("\n== 7. The lower-bound constraints ==")

# BOTH COLUMNS MOVED TOGETHER, so `allocated <= ordered` still HOLDS (-1 <= -1)
# and only the new lower bounds can be what rejects it. Setting one alone is
# caught by ck_allocation_within_order instead, which proves nothing about the
# constraints this change added.
try:
    cur.execute("UPDATE consignment_order_items "
                "SET ordered_quantity = -1, allocated_quantity = -1 WHERE id = %s",
                (widget_a,))
    check("a negative quantity pair is rejected by the database", False,
          "the UPDATE was accepted")
except Exception as e:                                         # noqa: BLE001
    check("a negative quantity pair is rejected by the database",
          "non_negative" in str(e), str(e).splitlines()[0][:140])

# And each bound on its own, against a row where the upper bound cannot be what
# fires: allocated = -1 with ordered = 0 satisfies `allocated <= ordered`.
try:
    cur.execute("UPDATE consignment_order_items "
                "SET ordered_quantity = 0, allocated_quantity = -1 WHERE id = %s",
                (widget_a,))
    check("a negative allocated_quantity alone is rejected", False,
          "the UPDATE was accepted")
except Exception as e:                                         # noqa: BLE001
    check("a negative allocated_quantity alone is rejected",
          "ck_order_item_allocated_quantity_non_negative" in str(e),
          str(e).splitlines()[0][:140])


print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
if FAILS:
    print("FAILED:\n  " + "\n  ".join(FAILS))
raise SystemExit(1 if FAILS else 0)
