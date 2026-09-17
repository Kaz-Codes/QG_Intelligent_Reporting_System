"""Addenda — amendments to the LC. Step 9 part 2.

An addendum is stored, displayed, and WIRED INTO NOTHING. That is the whole
design of this change, and it is the kind of constraint that decays quietly: the
next person to read `PaymentAddendum.value` sees a money column sitting beside a
consignment total and adds one line.

`TestNothingIsWiredIntoTheArithmetic` BELOW IS WHAT STOPS THAT, AND IT IS MEANT
TO BE DELETED ONE DAY. When the arithmetic is deliberately wired up — the LC
value becoming "the original plus the live addenda" — this class fails, and that
failure is the change asking to be confirmed rather than a regression. Delete it
in that change, in the same commit, having read this paragraph. Do not weaken
it: a test loosened until it passes records nothing.

WHAT THIS FILE CANNOT COVER, stated rather than implied. "Consignment total" and
"Outstanding" as an operator reads them on Step 4 are computed in the BROWSER
(`schema.ts`'s `foreignTotal` / `paidTotal` / `unpaidTotal`), and this project
has no frontend test runner. So those two figures are pinned by the browser
drive in the step 9 part 2 report, not here. What IS here is every backend
figure — the stored totals and the export's — plus the structural fact that
nothing on the addendum path can reach them.
"""

from decimal import Decimal

import pytest

from app.imports.helpers import new_addenda_to_add, recompute_derived
from app.imports.schemas import ConsignmentAddendumSchema
from app.imports.routes.export_consignments import _payment_total, _payment_count

from conftest import Obj, item


def d(v):
    return Decimal(str(v))


def addendum(value=None, bank_charges=None, deleted=False, id=None):
    return Obj(id=id, value=value, bank_charges=bank_charges, is_deleted=deleted)


def order(*addenda, payments=(), rate="280"):
    return Obj(exchange_rate=d(rate) if rate else None,
               addenda=list(addenda), payments=list(payments))


def consignment(group, *lines):
    return Obj(items=list(lines), batch_group=group,
               foreign_total=None, pkr_total=None, batch_sequence=1)


def payment(value, deleted=False):
    return Obj(value=d(value), is_deleted=deleted)


# --------------------------------------------------------------------------
# The constraint
# --------------------------------------------------------------------------

class TestNothingIsWiredIntoTheArithmetic:
    """Three addenda summing to a large number change no stored figure."""

    def lines(self):
        return [item(quantity=d("5"), unit_price=d("10"))]      # 50 foreign

    def test_the_foreign_total_ignores_addenda(self):
        bare = consignment(order(), *self.lines())
        loaded = consignment(
            order(addendum(value=d("1000000")), addendum(value=d("250000")),
                  addendum(value=d("-90000"))),
            *self.lines(),
        )
        recompute_derived(bare)
        recompute_derived(loaded)
        assert bare.foreign_total == d("50")
        assert loaded.foreign_total == bare.foreign_total

    def test_the_pkr_total_ignores_them_too(self):
        """The one that would be expensive. `pkr_total` is STORED and read back
        by every dashboard, report and export — all agreeing, because they all
        read the same number. An addendum term added here is written once and
        then believed for ever (test_derived_totals.py's reasoning)."""
        bare = consignment(order(), *self.lines())
        loaded = consignment(order(addendum(value=d("1000000"))), *self.lines())
        recompute_derived(bare)
        recompute_derived(loaded)
        assert bare.pkr_total == d("14000.00")                  # 50 x 280
        assert loaded.pkr_total == bare.pkr_total

    def test_BANK_CHARGES_ON_AN_ADDENDUM_ENTER_NO_TOTAL_EITHER(self):
        """THE ONE THAT DOES NOT LOOK LIKE A MISTAKE.

        `bankChargesTotal` already exists on Step 4 and payment bank charges
        genuinely do carry into actual landed cost — so summing an addendum's
        charges with them is a reasonable-looking one-line change that would
        restate a printed figure. An addendum's charges are a cost of AMENDING
        the LC, not of settling it.
        """
        bare = consignment(order(), *self.lines())
        loaded = consignment(
            order(addendum(value=d("0"), bank_charges=d("75000"))),
            *self.lines(),
        )
        recompute_derived(bare)
        recompute_derived(loaded)
        assert loaded.foreign_total == bare.foreign_total
        assert loaded.pkr_total == bare.pkr_total

    def test_the_exports_payment_total_ignores_them(self):
        """The export is the other stored-figure surface: a column summed in
        Excel by somebody who will never see this file."""
        with_addenda = Obj(batch_sequence=1, batch_group=order(
            addendum(value=d("1000000")), addendum(value=d("-400000")),
            payments=[payment("1500")],
        ))
        without = Obj(batch_sequence=1,
                      batch_group=order(payments=[payment("1500")]))
        assert _payment_total(with_addenda) == _payment_total(without) == 1500.0
        assert _payment_count(with_addenda) == _payment_count(without) == 1

    def test_a_DELETED_addendum_changes_nothing_either(self):
        """Stated separately because "it is excluded from the total" and "there
        is no total" are different facts, and only the second one is true."""
        c = consignment(order(addendum(value=d("999"), deleted=True)), *self.lines())
        recompute_derived(c)
        assert c.foreign_total == d("50")


# --------------------------------------------------------------------------
# The signed delta
# --------------------------------------------------------------------------

class TestValueIsASignedDelta:
    """`value` is the CHANGE to the LC amount, not the revised total."""

    def test_a_REDUCTION_is_accepted(self):
        """The trap that copying `ConsignmentPaymentSchema` would have walked
        into: its `value` is `Field(None, gt=0)`, which rejects every reduction
        addendum — the exact case a signed delta exists to record. The front end
        has its own copy of this trap (`optionalNumber` is `.nonnegative()`),
        caught separately in `schema.ts`."""
        assert ConsignmentAddendumSchema(value=d("-2500")).value == d("-2500")

    def test_an_increase_is_accepted(self):
        assert ConsignmentAddendumSchema(value=d("2500")).value == d("2500")

    def test_zero_is_accepted(self):
        """An amendment that moves a date or a description and not the money.
        `gt=0` would have rejected this one too."""
        assert ConsignmentAddendumSchema(value=d("0")).value == d("0")

    def test_bank_charges_stay_non_negative(self):
        """Signedness is about `value` alone. A charge is a cost; a negative one
        is not something this records, so `ge=0` stays."""
        with pytest.raises(Exception):
            ConsignmentAddendumSchema(bank_charges=d("-1"))

    def test_the_ORDER_of_addenda_cannot_matter(self):
        """WHY A DELTA RATHER THAN A REVISED TOTAL, expressed as arithmetic.

        Nothing sums these yet, so this asserts the PROPERTY the column design
        buys rather than a code path: deltas commute and survive a deletion,
        while revised totals depend on which row is newest and break when a
        middle row is soft-deleted. When the wiring lands, this is the invariant
        it has to keep.
        """
        deltas = [d("1000"), d("-250"), d("80")]
        assert sum(deltas) == sum(reversed(deltas))
        assert sum(deltas) - deltas[1] == sum(deltas[:1] + deltas[2:])


# --------------------------------------------------------------------------
# The payload diff
# --------------------------------------------------------------------------

class TestNewAddendaToAdd:

    def test_a_row_with_no_id_is_new(self):
        posted = Obj(addenda=[Obj(id=None), Obj(id=7)])
        assert [a.id for a in new_addenda_to_add(posted)] == [None]

    def test_an_absent_collection_is_not_a_crash(self):
        """`addenda` defaults to `[]` on the schema, but an older client posts
        no key at all and `None` is what arrives."""
        assert new_addenda_to_add(Obj(addenda=None)) == []
