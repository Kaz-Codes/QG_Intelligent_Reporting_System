"""Every query that names two tables must say how they join.

WHY THIS SUITE EXISTS

`consignment_order_items` was split out of `consignment_items` in part 4, and
three queries had their column names repointed onto the new table without a
join being added beside them. SQLAlchemy does not object: it puts the second
table in the FROM clause with no condition and emits a CARTESIAN PRODUCT.

    FROM consignment_items, consignment_order_items
   WHERE consignment_order_items.requisition_type IN (...)

Measured through the real route against a clone of production: the
requisition-type filter returned all 179 live consignments for BOTH types in
use, where the right answers are 1 and 0. The free-text search returned the
whole list for any term matching any item anywhere.

**THE RESPONSE BODY CANNOT SHOW THIS.** Both bugs returned 200 with a full page
of plausible consignments in it. A test that checks the status code passes; so
does one that checks "some rows came back"; so does one that checks the rows
are real consignments, because they are. Only two things catch it - comparing
the returned set against SQL (tests/… the HTTP checks do that), and reading the
compiled statement, which is what this file does.

This one is in the default pytest suite because it needs no database and no
login, so it is the one that actually fails on a later edit. It is deliberately
written against the SHAPE of the SQL rather than against a particular join
clause: any future correct spelling passes, and every cartesian product fails.
"""

import re

import pytest
from sqlalchemy import Select, select
from sqlalchemy.dialects import postgresql

# EVERY MODEL MODULE, BEFORE ANY MAPPER IS USED - and app.main is deliberately
# not how that is done: importing it opens a database connection and runs
# create_all. Same set app.main and alembic/env.py register, and nothing else.
import app.accounts.models          # noqa: F401
import app.masters.models           # noqa: F401
import app.imports.models           # noqa: F401
import app.logistics.models         # noqa: F401
import app.trucking.models          # noqa: F401
import app.logs.models              # noqa: F401
import app.reports.models           # noqa: F401
import app.loading.schemas.stores_schemas  # noqa: F401

from app.imports.models import (
    Consignment, ConsignmentBatchGroup, ConsignmentItem, ConsignmentOrderItem,
)


#-------------------------------------------------------------------
# READING A COMPILED STATEMENT FOR AN UNJOINED TABLE
#
# A cartesian product shows up in exactly one place: a FROM clause listing two
# tables separated by a comma, with no ON between them. Postgres' own syntax is
# what makes it detectable - `FROM a JOIN b ON ...` and `FROM a, b` are
# different strings, and only the second can fan out.
#
# Subqueries and correlated EXISTS each get their own FROM clause, so every one
# in the statement is checked, not just the outermost.
#-------------------------------------------------------------------

# `FROM <stuff>` up to the next clause keyword. Non-greedy, case-insensitive.
_FROM_CLAUSE = re.compile(
    r"\bFROM\b(.*?)(?=\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b"
    r"|\bLIMIT\b|\bOFFSET\b|\bUNION\b|\)|$)",
    re.IGNORECASE | re.DOTALL,
)


def from_clauses(stmt):
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    return [c.strip() for c in _FROM_CLAUSE.findall(sql)]


def comma_joined_tables(stmt):
    """Every FROM clause in `stmt` that lists two tables with no join condition.

    Returns the offending clauses, so a failure names the query rather than
    just asserting False.
    """
    bad = []
    for clause in from_clauses(stmt):
        # A comma at the top level of a FROM clause is an implicit cross join.
        # Commas inside parentheses (a function call, a VALUES list) are not,
        # so depth is tracked rather than splitting the string naively.
        depth, top_level_comma = 0, False
        for ch in clause:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                top_level_comma = True
        if top_level_comma:
            bad.append(" ".join(clause.split()))
    return bad


#-------------------------------------------------------------------
# THE THREE STATEMENTS, EXACTLY AS THE APP BUILDS THEM
#
# Imported from the code under test rather than retyped here. A copy would be a
# second spelling that agrees today and drifts later - which is the whole
# failure this file exists to catch, one level up.
#-------------------------------------------------------------------

def _list_statement(**kwargs):
    """The list query, captured off `fetch_consignments_page` without running it."""
    from app.imports.helpers import fetch_consignments_page

    captured = []

    class _Result:
        def scalar(self):
            return 0

        def scalars(self):
            return self

        def all(self):
            return []

    class _RecordingSession:
        def execute(self, stmt, *a, **kw):
            captured.append(stmt)
            return _Result()

    defaults = dict(
        include_deleted=False, include_closed=True, status=None, stage=None,
        branch_id=None, supplier_id=None, requisition_type=None,
        drafts_only=False, etd_from=None, etd_to=None, q=None,
        page=1, page_size=20,
    )
    defaults.update(kwargs)
    fetch_consignments_page(_RecordingSession(), **defaults)
    return captured


class TestTheListQuery:
    """`fetch_consignments_page` - the requisition filter and the search."""

    def test_requisition_type_filter_joins_the_order_line(self):
        for stmt in _list_statement(requisition_type=["Store"]):
            assert not comma_joined_tables(stmt), (
                "the requisition-type filter names consignment_order_items in a "
                "FROM clause with no join condition - it will match every "
                "consignment that has any line at all"
            )

    def test_free_text_search_joins_the_order_line(self):
        for stmt in _list_statement(q="shaft"):
            assert not comma_joined_tables(stmt), (
                "the search names consignment_order_items in a FROM clause with "
                "no join condition - it will return the whole list for any term "
                "that matches any item anywhere"
            )

    def test_both_filters_together(self):
        for stmt in _list_statement(requisition_type=["Store"], q="shaft"):
            assert not comma_joined_tables(stmt)

    def test_the_plain_list_is_clean_too(self):
        """The baseline, so a failure above is attributable to the filter."""
        for stmt in _list_statement():
            assert not comma_joined_tables(stmt)

    def test_the_requisition_filter_actually_constrains_the_order_line(self):
        """Not just joined - joined ON the column that links the two rows.

        A join on the wrong column would pass the cartesian check above while
        still being wrong, so the link condition is asserted by name.
        """
        sql = " ".join(
            str(s.compile(dialect=postgresql.dialect()))
            for s in _list_statement(requisition_type=["Store"])
        )
        assert "consignment_order_items.id = consignment_items.order_item_id" in sql \
            or "consignment_items.order_item_id = consignment_order_items.id" in sql

    def test_the_search_correlates_the_order_line_to_the_line(self):
        sql = " ".join(
            str(s.compile(dialect=postgresql.dialect()))
            for s in _list_statement(q="shaft")
        )
        assert "consignment_order_items.id = consignment_items.order_item_id" in sql \
            or "consignment_items.order_item_id = consignment_order_items.id" in sql


class TestTheFilterOptionsDropdown:
    """The requisition-type dropdown, which has to offer what the filter can return.

    The statement is rebuilt here rather than captured, because it is inline in
    a route body with authentication in front of it. The link condition is
    asserted by name for that reason - a retyped query that drifted from the
    route would pass the shape check while testing nothing, so the assertion is
    on the join being present AND on it being the right one.
    """

    def test_the_dropdown_query_joins(self):
        stmt = (
            select(ConsignmentOrderItem.requisition_type)
            .join(ConsignmentItem,
                  ConsignmentItem.order_item_id == ConsignmentOrderItem.id)
            .where(ConsignmentItem.is_deleted == False)  # noqa: E712
            .distinct()
        )
        assert not comma_joined_tables(stmt)

    def test_the_route_still_builds_it_that_way(self):
        """Reads the route's source, so the test above cannot drift from it."""
        import inspect

        import app.imports.routes.filter_options as mod

        source = inspect.getsource(mod.filter_options)
        block = source[source.index("requisition_types"):]
        block = block[:block.index("return")]
        assert ".join(" in block, (
            "filter_options' requisition-type query has lost its join - the "
            "dropdown will list types no live line carries"
        )


class TestTheDetectorItself:
    """A detector that cannot fail is worth nothing, so it is tested both ways.

    Every assertion above is of the form "no cartesian product found". That is
    the assertion shape most likely to pass because the detector is broken, so
    the broken query is reconstructed here and the detector must catch it.
    """

    def test_it_catches_the_original_requisition_bug(self):
        broken = select(ConsignmentItem.consignment_id).where(
            ConsignmentOrderItem.requisition_type.in_(["Store"])
        )
        assert comma_joined_tables(broken), (
            "the detector no longer recognises the exact statement this suite "
            "was written for"
        )

    def test_it_catches_the_original_search_bug(self):
        from sqlalchemy import or_

        broken = select(Consignment.id).where(
            Consignment.items.any(
                (ConsignmentItem.is_deleted == False) &  # noqa: E712
                or_(
                    ConsignmentOrderItem.item_name.ilike("%shaft%"),
                    ConsignmentOrderItem.item_code.ilike("%shaft%"),
                )
            )
        )
        assert comma_joined_tables(broken)

    def test_it_catches_the_original_dropdown_bug(self):
        broken = (
            select(ConsignmentOrderItem.requisition_type)
            .where(ConsignmentItem.is_deleted == False)  # noqa: E712
            .distinct()
        )
        assert comma_joined_tables(broken)

    def test_it_does_not_cry_wolf_on_a_correct_join(self):
        fine = (
            select(ConsignmentItem.consignment_id)
            .join(ConsignmentOrderItem,
                  ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
            .where(ConsignmentOrderItem.requisition_type.in_(["Store"]))
        )
        assert not comma_joined_tables(fine)

    def test_it_does_not_cry_wolf_on_a_nested_exists(self):
        fine = select(Consignment.id).where(
            Consignment.items.any(
                ConsignmentItem.order_item.has(
                    ConsignmentOrderItem.item_name.ilike("%shaft%")
                )
            )
        )
        assert not comma_joined_tables(fine)

    def test_it_does_not_cry_wolf_on_a_multi_column_select(self):
        """Commas in the SELECT list are not commas in the FROM clause."""
        fine = select(Consignment.id, Consignment.gd_number, Consignment.etd)
        assert not comma_joined_tables(fine)


class TestTheEagerLoads:
    """The order line is loaded with the shipment lines, not one query per line.

    `serialize_items` reads every line through `item.order_item`, so a missing
    chain here is invisible in the response and shows up only as latency.
    Measured before the fix: a 100-row list page emitted 254 statements, 248 of
    them one-per-line against consignment_order_items; after, 7 and 1.
    """

    @pytest.mark.parametrize("fn_name", ["fetch_consignment", "fetch_consignments_page"])
    def test_the_chain_is_declared(self, fn_name):
        import inspect

        import app.imports.helpers as helpers

        source = inspect.getsource(getattr(helpers, fn_name))
        assert "selectinload(Consignment.items).selectinload(ConsignmentItem.order_item)" \
            in " ".join(source.split()), (
                f"{fn_name} loads the lines but not the order lines behind them - "
                "every line will lazy-load its own"
            )

    def test_the_trucking_queue_chain_is_declared(self):
        import inspect

        import app.cross_module as cross

        source = " ".join(inspect.getsource(cross.derive_open_requests).split())
        assert "selectinload(Consignment.items) .selectinload(ConsignmentItem.order_item)" \
            in source or \
            "selectinload(Consignment.items).selectinload(ConsignmentItem.order_item)" \
            in source, (
                "_import_snapshot reads line_item_name / line_specification, which "
                "walk item.order_item - without the chain each line lazy-loads"
            )
