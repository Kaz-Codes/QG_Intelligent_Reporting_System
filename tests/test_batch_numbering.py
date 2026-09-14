"""Numbering and ordered-quantity: the rules that need no database.

WHY THESE FOUR RULES AND NOT COVERAGE OF THE MODULE

Each one is a decision that is expensive to get wrong and cheap to get wrong
QUIETLY - no error, just a different number on a screen nobody is comparing:

  * A1 - a single batch keeps the plain number, and a split gives every batch a
    suffix. Getting this wrong renames 179 live records at once.
  * A3 - numbers never move and are never reused. Getting this wrong makes a
    number that has been on an invoice resolve to a DIFFERENT shipment, which
    is worse than one that resolves to nothing, because both parties believe
    they agree.
  * `resolve_ordered_quantity` - when the order quantity stops following the
    line. Getting this wrong lets a save of batch 2 restate what the whole
    order bought, on every save, silently.
  * `renumbering_note` - what the API tells a client about the renumbering it
    just caused. It is the only warning a user will get before a number they
    may have written down changes.

The locked allocation invariant is NOT here: it is about two transactions and
a row lock, which cannot be expressed without a database.
`tests/check_allocation_concurrency.py` reproduces it, and
`tests/check_batch_allocation.py` drives the refusals through the real routes.
"""

from decimal import Decimal

import pytest

from app.imports.allocation import (
    OrderLineHasNoQuantity, OverAllocation, UnknownOrderLine, plain,
)
from app.imports.order_view import consignment_number_from

from conftest import Obj


def d(value):
    return Decimal(str(value))


#---------------------------------------------------------------------------
# A1 and A3 - the suffix rule
#---------------------------------------------------------------------------

class TestTheSuffixRule:

    def test_a_single_batch_has_no_suffix(self):
        """A1. 179 live records are in this state; a suffix here renames them all."""
        assert consignment_number_from(177, 1, 1) == "177"

    def test_a_split_order_suffixes_every_batch(self):
        """A1. Including the FOUNDING one, which is the renumbering."""
        assert consignment_number_from(177, 2, 1) == "177-1"
        assert consignment_number_from(177, 2, 2) == "177-2"

    def test_the_number_is_the_FOUNDING_batch_id_not_the_row_s_own(self):
        """The distinction the whole function exists for.

        Batch 2 of order 177 has its own primary key - 184, say - and that
        integer belongs to no number anyone can look up. A display number
        derived from `consignment.id` is correct on every record that exists
        today and silently wrong on the first split.
        """
        assert consignment_number_from(177, 2, 2) == "177-2"
        assert "184" not in consignment_number_from(177, 2, 2)

    @pytest.mark.parametrize("sequence,expected", [(1, "177-1"), (3, "177-3")])
    def test_a_deleted_batch_leaves_a_GAP(self, sequence, expected):
        """A3. 177-2 deleted: 177-1 and 177-3 remain, and nothing slides down.

        `batches_ever` is 3 and stays 3 - it counts every batch the order has
        EVER held, so the surviving numbers do not move.
        """
        assert consignment_number_from(177, 3, sequence) == expected

    def test_dropping_back_to_one_batch_does_NOT_restore_the_plain_number(self):
        """A3, the half that is easy to miss. Renumbering runs FORWARD ONLY.

        An order that split to two and then lost one keeps `177-1`. Reverting
        to a bare `177` would make a number that has been on paperwork mean
        something new - the same failure as reusing one, reached from the
        other direction.
        """
        assert consignment_number_from(177, 2, 1) == "177-1"

    def test_no_founding_id_renders_nothing_rather_than_guessing(self):
        assert consignment_number_from(None, 2, 1) == ""

    def test_a_missing_batches_ever_is_read_as_one(self):
        """Defensive, because the column is NOT NULL but old in-session copies
        can be expired: a missing count must never invent a suffix."""
        assert consignment_number_from(177, None, 1) == "177"


#---------------------------------------------------------------------------
# When the order quantity stops following the line
#---------------------------------------------------------------------------

class TestResolveOrderedQuantity:

    def resolve(self, ordered, line_quantity, payload, batches_ever):
        from app.imports.helpers import resolve_ordered_quantity

        return resolve_ordered_quantity(
            Obj(ordered_quantity=ordered),
            Obj(quantity=line_quantity),
            payload,
            Obj(batches_ever=batches_ever),
        )

    def test_the_payload_wins_whenever_it_states_one(self):
        assert self.resolve(d(250), d(100), {"ordered_quantity": d(300)}, 2) == d(300)

    def test_the_payload_wins_even_on_a_single_batch_order(self):
        """Otherwise "the order is for 300, this batch brings 100" would be
        unsayable on an order that has not split yet."""
        assert self.resolve(d(250), d(100), {"ordered_quantity": d(300)}, 1) == d(300)

    def test_a_brand_new_order_line_takes_the_line_s_quantity(self):
        assert self.resolve(None, d(250), None, 1) == d(250)

    def test_a_single_batch_order_FOLLOWS_its_line(self):
        """The case every one of the 179 existing records is in.

        With one shipment, "what was ordered" and "what this carries" are the
        same quantity. This is what lets the current wizard keep working with
        no change: it posts `quantity` and no `ordered_quantity`, and an
        ordinary edit moves both.
        """
        assert self.resolve(d(250), d(300), None, 1) == d(300)

    def test_A_SPLIT_ORDER_DOES_NOT_FOLLOW_ITS_LINE(self):
        """The rule the whole function exists for.

        The wizard posts the whole draft back on every save. Without this,
        saving batch 2 - which carries 150 of an order for 250 - would restate
        the order as 150, silently, on every save.
        """
        assert self.resolve(d(250), d(150), None, 2) is None

    def test_nor_after_a_split_that_lost_a_batch(self):
        """`batches_ever` never decrements, so an order that has been split
        stays split for this purpose. It does not quietly start following the
        survivor again."""
        assert self.resolve(d(250), d(100), None, 2) is None

    def test_a_line_with_no_quantity_orders_zero_rather_than_NULL(self):
        """`ordered_quantity` is NOT NULL and a draft line can carry nothing -
        the same COALESCE the migration and the loader apply."""
        assert self.resolve(None, None, None, 1) == d(0)

    def test_an_explicit_zero_in_the_payload_is_honoured(self):
        """Not treated as absent. `0 or default` is the bug this guards: it is
        how a deliberate zero becomes whatever the fallback happened to be."""
        assert self.resolve(d(250), d(100), {"ordered_quantity": d(0)}, 2) == d(0)


#---------------------------------------------------------------------------
# What the API says about the renumbering it caused
#---------------------------------------------------------------------------

class TestRenumberingNote:

    def note(self, batches_ever, sequences):
        from app.imports.helpers import renumbering_note

        return renumbering_note(
            Obj(founding_consignment_id=177, batches_ever=batches_ever),
            [Obj(id=100 + s, batch_sequence=s) for s in sequences],
        )

    def test_the_split_reports_the_founding_batch_s_old_and_new_numbers(self):
        result = self.note(2, [1, 2])
        founding = next(b for b in result["batches"] if b["batch_sequence"] == 1)
        assert founding["previous_consignment_number"] == "177"
        assert founding["consignment_number"] == "177-1"

    def test_the_split_is_flagged(self):
        assert self.note(2, [1, 2])["siblings_renumbered"] is True

    def test_a_THIRD_batch_renumbers_nobody(self):
        result = self.note(3, [1, 2, 3])
        assert result["siblings_renumbered"] is False
        for batch in result["batches"]:
            if batch["batch_sequence"] < 3:
                assert batch["previous_consignment_number"] == batch["consignment_number"]

    def test_the_NEW_batch_reports_no_previous_number(self):
        """It had none. Reporting one would invite a client to render
        "177 is now 177-2" for a shipment that did not exist a moment ago."""
        result = self.note(2, [1, 2])
        new = next(b for b in result["batches"] if b["batch_sequence"] == 2)
        assert new["previous_consignment_number"] is None

    def test_a_gap_in_the_sequences_is_reported_as_it_stands(self):
        """177-2 deleted, then 177-4 added. The note must not renumber around
        the hole - see A3."""
        result = self.note(4, [1, 3, 4])
        assert [b["consignment_number"] for b in result["batches"]] == [
            "177-1", "177-3", "177-4",
        ]


#---------------------------------------------------------------------------
# The refusals a person has to read
#---------------------------------------------------------------------------

class TestTheRefusalMessages:
    """Each of these is something the operator can fix, so each must say what.

    Asserted because a refusal is the one output of this feature that a user
    reads word for word, and because `OrderLineHasNoQuantity` exists ONLY to
    carry its message - a bare rejection would leave somebody stuck in front
    of a line they are perfectly able to correct.
    """

    def test_over_allocation_names_the_item_the_figures_and_the_overage(self):
        message = str(OverAllocation([{
            "order_item_id": 7, "item": "Forged Steel Round Bar",
            "ordered": d(250), "allocated": d(300), "over": d(50),
        }]))
        assert "Forged Steel Round Bar" in message
        assert "250" in message and "300" in message
        assert "over by 50" in message

    def test_over_allocation_falls_back_to_the_id_when_the_item_is_unnamed(self):
        message = str(OverAllocation([{
            "order_item_id": 7, "item": None,
            "ordered": d(1), "allocated": d(2), "over": d(1),
        }]))
        assert "order line 7" in message

    def test_over_allocation_lists_EVERY_line_that_is_over(self):
        """Not just the first. A batch is saved whole, so an operator fixing
        one item at a time because the message only mentioned one would be
        made to submit as many times as they have bad lines."""
        message = str(OverAllocation([
            {"order_item_id": 1, "item": "A", "ordered": d(10),
             "allocated": d(11), "over": d(1)},
            {"order_item_id": 2, "item": "B", "ordered": d(20),
             "allocated": d(25), "over": d(5)},
        ]))
        assert "A" in message and "B" in message and "over by 5" in message

    def test_a_line_that_ordered_nothing_is_told_HOW_TO_FIX_IT(self):
        message = str(OrderLineHasNoQuantity([(451, "Widget")]))
        assert "Set the ordered quantity" in message

    def test_a_foreign_order_line_says_why_it_was_refused(self):
        message = str(UnknownOrderLine(99))
        assert "99" in message and "does not belong to this order" in message

    @pytest.mark.parametrize("value,expected", [
        (Decimal("250.000"), "250"),
        (Decimal("250.500"), "250.5"),
        (Decimal("1000.000"), "1000"),
        (Decimal("0.000"), "0"),
        (None, "0"),
    ])
    def test_quantities_are_printed_as_a_person_writes_them(self, value, expected):
        """`250.000` and `2.5E+2` are both what Decimal gives you and neither
        is what anyone would type. The 1000 case is the one that matters:
        `normalize()` turns it into `1E+3`."""
        assert plain(value) == expected
