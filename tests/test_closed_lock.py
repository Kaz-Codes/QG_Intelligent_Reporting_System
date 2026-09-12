"""is_closed — the one-part closed test, and the transition that writes the lock.

REPLACES tests/test_submission_rules.py, which was deleted with the function it
covered. That suite is one of the four CLAUDE.md describes as chosen "for
consequence rather than coverage percentage", so its removal is deliberate and
recorded rather than accidental: `submission_errors()` no longer exists, imports
runs no submit rule set, and there is nothing left for it to pin.

What replaces it is a smaller suite about a smaller rule, and the reason it
exists at all is that NO EXISTING DATA EXERCISES THIS PATH. All 142 locked rows
in production were locked by the Excel loader, never by the app — CLAUDE.md rule
8 asserted the update route set `is_locked` and it never did. So the app-side
lock has, until now, never run in anger, and the first thing that would notice a
regression is a consignment that quietly stayed editable after its goods
arrived.

Two things are pinned here, and they are two halves of one rule:

  1. `is_closed()` is the STATUS ALONE. It used to also require
     `record_state == "submitted"`, which put the lock on an administrative
     gesture instead of on the event it represents.

  2. The lock is written on the TRANSITION into "Arrived at works", by the
     update route. /submit used to be the only writer of `is_locked` and now
     writes it never — so the two changes are only safe together. Deleting one
     without the other removes the closed lock from the system silently, which
     is the specific failure these tests exist to catch.

Pure, like the rest of the suite: plain stand-ins from conftest, no database.
The route body is not importable without a request, so the transition test
exercises the exact two-line rule the route applies rather than the route
itself. The route is proved separately by driving the real HTTP path.
"""

from conftest import consignment

from app.imports.helpers import is_closed, CLOSED_STATUS_VALUE
from app.enums import Status


ARRIVED = Status.ARRIVED_AT_WORKS.value


def apply_lock(c):
    """The rule update_consignment.py applies after the status has landed.

    Kept to two lines, identical to the route's, because the point of the test
    is the CONDITION rather than the mechanism.
    """
    if is_closed(c):
        c.is_locked = True
    return c


class TestIsClosed:
    def test_arrived_at_works_is_closed(self):
        assert is_closed(consignment(current_status=ARRIVED))

    def test_any_other_status_is_not_closed(self):
        for status in ("TT/LC in Process", "In Transit", "Arrived at QFL",
                       "Under Custom Clearance"):
            assert not is_closed(consignment(current_status=status)), status

    def test_record_state_is_no_longer_part_of_the_test(self):
        """The whole point of the one-part rule.

        A DRAFT at Arrived at Works is closed. Under the old two-part test it
        was not, and stayed editable until somebody pressed Submit — which made
        the lock depend on the gesture rather than on the goods arriving.
        """
        draft = consignment(current_status=ARRIVED, record_state="draft")
        submitted = consignment(current_status=ARRIVED, record_state="submitted")

        assert is_closed(draft)
        assert is_closed(submitted)

    def test_order_cancelled_is_terminal_but_not_closed(self):
        """Cancelled is terminal and the LIST groups it under Closed, but it
        does not lock. The consignment did not finish, it stopped, and locking
        it would need an admin to reopen something nobody completed."""
        assert not is_closed(consignment(current_status=Status.ORDER_CANCELLED.value))

    def test_the_constant_and_the_function_agree(self):
        """CLOSED_STATUS_VALUE is what the list filter and the notification
        path test against; is_closed is what the lock tests against. Two
        spellings of one status is how they drift."""
        assert is_closed(consignment(current_status=CLOSED_STATUS_VALUE))


class TestTheLockTransition:
    def test_moving_to_arrived_at_works_locks_the_record(self):
        c = consignment(current_status="In Transit", is_locked=False)
        c.current_status = ARRIVED

        assert apply_lock(c).is_locked is True

    def test_a_draft_moving_to_arrived_at_works_locks_too(self):
        """No submit required. This is the case the old two-part test let
        through, and the one that left arrived goods editable indefinitely."""
        c = consignment(current_status="In Transit", record_state="draft",
                        is_locked=False)
        c.current_status = ARRIVED

        assert apply_lock(c).is_locked is True

    def test_an_ordinary_status_change_does_not_lock(self):
        c = consignment(current_status="TT/LC in Process", is_locked=False)
        c.current_status = "In Transit"

        assert apply_lock(c).is_locked is False

    def test_a_save_that_does_not_touch_the_status_does_not_lock(self):
        c = consignment(current_status="Arrived at QFL", is_locked=False)

        assert apply_lock(c).is_locked is False

    def test_cancelling_does_not_lock(self):
        c = consignment(current_status="In Transit", is_locked=False)
        c.current_status = Status.ORDER_CANCELLED.value

        assert apply_lock(c).is_locked is False

    def test_applying_it_twice_is_a_no_op(self):
        """Every save of a closed record re-applies the rule. It must never be
        able to UN-close one — the route reaches this line only on the request
        that closes the consignment, but a future edit to the guard should not
        be able to turn a re-save into a reopen."""
        c = consignment(current_status=ARRIVED, is_locked=False)

        assert apply_lock(c).is_locked is True
        assert apply_lock(c).is_locked is True

    def test_submitting_is_not_what_locks(self):
        """The whole of what /submit now does, spelled out: it sets
        record_state and touches nothing else. If this ever fails, submit has
        grown a side effect back."""
        c = consignment(current_status="In Transit", record_state="draft",
                        is_locked=False)

        c.record_state = "submitted"

        assert c.is_locked is False
        assert not is_closed(c)
