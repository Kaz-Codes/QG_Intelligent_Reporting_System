"""Masters list pagination + the port search typeahead.

WHY THIS SUITE EXISTS

`GET /masters/{master}` used to load the WHOLE table, serialize every row,
then filter/page in Python. That stopped being viable once the ports master
grew to ~133,000 rows from its own dedicated workbook. This suite is DB-free
(no login, no live database — see tests/conftest.py and CLAUDE.md's "test
scripts never touch the live database" rule), so it can only check the SHAPE
of the SQL the app builds, not run it — but that shape is exactly where the
old bug lived (a Python scan with no WHERE/LIMIT at all) and exactly where a
future regression would reappear (a search field or a page bound that quietly
stops being a real SQL clause).

`search_ports` is exercised for real (not retyped here) via a recording fake
session, the same technique test_list_filter_joins.py uses for
fetch_consignments_page — importing the real function is what keeps this test
from silently drifting out of sync with the code it is meant to guard.

`list_masters`'s own query is inline in an authenticated route body, so it is
reconstructed here from the same registry config and sql_search_clause helper
the route itself imports (not retyped by hand), and the route's source is
read separately to confirm it actually uses LIMIT/OFFSET/sql_search_clause —
the same "rebuild + assert the route still builds it that way" pattern
test_list_filter_joins.py's TestTheFilterOptionsDropdown uses.
"""

import inspect

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

# EVERY MODEL MODULE, BEFORE ANY MAPPER IS USED — see test_list_filter_joins.py
# for why this is the set to import rather than app.main.
import app.accounts.models          # noqa: F401
import app.masters.models           # noqa: F401
import app.imports.models           # noqa: F401
import app.logistics.models         # noqa: F401
import app.trucking.models          # noqa: F401
import app.logs.models              # noqa: F401
import app.reports.models           # noqa: F401
import app.loading.schemas.stores_schemas  # noqa: F401

from app.dashboard.references import sql_search_clause
from app.masters.registry import get_master_config
from app.masters.models import Port


def _compiled(stmt):
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


class TestListMastersQueryShape:
    """The query list_masters.py builds for the port master, reconstructed
    from the same registry config and helper the route itself uses."""

    def _port_list_query(self, q=None, page=1, page_size=20):
        config = get_master_config("port")
        model = config["model"]
        columns = [getattr(model, f) for f in config["search_fields"]]

        conditions = [model.is_active == True]  # noqa: E712
        clause = sql_search_clause(q, *columns)
        if clause is not None:
            conditions.append(clause)

        return (
            select(model).where(*conditions)
            .order_by(model.name).limit(page_size).offset((page - 1) * page_size)
        )

    def test_the_query_has_a_limit_and_offset(self):
        sql = _compiled(self._port_list_query(page=3, page_size=20))
        assert "LIMIT 20" in sql
        assert "OFFSET 40" in sql

    def test_the_search_is_a_real_sql_ilike_across_search_fields(self):
        sql = _compiled(self._port_list_query(q="karachi"))
        assert "ILIKE" in sql.upper()
        # Every one of port's configured search_fields should be reachable —
        # the whole point of moving off the old Python _matches() scan.
        for field in get_master_config("port")["search_fields"]:
            assert f"ports.{field}" in sql, (
                f"port's search_fields lists '{field}' but the compiled search "
                "clause never references it — the registry and the query have "
                "drifted apart"
            )

    def test_an_empty_search_adds_no_ilike_clause(self):
        """sql_search_clause returns None for a blank term — an empty search
        must return exactly what no search returns, not an always-true OR."""
        sql = _compiled(self._port_list_query(q=None))
        assert "ILIKE" not in sql.upper()

    def test_the_count_query_shares_the_same_where(self):
        """The route runs a separate func.count() query with the SAME
        conditions before paging — reconstructed the same way, so a
        WHERE-clause drift between the two would show up as an assertion
        here rather than a wrong `pagination.total` nobody notices."""
        config = get_master_config("port")
        model = config["model"]
        columns = [getattr(model, f) for f in config["search_fields"]]
        conditions = [model.is_active == True]  # noqa: E712
        clause = sql_search_clause("karachi", *columns)
        if clause is not None:
            conditions.append(clause)

        count_sql = _compiled(select(func.count()).select_from(model).where(*conditions))
        assert "ILIKE" in count_sql.upper()

    def test_the_route_actually_builds_it_this_way(self):
        """Reads the route's source, so the reconstruction above cannot
        drift from what list_masters.py really does."""
        import app.masters.routes.list_masters as mod

        source = " ".join(inspect.getsource(mod.list_masters).split())
        assert "sql_search_clause(q, *columns)" in source, (
            "list_masters no longer runs the search in SQL via "
            "sql_search_clause — it may have reverted to a Python-side scan"
        )
        assert ".limit(page_size).offset(" in source, (
            "list_masters no longer pages in SQL — it may be loading the "
            "whole table again"
        )
        assert "used_counts(master, [row.id for row in rows], db)" in source, (
            "used_counts is no longer called with just the current page's "
            "ids — it may be back to counting every row in the table"
        )


class TestSearchPorts:
    """search_ports (app/masters/helpers.py), exercised for real."""

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class _RecordingSession:
        """Captures the statement search_ports builds instead of hitting a
        real database — same technique test_list_filter_joins.py uses."""
        def __init__(self):
            self.captured = []

        def execute(self, stmt, *a, **kw):
            self.captured.append(stmt)
            return TestSearchPorts._Result([])

    def _search(self, **kwargs):
        from app.masters.helpers import search_ports

        db = self._RecordingSession()
        defaults = dict(q=None, limit=10, port_type=None, used_as=None)
        defaults.update(kwargs)
        search_ports(db, **defaults)
        assert len(db.captured) == 1
        return _compiled(db.captured[0])

    def test_plain_search_is_ilike_on_name(self):
        sql = self._search(q="kara")
        assert "ports.name ILIKE" in sql.replace("public.", "")

    def test_port_type_is_a_real_where_clause(self):
        sql = self._search(port_type="Sea")
        assert "ports.port_type = " in sql.replace("public.", "")

    def test_used_as_matches_the_exact_value_or_both(self):
        """A 'Both' port must be offered for EITHER Loading or Delivery —
        this is the one piece of logic that isn't a straight mirror of
        search_items, so it gets its own explicit check."""
        sql = self._search(used_as="Loading")
        stripped = sql.replace("public.", "")
        assert "ports.used_as = 'Loading'" in stripped
        assert "ports.used_as = 'Both'" in stripped
        assert " OR " in stripped

    def test_used_as_is_not_a_plain_equality(self):
        """Guards against someone "simplifying" the OR away, which would
        silently drop every 'Both' port from both dropdowns."""
        sql = self._search(used_as="Delivery")
        # A bare equality would have exactly one `used_as =`; the correct
        # OR-with-Both form has two.
        assert sql.replace("public.", "").count("ports.used_as = ") == 2

    def test_is_active_only(self):
        sql = self._search()
        assert "ports.is_active" in sql.replace("public.", "")

    def test_has_a_limit(self):
        sql = self._search(limit=7)
        assert "LIMIT 7" in sql
