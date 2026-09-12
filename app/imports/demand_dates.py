"""When a batch was NEEDED — the one definition, in both languages.

THE PROBLEM THIS SOLVES

`required_date` used to be a header column: one consignment, one date. Under
batching it is a fact about the DEMAND, so it lives on the order item
(`consignment_order_items.required_date`) and a batch carrying three lines can
have three different ones. Everything that measures delay still needs ONE date
per batch, because delay is a comparison between two dates and a column cannot
show three.

THE RULE, from design section 6 Q2: the EARLIEST required date across that
batch's live lines, ignoring lines that carry none.

Earliest rather than latest because the figure exists to say *"something in here
is late"*, and the first date to pass is the first thing that is late. A batch
with one line needed in March and one in July is late from March.

WHY IT IS A MODULE AND NOT A ONE-LINER REPEATED ELEVEN TIMES

Eleven call sites read this, across the imports dashboard, the overview, the
overview's reference lists and the consignment serializer. CLAUDE.md is largely
a record of what happens when one metric is written twice: two dead-stock
definitions, two runway formulas, two procurement defaults — *"and neither
number was wrong for its own formula, which is what makes that class of bug
expensive: both screens looked right"*. Four of the eleven sites decide window
MEMBERSHIP and two more drive the Delayed tile, so a second spelling here would
not just restate a number, it would change which records a period contains.

TWO FORMS, DELIBERATELY, AND THEY MUST AGREE

Some callers are SQL aggregates that never build an object; others walk lines
already loaded in memory. Rather than force one shape on both — a subquery per
row, or a full load for an aggregate — this module provides both and pins them
to the same sentence. `tests/test_demand_dates.py` asserts they agree.
"""

from sqlalchemy import func, select

from app.imports.models import Consignment, ConsignmentItem, ConsignmentOrderItem


#-------------------------------------------------------------------
# THE SQL FORM
#
# A correlated scalar subquery, so it drops into a SELECT list, a WHERE or an
# ORDER BY against `consignments` without the caller having to join anything.
# Correlated on Consignment, so wherever `consignments` is already in the query
# this resolves per row.
#
# NOTE it reads through consignment_items rather than straight from
# consignment_order_items. Both are needed: the order item says what was needed
# and when, and the LINE says which batch was allocated against it. Going
# straight to the order items would give every batch of an order the same date -
# the order's earliest - rather than the earliest of the lines THIS batch
# actually carries.
#-------------------------------------------------------------------

EARLIEST_REQUIRED_DATE = (
    select(func.min(ConsignmentOrderItem.required_date))
    .select_from(ConsignmentItem)
    .join(ConsignmentOrderItem,
          ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
    .where(ConsignmentItem.consignment_id == Consignment.id)
    .where(ConsignmentItem.is_deleted.is_(False))
    .where(ConsignmentOrderItem.is_deleted.is_(False))
    .correlate(Consignment)
    .scalar_subquery()
)


#-------------------------------------------------------------------
# THE PYTHON FORM
#
# For callers that already hold the consignment with its lines loaded - the
# imports dashboard's delay calculations and the serializer. Issuing the
# subquery above per row instead would be an N+1 across the whole filtered set.
#
# The callers are responsible for the eager load
# (selectinload(Consignment.items).joinedload(ConsignmentItem.order_item));
# without it this function still returns the right answer and does it one query
# per line, which is the failure mode to watch for rather than a wrong number.
#-------------------------------------------------------------------

def earliest_required_date(consignment):
    """The earliest required date across a batch's live lines, or None."""
    dates = [
        line.order_item.required_date
        for line in (consignment.items or [])
        if not line.is_deleted
        and line.order_item is not None
        and not line.order_item.is_deleted
        and line.order_item.required_date is not None
    ]

    return min(dates) if dates else None


def line_required_date(line):
    """One LINE's own required date - no aggregate, and no fallback.

    For the per-line views (the expanded item panel, the reports row). A line
    whose order item carries no date has none; substituting the batch's earliest
    would attribute a demand to a line that never had it.
    """
    order_item = getattr(line, "order_item", None)
    return order_item.required_date if order_item is not None else None


def line_requisition_date(line):
    """One LINE's own requisition date.

    NO AGGREGATE EXISTS FOR THIS ONE, deliberately (design section 3.3).
    `required_date` needs a batch-level answer because the delay column is a
    header-level comparison that has to show a single number. Requisition date
    has no such consumer - it is a filter and a display, and both are better per
    line - so nothing here computes a batch-level version and nothing should.
    """
    order_item = getattr(line, "order_item", None)
    return order_item.requisition_date if order_item is not None else None
