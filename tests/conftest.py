"""Shared fixtures and in-memory stand-ins for the unit tests.

NOTHING HERE TOUCHES THE DATABASE. Every function under test in this suite is
pure — it takes objects and returns or mutates values — so the tests build
plain Python objects rather than ORM rows. That is not a shortcut: it is what
makes the suite runnable on a machine with no database, and it is what keeps
it inside the CLAUDE.md rule that no test may write to an operational table.

The stand-ins deliberately carry ONLY the attributes the function under test
reads. A test that had to fill in thirty unrelated columns to check one sum
would stop being read as a statement about that sum.
"""

import sys
from pathlib import Path

# Runnable from the repo root the same way tests/check_dashboard_consistency.py
# is, so `pytest` needs no installed package or PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Obj:
    """A stand-in row: whatever keyword arguments it is given become attributes.

    Used instead of the real SQLAlchemy models because constructing one of
    those pulls in a metadata registry, a session and a live engine to do the
    work of a dict. The functions under test read attributes; this has
    attributes.
    """

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __repr__(self):
        shown = ", ".join(f"{k}={v!r}" for k, v in list(self.__dict__.items())[:4])
        return f"Obj({shown}…)"


# The thirteen fields that moved to the ORDER LINE in part 4. A stand-in has to
# model the same two-row shape the code now reads through, or a test passes
# against a structure production does not have.
ORDER_LINE_FIELDS = {
    "item_id", "item_code", "item_name", "placeholder_name", "specification",
    "hs_code", "unit_price", "unit_of_measurement", "requisition_type",
    "reference_number", "job_number", "mo_number", "description",
}


def item(**overrides):
    """A consignment line and the order line above it, as ONE set of keywords.

    Callers still write `item(unit_price=d("10"))` because that is how the field
    reads to a person. Where the value is STORED changed in part 4, so this
    splits the keywords across the two rows and hangs the order line off
    `order_item` - which is exactly what `line_unit_price()` and the rest of
    app/imports/order_view.py walk.

    Defaults matter here: a test for "missing quantity" should say exactly
    that and nothing else, which means every OTHER field has to already be
    valid. Each test overrides the one field it is about.
    """
    base = dict(
        is_deleted=False,
        item_name="Servo drive",
        item_code="3218-60",
        quantity=None,
        unit_of_measurement="Pcs",
        unit_price=None,
        requisition_type="Store",
        reference_number="REF-1",
        job_number=None,
        mo_number=None,
        description=None,
        elc=None,
        alc=None,
        variance_absolute=None,
        variance_percentage=None,
    )
    base.update(overrides)

    order_line = {k: base.pop(k) for k in list(base) if k in ORDER_LINE_FIELDS}
    order_line.setdefault("is_deleted", base.get("is_deleted", False))

    return Obj(order_item=Obj(**order_line), **base)


# The ten shared values that moved to the batch GROUP, plus branch_id, which
# moved AND was renamed to works_branch_id.
GROUP_FIELDS = {
    "supplier_id", "origin", "currency", "consignment_type", "incoterm",
    "payment_instrument", "instrument_number", "exchange_rate",
    "rate_booked_on", "rate_source",
}


def consignment(**overrides):
    """A consignment header, defaulted to a live, open, mid-pipeline record."""
    base = dict(
        id=1,
        branch_id=1,
        supplier_id=1,
        origin="China",
        currency="USD",
        items=[],
        payment_instrument="LC",
        instrument_number="LC-0001",
        works="QCL",
        exchange_rate=None,
        rate_booked_on="2026-01-01",
        current_status="In Transit",
        etd=None,
        eta=None,
        foreign_total=None,
        pkr_total=None,
        # The two state flags. They are independent now: `is_closed` tests the
        # status alone, and `record_state` says only that a user marked the
        # record finished. Defaults match what a fresh record carries.
        record_state="draft",
        is_locked=False,
    )
    base.update(overrides)

    # The ORDER above the batch. The same split one level up: supplier,
    # currency and the booked rate are the order's, and order_view.py reads
    # them through `batch_group`.
    group = {k: base.pop(k) for k in list(base) if k in GROUP_FIELDS}
    if "branch_id" in base:
        group["works_branch_id"] = base.pop("branch_id")
    group.setdefault("is_deleted", False)

    return Obj(batch_group=Obj(**group), **base)


def package(**overrides):
    """A logistics package, for the packing-cost rollup."""
    base = dict(
        gross_weight=None,
        quoted_packing_cost=None,
        actual_packing_cost=None,
    )
    base.update(overrides)
    return Obj(**base)
