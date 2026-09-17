"""The group freeze — design §3.9.

WHAT THIS GUARDS. A batch closing settles the ORDER's terms, because money has
moved against them. The failure it prevents is not a crash: it is the group
saying rate 281.00 while a closed batch's stored `pkr_total` was computed at
278.50, with nothing on screen to say which basis a given number came from.

WHY IT NEEDS PINNING RATHER THAN DRIVING ALONE. The refusal is a predicate over
a set of field names, and the two ways it can go wrong are both silent: a field
missing from a tier is editable when it should not be, and a payload key that
does not route to its column is never tested at all. Neither shows up as an
error — the save returns 200. The HTTP checks drive the paths; these pin the
rule itself, including the two coverage facts the survey measured, which no
HTTP assertion can see.

No database: every function here takes objects and returns values.
"""

import pytest

from app.imports import helpers as h
from app.imports.helpers import (
    ADMIN_FROZEN, HARD_FROZEN, FREEZE_EXEMPT_GROUP_COLUMNS, GroupFrozenError,
    PAYLOAD_TO_GROUP, assert_group_writable, freezing_batch, frozen_columns_for,
    frozen_violations, group_is_frozen,
)

from conftest import Obj


ARRIVED = "Arrived at Works"
OPEN = "In Transit"


def batch(id, sequence, status=OPEN, deleted=False):
    return Obj(id=id, batch_sequence=sequence, current_status=status,
               is_deleted=deleted, batch_group=None)


def group(*batches, id=21):
    g = Obj(id=id, batches=list(batches), founding_consignment_id=id,
            batches_ever=len(batches))
    for b in batches:
        b.batch_group = g
    return g


ADMIN = Obj(id=1, is_admin=True)
CLERK = Obj(id=2, is_admin=False)


#---------------------------------------------------------------------------
# When a group is frozen at all
#---------------------------------------------------------------------------

class TestWhenAGroupFreezes:

    def test_an_order_whose_batches_are_all_open_is_not_frozen(self):
        assert not group_is_frozen(group(batch(21, 1), batch(186, 2)))

    def test_ONE_closed_batch_freezes_the_whole_order(self):
        """The rule is 'any batch', not 'every batch' — the point is that the
        money moved on the one that closed."""
        assert group_is_frozen(group(batch(21, 1, ARRIVED), batch(186, 2)))

    def test_a_later_batch_closing_freezes_it_too(self):
        assert group_is_frozen(group(batch(21, 1), batch(186, 2, ARRIVED)))

    def test_a_DELETED_closed_batch_does_not_freeze(self):
        """A soft-deleted batch is not a shipment that arrived."""
        assert not group_is_frozen(
            group(batch(21, 1, ARRIVED, deleted=True), batch(186, 2)))

    def test_a_CANCELLED_batch_does_not_freeze(self):
        """`is_closed` is the status 'Arrived at Works' and nothing else (rule
        8). The list's `is_truly_closed` also hides 'Order Cancelled', but that
        is a display rule, not a closing one — a cancelled order has not been
        reconciled against. Recorded in §3.9 as an open question; pinned here so
        the current answer is deliberate rather than incidental."""
        assert not group_is_frozen(group(batch(21, 1, "Order Cancelled")))

    def test_no_group_is_not_frozen(self):
        assert not group_is_frozen(None)

    def test_the_freezing_batch_is_the_EARLIEST_closed_one(self):
        """It is named in the refusal, so which one it is shows up on screen."""
        g = group(batch(21, 1, ARRIVED), batch(186, 2, ARRIVED))
        assert freezing_batch(g).id == 21


#---------------------------------------------------------------------------
# The two tiers
#---------------------------------------------------------------------------

class TestTheTwoTiers:

    def test_an_unfrozen_group_freezes_nothing_for_anyone(self):
        g = group(batch(21, 1))
        assert frozen_columns_for(g, CLERK) == frozenset()
        assert frozen_columns_for(g, ADMIN) == frozenset()

    def test_a_clerk_is_frozen_out_of_BOTH_tiers(self):
        g = group(batch(21, 1, ARRIVED))
        assert frozen_columns_for(g, CLERK) == HARD_FROZEN | ADMIN_FROZEN

    def test_AN_ADMIN_IS_STILL_FROZEN_OUT_OF_TIER_1(self):
        """The only rule in the application `is_admin` does not pass. A rate
        money has moved against is a historical fact, not a permission."""
        assert frozen_columns_for(group(batch(21, 1, ARRIVED)), ADMIN) == HARD_FROZEN

    def test_an_admin_may_write_tier_2(self):
        assert frozen_columns_for(group(batch(21, 1, ARRIVED)), ADMIN) \
            & ADMIN_FROZEN == frozenset()

    def test_a_missing_user_is_treated_as_NOT_admin(self):
        """Fail closed. A path that forgets to pass the user must refuse, not
        silently grant Tier 2."""
        assert frozen_columns_for(group(batch(21, 1, ARRIVED)), None) \
            == HARD_FROZEN | ADMIN_FROZEN


#---------------------------------------------------------------------------
# The coverage facts — measured in the survey, and silent if they break
#---------------------------------------------------------------------------

class TestCoverage:

    def test_the_tiers_cover_every_reachable_group_column_EXCEPT_THE_EXEMPT(self):
        """No gap and no overlap, over the columns the freeze governs.

        A column added to GROUP_SHARED_FIELDS without being placed in a tier
        would be editable on a closed order for ever, and nothing would say
        so — the save returns 200.

        THE EXEMPT SET IS SUBTRACTED, not special-cased. §3.9 exempts the
        payment process, so `insurance_amount` became payload-reachable in step
        9 while staying in neither tier — which is correct and which this
        assertion would otherwise have called a hole. Subtracting names the
        exemption rather than weakening the check: a column that is neither in
        a tier nor declared exempt still fails."""
        governed = set(PAYLOAD_TO_GROUP.values()) - FREEZE_EXEMPT_GROUP_COLUMNS
        assert (HARD_FROZEN | ADMIN_FROZEN) == governed

    def test_insurance_is_reachable_from_the_payload_AND_exempt(self):
        """Both halves matter. Reachable, or Step 4 cannot save it; exempt, or
        the freeze would lock the payment screen at exactly the point it starts
        being used (§3.9)."""
        assert "insurance_amount" in set(PAYLOAD_TO_GROUP.values())
        assert "insurance_amount" in FREEZE_EXEMPT_GROUP_COLUMNS

    def test_the_tiers_do_not_overlap(self):
        assert HARD_FROZEN & ADMIN_FROZEN == frozenset()

    def test_insurance_amount_is_in_NEITHER_tier(self):
        """§3.9: the payment process does not freeze — an LC is retired AFTER
        the goods arrive. It is unreachable from the payload today, so nothing
        can write it; step 9 wires it up, and an implementation of 'deny every
        group write for non-admins' would freeze it by accident."""
        assert "insurance_amount" not in (HARD_FROZEN | ADMIN_FROZEN)
        assert "insurance_amount" in FREEZE_EXEMPT_GROUP_COLUMNS


#---------------------------------------------------------------------------
# Payload keys, not column names
#---------------------------------------------------------------------------

class TestKeysAreRoutedNotCompared:

    def test_branch_id_is_tested_against_works_branch_id(self):
        """THE HOLE THIS CLOSES. The wizard posts `branch_id`; the column is
        `works_branch_id`. Comparing the posted key against a set of column
        names matches nothing, and the works field would stay editable on a
        closed order while every other Tier 2 field refused."""
        g = group(batch(21, 1, ARRIVED))
        assert frozen_violations(g, CLERK, ["branch_id"]) == ["branch_id"]

    def test_the_violation_is_reported_under_the_key_that_was_SENT(self):
        """So the front end can disable the input it actually has."""
        g = group(batch(21, 1, ARRIVED))
        assert "works_branch_id" not in frozen_violations(g, CLERK, ["branch_id"])

    def test_a_key_that_is_not_a_group_field_is_never_a_violation(self):
        g = group(batch(21, 1, ARRIVED))
        assert frozen_violations(g, CLERK, ["eta", "remarks", "current_status"]) == []

    def test_an_unfrozen_group_reports_no_violations(self):
        assert frozen_violations(group(batch(21, 1)), CLERK,
                                 ["exchange_rate", "supplier_id"]) == []


#---------------------------------------------------------------------------
# The refusal
#---------------------------------------------------------------------------

class TestTheRefusal:

    def test_a_permitted_write_raises_nothing(self):
        assert_group_writable(group(batch(21, 1)), CLERK, ["exchange_rate"])

    def test_tier_1_refuses_a_clerk(self):
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED)), CLERK,
                                  ["exchange_rate"])
        assert e.value.tier == "hard"

    def test_TIER_1_REFUSES_AN_ADMIN(self):
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED)), ADMIN,
                                  ["exchange_rate"])
        assert e.value.tier == "hard"

    def test_tier_2_refuses_a_clerk(self):
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED)), CLERK,
                                  ["supplier_id"])
        assert e.value.tier == "admin"

    def test_tier_2_PERMITS_an_admin(self):
        assert_group_writable(group(batch(21, 1, ARRIVED)), ADMIN, ["supplier_id"])

    def test_tier_1_is_reported_in_preference_when_a_payload_carries_both(self):
        """It is the refusal with no way round it, so it is the one to read
        first — telling an admin 'ask an admin' would be worse than useless."""
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED)), CLERK,
                                  ["supplier_id", "exchange_rate"])
        assert e.value.tier == "hard"
        assert e.value.fields == ["exchange_rate"]

    def test_the_message_NAMES_THE_FIELD_not_the_column(self):
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED)), CLERK,
                                  ["branch_id"])
        assert "works / branch" in str(e.value).lower()
        assert "works_branch_id" not in str(e.value)

    def test_the_message_NAMES_THE_BATCH_that_froze_it(self):
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED), batch(186, 2)),
                                  CLERK, ["exchange_rate"])
        assert "21-1" in str(e.value)

    def test_the_tier_1_message_says_an_admin_cannot_help(self):
        with pytest.raises(GroupFrozenError) as e:
            assert_group_writable(group(batch(21, 1, ARRIVED)), ADMIN,
                                  ["currency"])
        assert "admin" in str(e.value).lower()

    def test_it_is_423_not_403(self):
        """423 is what the row lock returns, so the front end's existing
        'this record is closed' handling applies unchanged."""
        assert GroupFrozenError(["currency"], "hard").status_code == 423


#---------------------------------------------------------------------------
# The second line of defence
#---------------------------------------------------------------------------

class TestTheSetattrGuard:

    def diff(self, **fields):
        return {k: {"old_value": None, "new_value": v} for k, v in fields.items()}

    def test_apply_group_updates_refuses_a_frozen_field_on_its_own(self):
        """It RE-DERIVES the answer rather than trusting the caller — the route
        check has already run, and this is what catches a seventh write path
        that forgets it. §4.7 records six found one at a time, four by driving."""
        g = group(batch(21, 1, ARRIVED))
        with pytest.raises(GroupFrozenError):
            h.apply_group_updates(self.diff(exchange_rate=281), g, CLERK)

    def test_it_RAISES_rather_than_dropping_the_field(self):
        """A silent skip is the failure this rule exists to prevent wearing the
        costume of a safety net: the save would return 200 and the operator
        would believe the rate had changed."""
        g = group(batch(21, 1, ARRIVED))
        g.exchange_rate = 278.50
        with pytest.raises(GroupFrozenError):
            h.apply_group_updates(self.diff(exchange_rate=281), g, CLERK)
        assert g.exchange_rate == 278.50

    def test_nothing_is_written_when_ANY_field_is_frozen(self):
        """The check runs over the whole diff before the first setattr, so a
        refused save does not half-apply."""
        g = group(batch(21, 1, ARRIVED))
        g.origin, g.exchange_rate = "China", 278.50
        with pytest.raises(GroupFrozenError):
            h.apply_group_updates(self.diff(origin="Japan", exchange_rate=281), g, CLERK)
        assert g.origin == "China"

    def test_an_admin_writing_tier_2_gets_through_it(self):
        g = group(batch(21, 1, ARRIVED))
        h.apply_group_updates(self.diff(origin="Japan"), g, ADMIN)
        assert g.origin == "Japan"

    def test_branch_id_is_written_to_works_branch_id(self):
        """The guard must not have broken the rename it guards."""
        g = group(batch(21, 1))
        h.apply_group_updates(self.diff(branch_id=7), g, CLERK)
        assert g.works_branch_id == 7
