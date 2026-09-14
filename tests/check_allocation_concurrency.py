"""Two operators allocating the last of a quantity at the same moment.

    DB_NAME=scratch_x python -m uvicorn app.main:app --port 8011
    DB_NAME=scratch_x python tests/check_allocation_concurrency.py

THE FAILURE THIS IS ABOUT

Order 250. Batch 1 holds 100, batch 2 holds 50. Two operators each raise their
own batch to 150 at the same moment, under Postgres' default READ COMMITTED:

    A reads the order's lines: 100 (its own, becoming 150) + 50 committed = 200
      -> 200 <= 250, writes allocated_quantity = 200
    B reads:                   100 committed + 50 (its own, becoming 150) = 200
      -> 200 <= 250, writes allocated_quantity = 200
    both commit. The real allocation is 300 against an order for 250.

`ck_allocation_within_order` passes both times, because each transaction
checked a figure it computed from a snapshot taken before the other wrote. And
the row lock Postgres takes on its own is not enough: both UPDATE the same
order line, so the WRITES serialise, but the COMPUTATION does not - B's number
was worked out in Python before it ever touched that row.

WHY THIS FILE RECONSTRUCTS THE UNLOCKED CODE INSTEAD OF FLAGGING IT OFF

A test for a lock is worthless if it cannot fail. The obvious way to make it
able to fail is a `use_lock=False` parameter on the real function - and that is
exactly the thing this project has twice recorded as a mistake: a parameter
that exists only for a test is a parameter production code can pass, and a
branch nothing exercises in anger.

So PART 1 below reproduces the OLD SHAPE locally - the same flush, the same
aggregate, the same write, with no `SELECT ... FOR UPDATE` - and drives the
race against it. It must and does end with 300 allocated against an order for
250, silently. PART 2 runs the identical scenario through the real
`reconcile_allocation` and requires that one of the two is refused.

If part 1 ever stops reproducing the corruption, this file has stopped testing
anything and says so rather than passing quietly.

SAFETY: scratch databases only, enforced before the first statement.
"""

import os
import sys
import threading
import time
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, select                                # noqa: E402

from tests.batch_fixture import _require_scratch, client, connect  # noqa: E402

_require_scratch(os.getenv("DB_NAME"))

# EVERY MODEL MODULE, BEFORE ANY MAPPER IS USED. This script talks to the ORM
# directly - it needs transaction control that HTTP cannot give - so it has to
# register the same set `app.main` and `alembic/env.py` do. Without it the
# first query dies on `expression 'Supplier' failed to locate a name`, which
# reads like a race outcome and is not one.
import app.accounts.models          # noqa: E402,F401
import app.masters.models           # noqa: E402,F401
import app.imports.models           # noqa: E402,F401
import app.logistics.models         # noqa: E402,F401
import app.trucking.models          # noqa: E402,F401
import app.logs.models              # noqa: E402,F401
import app.reports.models           # noqa: E402,F401
import app.loading.schemas.stores_schemas  # noqa: E402,F401

from sqlalchemy.orm import configure_mappers                       # noqa: E402

from app.database import SessionLocal                              # noqa: E402
from app.imports.allocation import (                               # noqa: E402
    OverAllocation, allocation_totals, reconcile_allocation,
)
from app.imports.models import (                                   # noqa: E402
    Consignment, ConsignmentItem, ConsignmentOrderItem,
)

configure_mappers()

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


def body_code(r):
    try:
        return r.json().get("status_code")
    except Exception:
        return None


#===========================================================================
# THE SCENARIO, BUILT THROUGH THE REAL ROUTES
#
# Order 250 of one item; batch 1 keeps 100, batch 2 takes 50. 100 outstanding,
# which is less than the 100 the two saves are about to add between them - so
# either one alone is legal and both together are not. That is the only shape
# in which a lost update is distinguishable from an ordinary refusal.
#===========================================================================

def build_scenario(tag):
    supplier_id = one("SELECT id FROM suppliers WHERE is_active ORDER BY id LIMIT 1")

    r = c.post("/consignments/", json={
        "supplier_id": supplier_id,
        "instrument_number": f"RACE-{tag}",
        "payment_instrument": "LC",
        "currency": "USD",
        "exchange_rate": 280,
        "current_status": "TT/LC in Process",
        "items": [{"item_name": f"Race widget {tag}", "quantity": 250,
                   "unit_price": 1, "unit_of_measurement": "Pcs"}],
        "payments": [],
    })
    assert body_code(r) == 201, r.text
    order = r.json()["data"]
    first_id, group_id = order["id"], order["batch_group_id"]
    order_item_id = order["allocation"][0]["order_item_id"]

    # Free 150 by lowering batch 1 to 100.
    detail = c.get(f"/consignments/{first_id}").json()["data"]
    from tests.batch_fixture import _draft_from
    payload = _draft_from(detail)
    payload["items"][0]["quantity"] = 100
    r = c.put(f"/consignments/{first_id}", json=payload)
    assert body_code(r) == 200, r.text

    # Batch 2 takes 50 of it. 100 remains outstanding.
    r = c.post(f"/consignments/{first_id}/batches", json={
        "allocations": [{"order_item_id": order_item_id, "quantity": 50}],
    })
    assert body_code(r) == 201, r.text
    second_id = r.json()["data"]["batch"]["id"]

    line_1 = one("""SELECT id FROM consignment_items
                     WHERE consignment_id = %s AND is_deleted = false""", first_id)
    line_2 = one("""SELECT id FROM consignment_items
                     WHERE consignment_id = %s AND is_deleted = false""", second_id)

    return {
        "group_id": group_id, "order_item_id": order_item_id,
        "first_id": first_id, "second_id": second_id,
        "line_1": line_1, "line_2": line_2,
    }


def state(scenario):
    """What the database actually holds: the true sum, and the stored column."""
    true_sum = one("""
        SELECT COALESCE(SUM(i.quantity), 0) FROM consignment_items i
          JOIN consignments cc ON cc.id = i.consignment_id
         WHERE i.order_item_id = %s AND i.is_deleted = false
           AND cc.is_deleted = false""", scenario["order_item_id"])
    stored, ordered = None, None
    cur.execute("""SELECT allocated_quantity, ordered_quantity
                     FROM consignment_order_items WHERE id = %s""",
                (scenario["order_item_id"],))
    stored, ordered = cur.fetchone()
    return Decimal(true_sum), Decimal(stored), Decimal(ordered)


#===========================================================================
# PART 1 - THE UNLOCKED CODE, RECONSTRUCTED, AND THE RACE IT LOSES
#===========================================================================

def reconcile_WITHOUT_lock_compute(db, group_id):
    """The old shape, phase one: flush, then read the sum. NO `FOR UPDATE`.

    Deliberately identical to `reconcile_allocation` minus the one statement,
    so what the comparison isolates is the lock and not some other difference.
    """
    db.flush()
    return allocation_totals(db, group_id)


def reconcile_WITHOUT_lock_write(db, group_id, totals):
    """The old shape, phase two: check the figure computed above, then write it."""
    order_items = db.execute(
        select(ConsignmentOrderItem)
        .where(ConsignmentOrderItem.batch_group_id == group_id)
        .order_by(ConsignmentOrderItem.id)
    ).scalars().all()

    for order_item in order_items:
        allocated, _live = totals.get(order_item.id, (Decimal("0"), 0))
        if allocated > (order_item.ordered_quantity or Decimal("0")):
            raise OverAllocation([{
                "order_item_id": order_item.id, "item": order_item.item_name,
                "ordered": order_item.ordered_quantity, "allocated": allocated,
                "over": allocated - order_item.ordered_quantity,
            }])
        order_item.allocated_quantity = allocated


print("\n== Part 1: the race, against the unlocked shape ==")

scenario = build_scenario("NOLOCK")
before = state(scenario)
print(f"  set up: true sum {before[0]}, stored {before[1]}, ordered {before[2]}")

computed = [threading.Event(), threading.Event()]
outcomes = [None, None]


def racer_unlocked(index, line_id):
    """Raise this batch's line to 150, the old way.

    THE BARRIER IS THE POINT. Both transactions COMPUTE before either WRITES,
    which is the interleaving the survey described. Without it the second
    transaction would happen to run after the first had committed and would
    see the right number - the race is real but not every schedule hits it,
    and a test that relies on the scheduler is a test that passes by luck.
    """
    db = SessionLocal()
    try:
        line = db.get(ConsignmentItem, line_id)
        line.quantity = Decimal("150")

        totals = reconcile_WITHOUT_lock_compute(db, scenario["group_id"])
        computed[index].set()
        computed[1 - index].wait(timeout=30)

        reconcile_WITHOUT_lock_write(db, scenario["group_id"], totals)
        db.commit()
        outcomes[index] = "committed"
    except OverAllocation as e:                                   # noqa: BLE001
        db.rollback()
        outcomes[index] = f"refused: {e}"
    except Exception as e:                                        # noqa: BLE001
        db.rollback()
        outcomes[index] = f"error: {type(e).__name__}: {e}"
    finally:
        db.close()


threads = [
    threading.Thread(target=racer_unlocked, args=(0, scenario["line_1"])),
    threading.Thread(target=racer_unlocked, args=(1, scenario["line_2"])),
]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=60)

true_sum, stored, ordered = state(scenario)
print(f"  outcomes: {outcomes}")
print(f"  after: true sum {true_sum}, stored {stored}, ordered {ordered}")

check("PART 1: both unlocked saves were accepted",
      outcomes == ["committed", "committed"], str(outcomes))
check("PART 1: the order is OVER-ALLOCATED - 300 committed against 250",
      true_sum == Decimal("300") and ordered == Decimal("250"),
      f"{true_sum} against {ordered}")
# WHICH FIGURE SURVIVES IS UP TO THE SCHEDULER, so the assertion is about the
# disagreement rather than about a particular number. The two transactions
# compute DIFFERENT stale sums - one sees its own 150 against a committed 50,
# the other its own 150 against a committed 100 - and whichever writes last
# wins. What is invariant is that neither of them is 300.
check("PART 1: and the stored column does not know it - it disagrees with the lines",
      stored != true_sum,
      f"stored {stored}, true {true_sum} - the losing save's contribution "
      f"vanished from the column while its line stayed in the table")
check("PART 1: so ck_allocation_within_order was satisfied throughout",
      stored <= ordered,
      f"the CHECK saw {stored} <= {ordered} and had no way to see the {true_sum}")

if FAILS:
    print("\n  Part 1 did not reproduce the corruption, so Part 2 proves nothing.")
    print("  Stopping rather than reporting a pass.")
    raise SystemExit(1)


#===========================================================================
# PART 2 - THE SAME RACE, THROUGH THE REAL LOCKED FUNCTION
#===========================================================================

print("\n== Part 2: the same race, through reconcile_allocation ==")

scenario = build_scenario("LOCKED")
before = state(scenario)
print(f"  set up: true sum {before[0]}, stored {before[1]}, ordered {before[2]}")

holding = threading.Event()
outcomes2 = [None, None]


def racer_locked(index, line_id, go_first):
    """Raise this batch's line to 150, through the real path.

    NO SYMMETRIC BARRIER HERE, and that is not a weaker test - it is the only
    schedule the lock permits. The first transaction takes the row lock and
    signals; the second cannot reach its own computation until the first has
    committed, so a barrier waiting for it would deadlock the test rather than
    the database. The `sleep` is what guarantees the second arrives while the
    first still holds the lock, which is the contention being tested.
    """
    db = SessionLocal()
    try:
        if not go_first:
            holding.wait(timeout=30)

        line = db.get(ConsignmentItem, line_id)
        line.quantity = Decimal("150")

        reconcile_allocation(db, scenario["group_id"])

        if go_first:
            holding.set()
            time.sleep(2)

        db.commit()
        outcomes2[index] = "committed"
    except OverAllocation as e:                                   # noqa: BLE001
        db.rollback()
        outcomes2[index] = f"refused: {e}"
    except Exception as e:                                        # noqa: BLE001
        db.rollback()
        outcomes2[index] = f"error: {type(e).__name__}: {e}"
    finally:
        db.close()


threads = [
    threading.Thread(target=racer_locked, args=(0, scenario["line_1"], True)),
    threading.Thread(target=racer_locked, args=(1, scenario["line_2"], False)),
]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=60)

true_sum, stored, ordered = state(scenario)
print(f"  outcomes: {outcomes2}")
print(f"  after: true sum {true_sum}, stored {stored}, ordered {ordered}")

check("PART 2: exactly one of the two saves succeeded",
      sorted(o.split(":")[0] for o in outcomes2) == ["committed", "refused"],
      str(outcomes2))
check("PART 2: the one that lost was REFUSED, not silently dropped",
      any(o.startswith("refused") for o in outcomes2), str(outcomes2))
check("PART 2: the refusal names the overage it would have caused",
      any("over by 50" in o for o in outcomes2),
      next((o for o in outcomes2 if o.startswith("refused")), ""))
check("PART 2: the order is NOT over-allocated",
      true_sum <= ordered, f"{true_sum} against {ordered}")
check("PART 2: the stored column agrees with the lines it is the sum of",
      stored == true_sum, f"stored {stored} vs true {true_sum}")
check("PART 2: and the accepted save did land - 150 + 50",
      true_sum == Decimal("200"), str(true_sum))


print(f"\n{len(PASSES)} passed, {len(FAILS)} failed")
if FAILS:
    print("FAILED:\n  " + "\n  ".join(FAILS))
raise SystemExit(1 if FAILS else 0)
