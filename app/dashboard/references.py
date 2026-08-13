"""
THE RECORDS BEHIND A FIGURE — one shape, one pagination contract.

Every dashboard KPI can be opened to see the records it counted. Those lists are
COMPLETE: there is no hidden cap, because a truncated list quietly changes the
question from "which records is this number about" to "which records did we feel
like showing", and the user has no way to tell the difference.

Complete does not mean shipped all at once. Local procurement alone stands over
8,731 orders — 1.3 MB of JSON on a screen that reloads whenever a filter moves,
and 2.3 MB across the Overview's three biggest lists. So a dashboard payload
carries the TRUE TOTAL plus the first page, and the panel fetches further pages
from the module's `/references` endpoint as the user scrolls. Nothing is hidden;
it is just not all sent before anyone has asked to see it.

THE CONTRACT (`ReferenceSet` on the front end)

    {
      "total":     every record behind the figure, always the true count
      "unit":      what a row IS — "line", "consignment", "order", "item"
      "groups":    how many PARENTS those rows belong to (null when rows are
                   already the parent), plus "group_unit" naming them
      "page":      1-based
      "page_size": rows per page
      "pages":     how many pages `total` divides into
      "items":     THIS page's rows, each {id, reference, detail, meta, badge}
    }

A LIST NEVER HIDES LINES. Where a record has lines under it, the list shows the
LINES — a consignment with three shaft rows is three rows, not one. Folding them
up looks tidy and destroys the only view that explains the number: it was
exactly this that let payment ref 65704 show a single row for seven lines
arriving on two different dates.

That means `total` (lines) and the KPI (consignments) legitimately differ, so
BOTH are published: `unit` and `groups` let the panel say "3 lines across 1
consignment", and the KPI stays reconcilable at a glance. What is NOT allowed is
a list that quietly reports a different number with no way to see why — the
Delayed tile reading 247 over a list reading 454, with nothing saying one
counted orders and the other lines.
"""

DEFAULT_PAGE_SIZE = 50

# A page big enough to be worth a round trip, small enough that a client cannot
# ask for the whole 8,731-row list in one request and undo the point of paging.
MAX_PAGE_SIZE = 500

#-----------------------------------------------------
# SEARCH, ON WHAT THE READER SEES
#
# Every panel searches the RENDERED text — reference, detail, meta, badge —
# never the raw underlying columns. Two reasons:
#
#   1. The visible strings are already the thing a reader is scanning for: a
#      payment reference, a customer name, an item, a status. Searching
#      anything else risks a term that matches a row on screen and the box
#      still saying "no results", which is the one failure mode a search box
#      cannot be allowed to have.
#   2. It is the ONE place the rule has to be applied, for every list on every
#      dashboard, regardless of how many underlying columns feed the row.
#
# The trade-off: a value that is IN the record but never rendered (say, an
# internal id) cannot be searched. That is the correct trade — showing a
# result the reader cannot see why it matched would be worse.
#-----------------------------------------------------


def matches_search(item, term):
    """Whether one ReferenceItem's visible text contains the search term.

    `term` must already be lower-cased and stripped — callers loop this over
    many rows, so the normalisation happens once in `search_filter`, not once
    per row.
    """
    haystack = " ".join(
        str(item.get(field) or "") for field in ("reference", "detail", "meta", "badge")
    )
    return term in haystack.lower()


def search_filter(items, term):
    """The items whose visible text contains `term` — all of them if `term`
    is empty. Used by every IN-MEMORY reference list (imports, purchases,
    inventory, logistics); the Overview's SQL-backed lists filter in the
    query itself instead, since they never materialize the full row set —
    see `sql_search_clause`.
    """
    term = (term or "").strip().lower()
    if not term:
        return items
    return [item for item in items if matches_search(item, term)]


def sql_search_clause(term, *columns):
    """An `OR(col ILIKE '%term%' for col in columns)` clause, or None.

    For the Overview's SQL-paginated lists, which page via `OFFSET`/`LIMIT` in
    the database and must never pull a whole table into Python just to filter
    it — see the module docstring in `app.dashboard.whole.references`.

    None (not an always-true clause) when there is no term, so callers can
    `.where(clause)` only `if clause is not None` and the query is otherwise
    untouched — an empty search must return exactly what no search returns.
    """
    term = (term or "").strip()
    if not term:
        return None

    from sqlalchemy import or_

    pattern = f"%{term}%"
    return or_(*[col.ilike(pattern) for col in columns if col is not None])


def clamp(page=None, page_size=None):
    """(page, page_size) — sane values whatever the query string said."""
    page = max(1, int(page or 1))
    size = int(page_size or DEFAULT_PAGE_SIZE)
    size = max(1, min(size, MAX_PAGE_SIZE))
    return page, size


def page_count(total, page_size):
    return (total + page_size - 1) // page_size if page_size else 0


def paginate(rows, page=None, page_size=None, total=None,
             unit="record", groups=None, group_unit=None):
    """Slice an in-memory list into the reference-set shape.

    `total` overrides len(rows) for the callers that already know the full count
    without holding every row — the SQL-backed Overview lists, which page in the
    database rather than in Python.

    `unit` / `groups` / `group_unit` are how a list of LINES stays honest about
    the KPI it opened from: 3 lines across 1 consignment, 454 lines across 247
    orders. `groups` is None when the rows already ARE the parent.
    """
    page, size = clamp(page, page_size)
    count = len(rows) if total is None else total
    start = (page - 1) * size

    return {
        "total": count,
        "unit": unit,
        "groups": groups,
        "group_unit": group_unit,
        "page": page,
        "page_size": size,
        "pages": page_count(count, size),
        "items": rows[start:start + size] if total is None else list(rows),
    }


def empty(page=None, page_size=None, unit="record"):
    return paginate([], page, page_size, unit=unit)
