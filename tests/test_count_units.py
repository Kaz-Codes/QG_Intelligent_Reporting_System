"""The fourteen count sites: does each one count BATCHES or ORDERS?

WHY THIS SUITE EXISTS, AND WHY IT LOOKS AT SQL RATHER THAN AT NUMBERS

A consignment used to BE an order. Under batching it is one shipment OF an
order, so an LC split across two arrivals is two `consignments` rows where it
was one. Every `count(Consignment.id)` in the app therefore has to say which
question it is answering — "how many arrivals" (count rows) or "how many LCs"
(count distinct `batch_group_id`) — and the answer is a judgement per site,
recorded in `docs/imports-batching-design.md` §3.2.

Getting one wrong is silent. The figure does not error, it just quietly means
something else, and every screen reading it agrees with every other screen
because they all read the same wrong number. CLAUDE.md is largely a record of
that failure mode.

**AND IT CANNOT BE CAUGHT BY LOOKING AT THE ANSWERS.** Every group in every
database today holds exactly one batch — revision A gave each existing
consignment a group of its own, and batch creation is step 7. So `count(rows)`
and `count(distinct group)` return the IDENTICAL number at all fourteen sites,
and an assertion on the figures passes whichever unit the code uses. A test
written that way would be the "both screens looked right" bug, inside the test
written to prevent it.

So this suite asserts the SQL, not the result. It runs each helper against a
recording session that captures the statements instead of executing them, then
compiles each one and reads what it counts. That is a claim about the code,
which is true today and stays checkable when the data changes.

The companion check is `tests/check_dashboard_consistency.py`, which builds a
real two-batch group in a scratch database and proves the screens reconcile.
That one needs a database and a login; this one needs neither, so this is the
one that runs in the default suite and actually fails on a later edit.

WHAT "ROWS" AND "GROUPS" COMPILE TO

    rows    ->  count(consignments.id)
    groups  ->  count(DISTINCT consignments.batch_group_id)
                or count(consignment_batch_groups.id), where the query has
                already moved onto the group table (masters supplier/branch)
"""

from datetime import date

import pytest
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

# EVERY MODEL MODULE, BEFORE ANY MAPPER IS USED — and app.main is deliberately
# NOT how that is done here. Importing app.main opens a database connection and
# runs create_all; this suite must stay pure, so it registers the same set of
# models app.main and alembic/env.py register, and nothing else. Without it,
# ConsignmentBatchGroup's relationship to User cannot resolve the name and every
# statement below fails at mapper configuration rather than on what it counts.
import app.accounts.models          # noqa: F401
import app.masters.models           # noqa: F401
import app.imports.models           # noqa: F401
import app.logistics.models         # noqa: F401
import app.trucking.models          # noqa: F401
import app.logs.models              # noqa: F401
import app.reports.models           # noqa: F401
import app.loading.schemas.stores_schemas  # noqa: F401


#-------------------------------------------------------------------
# A SESSION THAT RECORDS INSTEAD OF EXECUTING
#
# Every helper under test calls db.execute(stmt) and then unpacks the result.
# This returns a correctly-SHAPED empty answer so the Python after the query
# runs to completion, and keeps the statement.
#
# The arity of a .one() row is read off the statement itself rather than
# hard-coded per call site — otherwise adding a column to a query would break
# this file for a reason that has nothing to do with counting.
#-------------------------------------------------------------------

class _Result:
    def __init__(self, width):
        self._width = width

    def one(self):
        return tuple(0 for _ in range(self._width))

    def all(self):
        return []

    def scalar(self):
        return 0

    def scalar_one(self):
        return 0

    def scalar_one_or_none(self):
        return None

    def scalars(self):
        return self

    def unique(self):
        return self

    def first(self):
        return None


class RecordingSession:
    """Captures statements. Executes nothing, connects to nothing."""

    def __init__(self):
        self.statements = []

    def execute(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        width = 1
        if isinstance(stmt, Select):
            try:
                width = len(stmt.selected_columns)
            except Exception:
                width = 1
        return _Result(width)

    # Some helpers touch these; none of them matter to what is being asserted.
    def add(self, *a, **k):
        pass

    def flush(self, *a, **k):
        pass


def sql(stmt) -> str:
    """The statement as Postgres would see it, whitespace-normalised."""
    text = str(stmt.compile(dialect=postgresql.dialect()))
    return " ".join(text.split())


def counts_rows(stmt) -> bool:
    return "count(consignments.id)" in sql(stmt)


def counts_groups(stmt) -> bool:
    text = sql(stmt)
    return (
        # Two spellings, both accepted deliberately: `col.distinct()` emits the
        # DISTINCT keyword and `func.distinct(col)` emits a function call. They
        # are the same thing to Postgres, and this suite is asserting what is
        # COUNTED, not how the DISTINCT was spelled — over-specifying the syntax
        # would fail a correct implementation for a stylistic reason.
        "count(DISTINCT consignments.batch_group_id)" in text
        or "count(distinct(consignments.batch_group_id))" in text
        # Where the query has already moved onto the group table (masters
        # supplier / branch), a plain row count IS an order count.
        or "count(consignment_batch_groups.id)" in text
    )


def consignment_counting_statements(session):
    """Every captured statement that counts consignments one way or the other.

    A helper issues several queries and only some of them count; the rest
    (item counts, history counts, the page fetch) are not this suite's
    business and are filtered out here rather than by index, which would
    break the moment a query is added.
    """
    return [s for s in session.statements if counts_rows(s) or counts_groups(s)]


def only_statement(session):
    found = consignment_counting_statements(session)
    assert found, "no consignment-counting statement was issued at all"
    return found


WINDOW = (date(2026, 1, 1), date(2026, 12, 31))


def assert_all_rows(session, expected_count=None):
    found = only_statement(session)
    if expected_count is not None:
        assert len(found) == expected_count, (
            f"expected {expected_count} counting statements, got {len(found)}"
        )
    for stmt in found:
        assert counts_rows(stmt) and not counts_groups(stmt), sql(stmt)


#-------------------------------------------------------------------
# 1, 2 — dashboard/imports/helpers.py source_coverage
#
# ROWS. The coverage denominator has to be the population the screen shows,
# and the imports list shows one row per batch. Its own docstring says so.
#-------------------------------------------------------------------

class TestImportsSourceCoverage:
    def test_both_statements_count_rows(self):
        from app.dashboard.imports import helpers

        db = RecordingSession()
        helpers.source_coverage(db, *WINDOW)

        assert_all_rows(db, expected_count=2)


#-------------------------------------------------------------------
# 3 — whole/helpers.py imports_period_value
#
# ROWS on the tile, because VALUE is summed per batch row and a group count
# beside a row-summed value gives a false average. PLUS a group count
# published alongside, so a panel can say "2 batches across 1 order".
#-------------------------------------------------------------------

class TestOverviewPeriodValue:
    def test_the_tile_count_is_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_period_value(db, *WINDOW)

        assert any(counts_rows(s) for s in db.statements)

    def test_a_group_count_is_ALSO_published(self):
        """Both units, never one silently — CLAUDE.md's reference rule, one
        level up. This is an ADDED figure; it does not replace the tile's."""
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_period_value(db, *WINDOW)

        assert any(counts_groups(s) for s in db.statements), (
            "imports_period_value must publish the order count as well as the "
            "batch count"
        )


#-------------------------------------------------------------------
# 4 — whole/helpers.py imports_value_undated
#
# ROWS. It is the complement of #3's population: dated + undated has to add
# back to the total, which it cannot do in a different unit.
#-------------------------------------------------------------------

class TestOverviewValueUndated:
    def test_counts_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_value_undated(db)

        assert_all_rows(db)


#-------------------------------------------------------------------
# 5 — whole/helpers.py imports_date_coverage
#
# ROWS. A data-completeness ratio over the same population as #3.
#-------------------------------------------------------------------

class TestOverviewDateCoverage:
    def test_counts_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_date_coverage(db)

        assert_all_rows(db)


#-------------------------------------------------------------------
# 6 — whole/helpers.py imports_in_process_by_stage
#
# ROWS, and groups is not even expressible: status is per batch, so two
# batches of one LC are legitimately at different stages and the group has
# no single stage to be counted under.
#-------------------------------------------------------------------

class TestOverviewInProcessByStage:
    def test_counts_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_in_process_by_stage(db, *WINDOW)

        assert_all_rows(db)


#-------------------------------------------------------------------
# 7, 8 — whole/helpers.py shipments_handled
#
# ROWS, and this is the clearest case in the set: the figure's NAME is the
# unit. A batch is a shipment handled.
#-------------------------------------------------------------------

class TestShipmentsHandled:
    def test_the_unwindowed_totals_count_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.shipments_handled(db)

        assert_all_rows(db)

    def test_the_windowed_count_counts_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.shipments_handled(db, *WINDOW)

        assert_all_rows(db)


#-------------------------------------------------------------------
# 9 — whole/helpers.py imports_population
#
# ROWS on the tile: the in-process/arrived/cancelled buckets are status-keyed
# so they can only be rows (#6), and the total has to match its own buckets
# AND equal #3. PLUS the group count published alongside, as #3.
#-------------------------------------------------------------------

class TestOverviewPopulation:
    def test_the_tile_count_is_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_population(db, *WINDOW)

        assert any(counts_rows(s) for s in db.statements)

    def test_a_group_count_is_ALSO_published(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_population(db, *WINDOW)

        assert any(counts_groups(s) for s in db.statements), (
            "imports_population must publish the order count as well"
        )


#-------------------------------------------------------------------
# 10, 11 — whole/helpers.py imports_coverage
#
# ROWS. The Overview's twin of #1/#2, and it must agree with them.
#-------------------------------------------------------------------

class TestOverviewCoverage:
    def test_both_statements_count_rows(self):
        from app.dashboard.whole import helpers

        db = RecordingSession()
        helpers.imports_coverage(db, *WINDOW)

        assert_all_rows(db, expected_count=2)


#-------------------------------------------------------------------
# 12 — whole/references.py imports_delayed_references
#
# ROWS, because it has to TOTAL THE TILE IT DRILLS INTO (imports_delay, which
# is already row-shaped). A reference list reporting a different number from
# the KPI that opened it, with nothing saying why, is the exact failure
# app/dashboard/references.py's rules exist to prevent.
#-------------------------------------------------------------------

class TestDelayedReferences:
    def test_the_total_counts_rows(self):
        from app.dashboard.whole import references

        db = RecordingSession()
        references.imports_delayed_references(db, *WINDOW)

        assert_all_rows(db)


#-------------------------------------------------------------------
# 13 — imports/helpers.py fetch_consignments_page
#
# ROWS, and this one is FORCED rather than chosen: the number is the page
# count for the rows the query returns. Counting groups here would not merely
# report a different figure, it would break paging.
#-------------------------------------------------------------------

class TestListPagination:
    def test_the_page_total_counts_rows(self):
        from app.imports import helpers

        db = RecordingSession()
        helpers.fetch_consignments_page(
            db, include_deleted=False, include_closed=False, status=None,
            stage=None, branch_id=None, supplier_id=None, requisition_type=None,
            drafts_only=False, etd_from=None, etd_to=None, q=None,
            page=1, page_size=50,
        )

        assert_all_rows(db)


#-------------------------------------------------------------------
# 14 — masters/helpers.py used_counts
#
# THE ONLY SPLIT IN THE SET, and it is not a matter of taste: it follows from
# where each column now lives.
#
#   supplier  ->  GROUPS. supplier_id is on the group, so the query moves to
#                 consignment_batch_groups and counting its rows IS counting
#                 orders. "Used by N orders."
#   branch    ->  GROUPS, on group.works_branch_id. Splitting one LC must not
#                 inflate a branch's usage.
#   agent     ->  ROWS. clearing_agent_id stays PER BATCH, and an agent who
#                 cleared two batches of one LC did two clearances.
#                 Understating that in a deactivation guard fails in the
#                 DANGEROUS direction — it invites somebody to switch off an
#                 agent the business is still using.
#-------------------------------------------------------------------

class TestMastersUsedCounts:
    @pytest.mark.parametrize("master", ["supplier", "branch"])
    def test_supplier_and_branch_count_orders(self, master):
        from app.masters import helpers

        db = RecordingSession()
        helpers.used_counts(master, [1, 2, 3], db)

        found = [s for s in db.statements if "count(" in sql(s)]
        assert found, f"{master} issued no counting statement"
        for stmt in found:
            assert counts_groups(stmt), (
                f"{master} 'used in' must count ORDERS, not batches: {sql(stmt)}"
            )

    def test_clearing_agent_counts_batches(self):
        from app.masters import helpers

        db = RecordingSession()
        helpers.used_counts("agent", [1, 2, 3], db)

        found = [s for s in db.statements if "count(" in sql(s)]
        assert found, "agent issued no counting statement"
        for stmt in found:
            assert counts_rows(stmt) and not counts_groups(stmt), (
                "a clearing agent's usage is per BATCH — two batches of one LC "
                f"are two clearances: {sql(stmt)}"
            )
