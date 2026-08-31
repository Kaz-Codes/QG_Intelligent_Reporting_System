"""The threshold scanner's crossing logic.

THE RULE THIS PINS: threshold events fire on the CROSSING, not on the
CONDITION. "Below reorder level" stays true until somebody restocks, so a
scanner that emitted whenever the condition held would emit on all 96 passes a
day, for every affected item, for as long as the situation lasted. Tens of
thousands of notifications for a handful of real facts, and the channel is
dead inside a week.

That makes this the highest-consequence pure logic in the notification
subsystem: a regression here is not an error message, it is a flood, and the
only symptom is that people stop reading their notifications.

SCOPE NOTE. The transition RULE is pure and fully covered below. The check
functions that apply it (check_below_reorder, check_stockout, ...) are not
testable here — see test_scanner_db_bound_note at the bottom for exactly why
and what would have to change.
"""

from decimal import Decimal

from conftest import Obj  # noqa: F401  (imported for the path bootstrap)

from app.notifications.scanner import (
    ABOVE,
    ALERTING_STATES,
    BELOW,
    CLEAR,
    CRITICAL_RANKS,
    IN_STOCK,
    OPEN,
    OUT,
    REORDER_HYSTERESIS,
    _crossing_state,
    _dedupe_key,
    _effective_reorder_level,
    _state_key_from_dedupe,
)
from app.dashboard.inventory.calculations import (
    MOVE_DEAD,
    MOVE_FAST,
    MOVE_SLOW,
    derive_movement,
)


def d(value):
    return Decimal(str(value))


class TestCrossingDetection:
    """_crossing_state(stored, entering, leaving, alert_state, clear_state)."""

    def test_above_to_below_emits(self):
        assert _crossing_state(ABOVE, True, False, BELOW, ABOVE) == BELOW

    def test_below_to_below_does_NOT_emit(self):
        # The whole point. The condition still holds; nothing changed.
        assert _crossing_state(BELOW, True, False, BELOW, ABOVE) is None

    def test_first_ever_observation_already_over_the_line_counts_as_a_crossing(self):
        # No stored state means never observed, not "was fine". An item that is
        # already below reorder the first time it is scanned is news.
        assert _crossing_state(None, True, False, BELOW, ABOVE) == BELOW

    def test_recovery_is_recorded_but_is_a_different_state(self):
        # Recovering is not news, but it must be WRITTEN, or the next dip
        # would not read as a crossing.
        assert _crossing_state(BELOW, False, True, BELOW, ABOVE) == ABOVE

    def test_recovery_from_an_already_clear_state_is_a_no_op(self):
        assert _crossing_state(ABOVE, False, True, BELOW, ABOVE) is None

    def test_neither_entering_nor_leaving_changes_nothing(self):
        # This is the hysteresis band: below the recovery line but above the
        # trigger line, an item matches neither test and holds its state.
        assert _crossing_state(BELOW, False, False, BELOW, ABOVE) is None
        assert _crossing_state(ABOVE, False, False, BELOW, ABOVE) is None
        assert _crossing_state(None, False, False, BELOW, ABOVE) is None

    def test_the_same_rule_serves_the_other_state_pairs(self):
        # One rule, three vocabularies — stockout and the open-request checks
        # must not grow their own copy of it.
        assert _crossing_state(IN_STOCK, True, False, OUT, IN_STOCK) == OUT
        assert _crossing_state(OUT, True, False, OUT, IN_STOCK) is None
        assert _crossing_state(CLEAR, True, False, OPEN, CLEAR) == OPEN
        assert _crossing_state(OPEN, True, False, OPEN, CLEAR) is None


class TestHysteresisBand:
    """An item sitting on its reorder point must not re-alert every pass.

    Crossing DOWN happens at the reorder level; the state only resets to
    "above" once the item clears reorder_level * REORDER_HYSTERESIS. Between
    the two it keeps whatever state it had.
    """

    LEVEL = d(100)

    def band_top(self):
        return self.LEVEL * REORDER_HYSTERESIS

    def state_for(self, available, stored):
        """Mirrors what check_below_reorder computes, on plain numbers."""
        is_below = available < self.LEVEL
        recovered = available > self.band_top()
        return _crossing_state(stored, is_below, recovered, BELOW, ABOVE)

    def test_the_band_is_five_percent(self):
        assert REORDER_HYSTERESIS == d("1.05")
        assert self.band_top() == d(105)

    def test_dropping_below_the_line_alerts(self):
        assert self.state_for(d(99), ABOVE) == BELOW

    def test_inside_the_band_holds_the_alerting_state(self):
        # 100..105 — recovered past the trigger but not past the reset line.
        for available in (d(100), d(101), d(104), d(105)):
            assert self.state_for(available, BELOW) is None, available

    def test_dipping_below_again_from_inside_the_band_stays_silent(self):
        # The flap this exists to stop: issue two, drop below; receive three,
        # rise into the band; repeat all day. Only the first drop is news.
        assert self.state_for(d(99), BELOW) is None

    def test_clearing_the_band_resets_silently(self):
        assert self.state_for(d(106), BELOW) == ABOVE

    def test_after_a_reset_the_next_drop_alerts_again(self):
        assert self.state_for(d(99), ABOVE) == BELOW

    def test_exactly_on_the_band_top_does_not_reset(self):
        # `>` not `>=`: 105.00 is the edge of the band, not past it.
        assert self.state_for(self.band_top(), BELOW) is None


class TestCriticalRanks:
    """Only rank A and B are worth interrupting anybody about.

    C is the DEFAULT rank — the source workbook lists only A and B — so
    treating C as critical would alert on everything the workbook never
    mentioned, which in the current data is 5,735 of 6,098 stock rows.
    """

    def test_rank_c_is_not_critical(self):
        assert "C" not in CRITICAL_RANKS

    def test_a_and_b_are_critical(self):
        assert "A" in CRITICAL_RANKS
        assert "B" in CRITICAL_RANKS

    def test_only_two_ranks_qualify(self):
        assert set(CRITICAL_RANKS) == {"A", "B"}


class TestStockoutMovementGate:
    """Zero of something nobody issues is not news.

    check_stockout only alerts when derive_movement says the item is Fast or
    Slow. derive_movement is the shared definition the Inventory dashboard and
    the Overview were deliberately unified onto, so these tests pin the GATE,
    not a second copy of the classification.
    """

    ALERTS_ON = (MOVE_FAST, MOVE_SLOW)

    def test_an_item_issued_recently_is_fast_and_alerts(self):
        movement = derive_movement(d(10), d(50), available_qty=d(0))
        assert movement == MOVE_FAST
        assert movement in self.ALERTS_ON

    def test_an_item_issued_within_the_year_is_slow_and_alerts(self):
        movement = derive_movement(d(0), d(50), available_qty=d(0))
        assert movement == MOVE_SLOW
        assert movement in self.ALERTS_ON

    def test_an_item_with_no_issuance_at_zero_stock_is_unclassified_and_is_skipped(self):
        # available <= 0 returns None BEFORE the Dead branch — an item with
        # nothing on the shelf has no stock to be dead.
        movement = derive_movement(d(0), d(0), available_qty=d(0))
        assert movement is None
        assert movement not in self.ALERTS_ON

    def test_a_dead_item_that_still_has_stock_is_not_a_stockout_candidate(self):
        movement = derive_movement(d(0), d(0), available_qty=d(500))
        assert movement == MOVE_DEAD
        assert movement not in self.ALERTS_ON

    def test_the_fast_slow_check_runs_BEFORE_the_zero_stock_branch(self):
        # This ordering is what makes the stockout gate work at all: a stockout
        # item has available_qty <= 0 by definition, so if the None branch came
        # first every stockout would be unclassified and nothing would ever
        # alert.
        assert derive_movement(d(5), d(5), available_qty=d(0)) == MOVE_FAST


class TestEffectiveReorderLevel:
    """Derived level first, stored column only as the fallback.

    Same precedence the Inventory dashboard's serializer applies. It matters:
    stock.reorder_level is 0 on every row in the current data, so a check
    judging by the raw column alone could never fire.
    """

    def test_the_derived_level_wins(self):
        levels = {("ITM1", "QCL"): d(250)}
        assert _effective_reorder_level(levels, "ITM1", "QCL", d(10)) == d(250)

    def test_falls_back_to_the_stored_column_when_not_derived(self):
        assert _effective_reorder_level({}, "ITM1", "QCL", d(10)) == d(10)

    def test_is_per_branch_not_per_item(self):
        # An item can be stocked at several branches with different demand.
        levels = {("ITM1", "QCL"): d(250), ("ITM1", "QEN"): d(9)}
        assert _effective_reorder_level(levels, "ITM1", "QEN", d(10)) == d(9)

    def test_none_from_both_sources_stays_none(self):
        assert _effective_reorder_level({}, "ITM1", "QCL", None) is None


class TestDedupeKeyRoundTrip:
    """The key encodes the state it was raised for, and reconcile_state reads
    it back out. Build and parse must stay inverses of each other."""

    import datetime as _dt
    DAY = _dt.date(2026, 8, 31)

    def test_round_trips_a_simple_key(self):
        key = _dedupe_key("imports.clearance_aging", "clearance_aging:168", self.DAY)
        assert _state_key_from_dedupe(key) == "clearance_aging:168"

    def test_round_trips_a_state_key_containing_colons(self):
        # Real keys carry branch names with punctuation.
        state_key = "stockout:22296-60:Qadri Brothers (Pvt.) Ltd. (Unit-II)"
        key = _dedupe_key("inventory.stockout", state_key, self.DAY)
        assert _state_key_from_dedupe(key) == state_key

    def test_the_grouped_key_parses_to_something_that_matches_no_state(self):
        key = _dedupe_key("inventory.stockout", "grouped", self.DAY)
        assert _state_key_from_dedupe(key) == "grouped"

    def test_a_malformed_key_returns_none_rather_than_raising(self):
        assert _state_key_from_dedupe("") is None
        assert _state_key_from_dedupe(None) is None
        assert _state_key_from_dedupe("nocolons") is None


class TestAlertingStates:
    def test_only_the_alerting_half_of_each_pair_qualifies(self):
        # reconcile_state resets these and only these: a cleared state claims
        # no event needs to exist for it.
        assert set(ALERTING_STATES) == {BELOW, OUT, OPEN}
        for cleared in (ABOVE, IN_STOCK, CLEAR):
            assert cleared not in ALERTING_STATES


def test_scanner_db_bound_note():
    """The check functions themselves are NOT covered, deliberately.

    check_below_reorder, check_stockout and the six others each run a query and
    then call _commit_crossings -> emit(). emit() opens its OWN SessionLocal
    and commits, by design, so that a notification failure can never roll back
    the caller's business transaction. That design is correct and is exactly
    what makes these untestable here: calling one would write real rows to
    notification_events, which the CLAUDE.md rule forbids, and a rolled-back
    outer transaction would NOT contain those writes because emit does not
    share it.

    What would make them testable, if you want that later: let emit be injected
    or patched at the module boundary, so a test could pass a collector instead
    of the real one and assert on what WOULD have been raised. That is a
    production change and is not made here.

    Everything the checks decide WITH is covered above: the transition rule,
    the hysteresis band, the rank filter, the movement gate and the reorder
    level. What is not covered is the SQL that feeds them.
    """
    assert True
