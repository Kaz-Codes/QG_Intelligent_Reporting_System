"""Payments belong to the ORDER — step 9, design §4.4.

Two rules with no database between them, both of which fail silently if they
break:

  * WHICH BATCH MAY EDIT STEP 4. The wizard disables the step on a later batch,
    but a disabled fieldset stops typing and not posting — the array still
    arrives. If this predicate goes wrong in the permissive direction, batch 3
    rewrites the order's payment history and the response is 200.
  * WHAT GOES IN THE ORPHANED `payments.consignment_id`. It is still NOT NULL
    until Revision B, so a wrong answer here is an insert failure on the first
    payment anybody records.

The revert path — `add_or_delete` and `revert_old_values` taking the owner
COLUMN rather than assuming `consignment_id` — needs a session and real rows,
so it is driven over HTTP instead (see the step 9 report). Named here so the
gap is deliberate rather than forgotten.
"""

from app.imports.helpers import (
    legacy_payment_consignment_id, payments_belong_to_this_batch,
)

from conftest import Obj


def batch(seq, deleted=False):
    return Obj(batch_sequence=seq, is_deleted=deleted)


def order(*batches, founding=21):
    group = Obj(id=21, batches=list(batches), founding_consignment_id=founding)
    return group


def consignment(seq, group):
    return Obj(batch_sequence=seq, batch_group=group)


#---------------------------------------------------------------------------
# Which batch owns Step 4
#---------------------------------------------------------------------------

class TestWhichBatchMayEditPayments:

    def test_an_unsplit_order_is_editable(self):
        """EVERY ORDER IN THE SYSTEM TODAY. Keying off `batch_sequence != 1`
        alone would be right on a split order and refuse payments on every
        single-batch one, which is nearly all of them."""
        g = order(batch(1))
        assert payments_belong_to_this_batch(consignment(1, g))

    def test_the_founding_batch_of_a_split_order_is_editable(self):
        g = order(batch(1), batch(2))
        assert payments_belong_to_this_batch(consignment(1, g))

    def test_a_LATER_batch_is_NOT(self):
        g = order(batch(1), batch(2))
        assert not payments_belong_to_this_batch(consignment(2, g))

    def test_the_third_batch_is_not_either(self):
        g = order(batch(1), batch(2), batch(3))
        assert not payments_belong_to_this_batch(consignment(3, g))

    def test_it_counts_LIVE_batches_not_batches_ever(self):
        """An order that split and then lost the second batch is back to one
        arrival, and Step 4 belongs to it again. `batches_ever` never
        decrements — numbers are permanent (§3.5a) — so counting it would
        refuse payments on the only batch left.

        IT PINS SOMETHING THE CODE NO LONGER SAYS OUT LOUD. There used to be an
        explicit `if len(live) <= 1: return True` short-circuit; ranking on the
        lowest live sequence subsumes it, which is cleaner and means the
        single-survivor case is now special-cased nowhere. This test is the only
        statement left that it must hold."""
        g = order(batch(1), batch(2, deleted=True))
        assert payments_belong_to_this_batch(consignment(1, g))

    def test_a_consignment_with_no_group_is_permissive(self):
        """Fail OPEN here, not closed: a batch with no order is a record being
        created, and refusing its payments would break the create path for a
        state that cannot persist anyway."""
        assert payments_belong_to_this_batch(Obj(batch_sequence=1, batch_group=None))

    def test_a_NULL_sequence_does_not_outrank_a_live_batch_1(self):
        """WHICH WAY THE DEFENCE FALLS, for a case the schema forbids.

        `batch_sequence` is `nullable=False` with a server default of 1 and a
        uniqueness constraint per group, and no row in the database is NULL — so
        a NULL can only come from an expired or detached in-session object. This
        pins which way that defence falls, and it falls AWAY from the batch with
        a real sequence.

        The old assertion was the reverse, under the name
        `..._is_read_as_the_founding_batch`, coercing NULL to 1. That is worse
        than it looks: coercing to 1 does not merely let a NULL outrank a real
        batch, it produces a TIE with live batch 1 — and a tie means BOTH own
        Step 4 (see the docstring), which puts two batches into one order's
        payment history. Ranking NULL last cannot produce that state at all."""
        g = order(batch(1), batch(2))
        assert not payments_belong_to_this_batch(consignment(None, g))

    def test_a_LONE_NULL_sequenced_batch_still_owns_step_4(self):
        """Where "an unknown sequence reads as founding" survives. With nothing
        real to outrank it, the NULL-sequenced batch is still the lowest live
        one — so the intent holds wherever it does not collide with a batch that
        has a sequence."""
        g = order(batch(None))
        assert payments_belong_to_this_batch(consignment(None, g))


class TestWhenTheFoundingBatchIsDeleted:
    """THE CASE THAT MADE THIS PREDICATE WRONG, and it is reachable.

    `delete_consignment` requires an admin and then soft-deletes whatever id it
    is given — no guard on the founding batch, no check that a later one
    survives — and nothing repoints `founding_consignment_id` afterwards
    (correctly: the consignment NUMBER derives from it, and §3.5a/A3 forbids
    renumbering a live order).

    So an order can have no live batch with sequence 1. Under the old
    `== 1` test that meant NO batch owned Step 4: the route ignored the payments
    array on every one of them and returned 200 having written nothing.
    """

    def test_one_survivor_owns_step_4(self):
        g = order(batch(1, deleted=True), batch(2))
        assert payments_belong_to_this_batch(consignment(2, g))

    def test_TWO_survivors_the_lowest_live_sequence_owns_it(self):
        """The case that was driven and found broken: PUT returned 200 and
        wrote zero payment rows on BOTH live batches."""
        g = order(batch(1, deleted=True), batch(2), batch(3))
        assert payments_belong_to_this_batch(consignment(2, g))

    def test_TWO_survivors_the_higher_one_does_NOT(self):
        g = order(batch(1, deleted=True), batch(2), batch(3))
        assert not payments_belong_to_this_batch(consignment(3, g))

    def test_a_deleted_MIDDLE_batch_is_skipped_too(self):
        """Founding deleted and the middle one deleted: the lowest LIVE
        sequence is 3, and it owns the step."""
        g = order(batch(1, deleted=True), batch(2, deleted=True), batch(3), batch(4))
        assert payments_belong_to_this_batch(consignment(3, g))
        assert not payments_belong_to_this_batch(consignment(4, g))

    def test_EVERY_batch_deleted_owns_nothing(self):
        """A group still marked alive with no live batch — reachable
        mid-transaction, before `sync_group_deleted_state` runs. There is no
        batch to own Step 4, and refusing a write to an order whose every
        shipment has been removed is the safe direction. Note this is the
        OPPOSITE answer from a consignment with no group at all, which is a
        record being created and must be able to record a payment."""
        g = order(batch(1, deleted=True), batch(2, deleted=True))
        assert not payments_belong_to_this_batch(consignment(1, g))
        assert not payments_belong_to_this_batch(consignment(2, g))


#---------------------------------------------------------------------------
# The orphaned column, until Revision B
#---------------------------------------------------------------------------

class TestTheLegacyConsignmentId:

    def test_it_is_the_orders_FOUNDING_batch(self):
        """Not the batch on screen. The founding one is what the order is named
        after everywhere else (`order_view.consignment_number_from`), so two
        payments recorded on one order from different batches agree about it."""
        assert legacy_payment_consignment_id(order(batch(1), founding=21)) == 21

    def test_it_does_not_depend_on_which_batch_is_open(self):
        g = order(batch(1), batch(2), founding=21)
        assert legacy_payment_consignment_id(g) == 21

    def test_no_group_yields_None_so_the_caller_falls_back(self):
        """The create path falls back to the consignment's own id — a brand-new
        record whose group is a line away from existing."""
        assert legacy_payment_consignment_id(None) is None
