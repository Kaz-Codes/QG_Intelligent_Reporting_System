"""Allocation - the invariant, and the lock that makes it one.

    allocated_quantity = SUM(quantity) over every LIVE line on every LIVE batch
                         of this order, per order line
    and it may never exceed ordered_quantity

THE DATABASE CANNOT ENFORCE THIS ON ITS OWN, and the design says so without
hedging (section 6, B3). A CHECK sees one row; the quantities being summed live
on `consignment_items` rows hanging off DIFFERENT `consignments`, and the limit
lives on a third table. SQL has no cross-row CHECK and no exclusion constraint
expresses a SUM.

So there are two layers, and neither of them is the client:

    Layer 1, the enforcement: this module. A row lock on the order lines, the
        sum read back OUT OF THE DATABASE afterwards, and a readable 422 naming
        the item and the overage.
    Layer 2, the backstop: `ck_allocation_within_order` on the denormalised
        column, which catches any path that skips layer 1 - the loaders
        included, since they bypass the ORM entirely and are exactly the kind of
        code that forgets.

AND LAYER 2 HAD NEVER REJECTED ANYTHING, for a structural reason worth
recording: until this change the only two writers set `allocated_quantity` and
`ordered_quantity` to the SAME value, so the constraint evaluated `q <= q` on
every row ever written. Measured before the change: 455 of 455 order items had
the two equal. A constraint that cannot fire is documentation until something
can make it fire, which is what this module is.

WHY ITS OWN MODULE. Same reason `order_view.py` is one: it imports models and
nothing else, so the routes, the helpers and anything later can all reach it
with no risk of the import cycle `serializers.py` already has to dodge by
importing `helpers` inside a function body.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.imports.models import (
    Consignment, ConsignmentItem, ConsignmentOrderItem,
)


#---------------------------------------------------------------------------
# THE REFUSALS
#
# Every one of these is something the operator can fix, so each carries a
# message saying what to do rather than only what went wrong.
#---------------------------------------------------------------------------

class AllocationError(Exception):
    """Base for the ways an allocation is refused."""

    status_code = 422


class OverAllocation(AllocationError):
    """More has been committed to batches than the order bought."""

    def __init__(self, overages):
        self.overages = overages
        parts = [
            f"{o['item'] or 'order line ' + str(o['order_item_id'])}: "
            f"{plain(o['allocated'])} allocated against {plain(o['ordered'])} "
            f"ordered (over by {plain(o['over'])})"
            for o in overages
        ]
        super().__init__(
            "More has been allocated than the order holds. " + "; ".join(parts)
        )


class OrderLineHasNoQuantity(AllocationError):
    """Allocating against a line that ordered nothing.

    NOT A BARE REFUSAL, deliberately. The two rows in this state are the
    migration's COALESCE rows - sheet lines that carried no quantity, not orders
    of zero - and since `ordered_quantity` is a schema field they can be
    corrected through the ordinary edit. A refusal that does not say so leaves
    the operator stuck in front of a line they are perfectly able to fix.
    """

    def __init__(self, lines):
        self.lines = lines
        names = ", ".join(
            (name or f"order line {line_id}") for line_id, name in lines
        )
        super().__init__(
            f"Nothing has been ordered on {names}, so there is nothing to "
            f"allocate. Set the ordered quantity on the item first, then create "
            f"the batch."
        )


class UnknownOrderLine(AllocationError):
    """A line pointed at an order line belonging to another order, or to none."""

    def __init__(self, order_item_id):
        self.order_item_id = order_item_id
        super().__init__(
            f"Order line {order_item_id} does not belong to this order. A batch "
            f"can only allocate against the items its own order bought."
        )


def plain(value):
    """A Decimal as a person writes it: 250, not 250.000 and not 2.5E+2."""
    if value is None:
        return "0"
    quantised = Decimal(value).normalize()
    if quantised == quantised.to_integral_value():
        quantised = quantised.quantize(Decimal(1))
    return f"{quantised:f}"


#---------------------------------------------------------------------------
# THE LOCK
#
# THE FAILURE IT PREVENTS, reasoned through in the survey and then REPRODUCED
# against unlocked code (tests/check_allocation_concurrency.py). Order 250;
# batch 1 holds 100 and batch 2 holds 50; two operators each raise their own
# batch to 150 at the same moment, under Postgres' default READ COMMITTED:
#
#   A reads the order's lines: 100 (its own, becoming 150) + 50 committed = 200
#     -> 200 <= 250, writes allocated_quantity = 200
#   B reads:                   100 committed + 50 (its own, becoming 150) = 200
#     -> 200 <= 250, writes allocated_quantity = 200
#   both commit. The real allocation is 300 against an order for 250.
#
# `ck_allocation_within_order` passes both times, because each transaction
# checked a figure it computed from a snapshot taken before the other wrote.
#
# THE ROW LOCK POSTGRES TAKES ON ITS OWN IS NOT ENOUGH. Both transactions
# UPDATE the same order line, so the WRITES serialise - B blocks until A
# commits. The COMPUTATION does not: B's number was worked out in Python before
# it ever touched that row, so B writes a stale figure over A's and the losing
# contribution simply disappears from the column while its line stays in the
# table. Drift AND over-allocation out of one race, with nothing raised.
#
# WHAT THIS DOES ABOUT IT:
#
#   1. SELECT ... FOR UPDATE on the order lines, BEFORE anything is read;
#   2. flush, so this session's own pending writes are visible to SQL;
#   3. re-read the sum FROM THE DATABASE - never from `consignment.items`,
#      which holds one batch's lines and can never see a sibling's.
#
# THE FLUSH COMES FIRST, AND THAT IS NOT INTERCHANGEABLE WITH LOCKING FIRST.
#
# Measured, by driving the create route: with the lock taken before the flush,
# a brand-new order's line rows DO NOT EXIST IN THE DATABASE YET, so
# `SELECT ... FOR UPDATE` matched nothing, the loop below ran over an empty
# list, and `allocated_quantity` was left at its server default of 0 on every
# line of every newly created order. Nothing raised; the very next save
# corrected it, so it looked fine from any test that did two saves. The detail
# payload reported "250 ordered, 0 allocated" on an order fully allocated to
# its only batch.
#
# LOCK ORDER IS STILL FIXED, and flushing first is what fixes it rather than
# what threatens it: THE GROUP ROW IS TAKEN BEFORE THE ORDER LINES, on every
# path. `claim_batch_sequence` (batch create) and `apply_group_updates` (an
# ordinary edit, and a revert) both run BEFORE this function is called, so
# their UPDATE on the group row lands in this flush - ahead of the
# `FOR UPDATE` below. Two concurrent transactions therefore take the two locks
# in the same order and cannot deadlock against each other.
#
# WHAT THE LOCK ITSELF STILL GUARANTEES, after the flush: the sum is read from
# the database AFTER it is held, so a second transaction blocks here and then
# sees the first one's committed lines rather than the snapshot it started
# from. That is the whole mechanism, and it is what
# tests/check_allocation_concurrency.py reproduces the absence of.
#
# `ORDER BY id` - two transactions touching order lines 5 and 7 in opposite
# orders would deadlock; ascending id is the cheapest total order available.
#
# THE WHOLE ORDER'S SET IS TAKEN, not only the lines being written, because a
# save can add and remove lines and so change which order lines are involved
# halfway through. One acquisition, up front, covering everything the
# transaction could touch.
#
# THE COST, STATED PLAINLY: locking the order's whole set serialises two
# batches of one order even when they touch different items. With ten to thirty
# users and a split that only happens by deliberate action, that is not a
# throughput concern, and the alternative is a second lock acquisition in an
# order nothing can bound.
#---------------------------------------------------------------------------

def lock_order_lines(db, group_id):
    """Take the row locks, in a fixed order, before any quantity is read.

    Returns the locked rows. Nothing in this module reads a quantity before
    this has been called, and the caller has already flushed - see above for
    why that order and not the other one.
    """
    return list(db.execute(
        select(ConsignmentOrderItem)
        .where(ConsignmentOrderItem.batch_group_id == group_id)
        .order_by(ConsignmentOrderItem.id)
        .with_for_update()
    ).scalars().all())


def allocation_totals(db, group_id):
    """The true allocation per order line, straight from SQL.

    Returns {order_item_id: (total, live_line_count)}.

    Two filters, and both matter:

      * `consignment_items.is_deleted = false` - a removed line allocates
        nothing.
      * `consignments.is_deleted = false` - AND SO DOES A DELETED BATCH.
        Deleting a consignment sets the flag on the consignment alone and
        leaves its lines live (measured: 4 such lines in the restored
        database), so counting lines without asking about their batch would
        strand the quantity of every deleted batch for ever - allocated to a
        shipment nobody can see, and unavailable to the batch that replaces it.

    An order line with no live lines is ABSENT rather than zero, because
    "nothing allocated" and "no line left at all" are different states and only
    the second retires the order line.
    """
    rows = db.execute(
        select(
            ConsignmentItem.order_item_id,
            func.coalesce(func.sum(func.coalesce(ConsignmentItem.quantity, 0)), 0),
            func.count(ConsignmentItem.id),
        )
        .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
        .join(ConsignmentOrderItem,
              ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
        .where(ConsignmentOrderItem.batch_group_id == group_id)
        .where(ConsignmentItem.is_deleted == False)   # noqa: E712
        .where(Consignment.is_deleted == False)       # noqa: E712
        .group_by(ConsignmentItem.order_item_id)
    ).all()

    return {oid: (Decimal(total), count) for oid, total, count in rows}


def reconcile_allocation(db, group_id):
    """Bring `allocated_quantity` back in step with the lines, or refuse.

    THE ONE WRITER of `allocated_quantity` and of an order line's `is_deleted`.
    Every path that can change what a batch carries ends here: create, update,
    batch creation, delete and undo-delete.

    Raises `OverAllocation` naming every line that is over and by how much.
    Returns the order's allocation, for the caller to publish.
    """
    # FLUSH, THEN LOCK, THEN READ - in that order, for the reasons above. The
    # session's own pending inserts and quantity changes have to be in the
    # database before either the lock or the aggregate can see them, and on a
    # create the order lines do not exist at all until this runs. Explicit
    # rather than left to autoflush: this is the statement whose correctness
    # depends on it.
    db.flush()

    locked = lock_order_lines(db, group_id)

    totals = allocation_totals(db, group_id)

    overages, summary = [], []

    for order_item in locked:
        allocated, live_lines = totals.get(order_item.id, (Decimal("0"), 0))
        ordered = order_item.ordered_quantity or Decimal("0")

        if allocated > ordered:
            overages.append({
                "order_item_id": order_item.id,
                "item": order_item.item_name,
                "ordered": ordered,
                "allocated": allocated,
                "over": allocated - ordered,
            })

        order_item.allocated_quantity = allocated

        # AN ORDER LINE OUTLIVES ANY ONE BATCH'S LINE. It is retired when the
        # last live line across the whole order goes, and comes back if one
        # returns - which is exactly what undoing a delete does. Mirroring the
        # line's own flag, which is what this used to do, meant removing batch
        # 2's line retired the order line batch 1 was still pointing at.
        should_be_deleted = live_lines == 0
        if should_be_deleted != order_item.is_deleted:
            order_item.is_deleted = should_be_deleted
            order_item.deleted_at = (
                datetime.now(timezone.utc) if should_be_deleted else None
            )

        summary.append({
            "order_item_id": order_item.id,
            "item": order_item.item_name,
            "item_code": order_item.item_code,
            "unit_of_measurement": order_item.unit_of_measurement,
            "ordered_quantity": ordered,
            "allocated_quantity": allocated,
            "outstanding_quantity": ordered - allocated,
        })

    if overages:
        raise OverAllocation(overages)

    return summary


def allocation_view(group):
    """The order's allocation as it currently stands, for serialization.

    Read-only, and reads the order lines already loaded on the group rather
    than querying - so it costs nothing on a detail fetch. Not called from the
    list, which does not load them.
    """
    if group is None:
        return []

    out = []
    for order_item in sorted(group.order_items, key=lambda o: o.id):
        if order_item.is_deleted:
            continue
        ordered = order_item.ordered_quantity or Decimal("0")
        allocated = order_item.allocated_quantity or Decimal("0")
        out.append({
            "order_item_id": order_item.id,
            "item": order_item.item_name,
            "item_code": order_item.item_code,
            "unit_of_measurement": order_item.unit_of_measurement,
            "ordered_quantity": ordered,
            "allocated_quantity": allocated,
            "outstanding_quantity": ordered - allocated,
        })
    return out
