"""
Read-only query execution against Postgres.

Every query runs inside a READ ONLY transaction with a statement timeout, so
even if a bad query slips past the validator it cannot write anything or hang
the API. Credentials come from .env via backend.config.

Recommended: point DB_USER at a role with SELECT-only grants. The read-only
transaction is a safety net, not a substitute for that.
"""

import datetime
import re
import decimal
from typing import Any, Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.config import SQL_TIMEOUT_MS, get_engine


class QueryExecutionError(RuntimeError):
    """Raised when the database rejects or fails a query."""


def _to_jsonable(value: Any) -> Any:
    """Convert Postgres types into things FastAPI and the LLM can handle."""
    if isinstance(value, decimal.Decimal):
        # float is fine here - these are quantities and money for display,
        # not values we do further exact arithmetic on.
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return value.days
    if isinstance(value, memoryview):
        return value.tobytes().decode("utf-8", errors="replace")
    return value


def run_query(sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Execute a SELECT and return (columns, rows).

    Raises QueryExecutionError with the database's own message, which the SQL
    agent uses to repair the query on its retry.
    """
    try:
        with get_engine().connect() as conn:
            # READ ONLY blocks writes; the timeout stops a runaway scan.
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text(f"SET LOCAL statement_timeout = {SQL_TIMEOUT_MS}"))

            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [
                {col: _to_jsonable(val) for col, val in zip(columns, row)}
                for row in result.fetchall()
            ]
        return columns, rows

    except SQLAlchemyError as exc:
        # orig carries the raw psycopg2 message, which is far more useful to
        # the retrying SQL agent than SQLAlchemy's wrapper text.
        detail = str(getattr(exc, "orig", exc)).strip()
        raise QueryExecutionError(detail) from exc


def _singular_stem(token: str) -> str:
    """
    Trim a plural ending so a plural query finds singular item names.

    The master stores singular names - "Resin", "Shaft", "Round Bar" - but users
    type plurals. Because matching is by SUBSTRING, searching the shorter stem
    finds both forms, while searching the plural finds neither: 'resins' matched
    0 of the 19 real resin codes.

    Worse, it did not simply return nothing. Punctuation-stripped matching joins
    words together, so 'resins' hit "Epoxy Re[sin Set]" -> 'epoxyresinset' and
    "Re[sin Sand]" -> 'resinsand'. The user was offered two accidental matches
    and told those were the only resins in the system.

    Trimming is safe even when the word is not a plural: 'brass' -> 'bras' is
    still a substring of "Brass", and 'glass' -> 'glas' of "Glass". Short tokens
    are left alone so 'gas' does not become 'ga'.
    """
    lowered = token.lower()
    if len(lowered) >= 5 and lowered.endswith(("ches", "shes", "sses", "xes")):
        return lowered[:-2]          # boxes -> box, batches -> batch
    if len(lowered) >= 4 and lowered.endswith("s") and not lowered.endswith("ss"):
        return lowered[:-1]          # resins -> resin, shafts -> shaft
    return lowered


def find_items_by_name(name: str, limit: int = 0) -> Dict[str, Any]:
    """
    Item master rows whose name matches, for same-name/different-item_code
    disambiguation before SQL is generated.

    limit <= 0 (the default) means no cap - common item names genuinely span
    hundreds of item_codes ("Round Bar" alone is 1000+), and the UI's table
    is sortable/searchable/scrollable, so there is no need to truncate what
    the user sees. Pass a positive limit to cap it (used for the LLM
    resolution prompt, which only needs a representative sample).
    """
    # A user names an item the way it reads on paper - "resin a 85" - but the
    # name and the spec live in DIFFERENT columns ("Resin" + specs "A-85"), and
    # the punctuation rarely matches ("a 85" vs "A-85" vs "a85"). Matching the
    # raw phrase against items.name alone finds nothing.
    #
    # So: search the item name, spec AND category together, with
    # punctuation flattened to spaces on both sides, and require every token of
    # the user's phrase to appear somewhere in that combined text. Over-matching
    # is fine - the item-resolution agent shows the candidates and asks - while
    # under-matching is the failure that leaves the user with nothing.
    tokens = [_singular_stem(t) for t in re.split(r"[^0-9a-zA-Z]+", name or "") if t]
    if not tokens:
        return {"rows": [], "truncated": False}

    # The item master is now name + default_specification + category; the old
    # material_standard and group_name columns are gone. Category is included
    # because it carries the material grade the standard used to hold.
    _combined = (
        "lower(coalesce(name,'') || ' ' || coalesce(default_specification,'') "
        "|| ' ' || coalesce(category,''))"
    )
    # Two normalisations, because users split or join spec tokens either way:
    #   spaced - punctuation becomes a space, so "A-85" matches tokens "a","85"
    #   tight  - punctuation and spaces removed, so "A-85" matches token "a85"
    # A token counts if it appears in EITHER form.
    spaced = f"regexp_replace({_combined}, '[^a-z0-9]+', ' ', 'g')"
    tight = f"regexp_replace({_combined}, '[^a-z0-9]+', '', 'g')"
    conditions = " AND ".join(
        f"({spaced} LIKE :tok{i} OR {tight} LIKE :tok{i})" for i in range(len(tokens))
    )
    params: Dict[str, Any] = {f"tok{i}": f"%{t.lower()}%" for i, t in enumerate(tokens)}

    # Aliased back to the names the item-resolution agent matches on, so the
    # renamed master does not ripple through the agent's scoring.
    sql_text = f"""
        SELECT item_code,
               name AS item,
               default_specification AS specs,
               default_unit_of_measurement AS uom,
               category AS item_category,
               is_active
        FROM items
        WHERE {conditions}
        ORDER BY item_code
    """
    if limit > 0:
        sql_text += " LIMIT :limit"
        params["limit"] = limit + 1

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            result = conn.execute(text(sql_text), params)
            columns = list(result.keys())
            rows = [
                {col: _to_jsonable(val) for col, val in zip(columns, row)}
                for row in result.fetchall()
            ]
    except SQLAlchemyError:
        return {"rows": [], "truncated": False}

    if limit <= 0:
        return {"rows": rows, "truncated": False}

    truncated = len(rows) > limit
    return {"rows": rows[:limit], "truncated": truncated}


def get_reorder_inputs(item_code: str, branch: str = "") -> Dict[str, Any]:
    """
    Current stock and planning parameters for an item, for the reorder /
    run-out calculation.

    Looked up directly rather than through the generated SQL: a trend/forecast
    query is required to return exactly one row per period (see sql_prompt), so
    it structurally cannot also carry stock and lead-time columns. Fetching them
    here keeps both shapes correct.

    Any field can come back None - an item may have no stock row, or too little
    purchase history to observe a lead time, and safety days have no source in
    this schema at all. The caller reports the gap rather than guessing.
    """
    out: Dict[str, Any] = {
        "item_code": item_code,
        "available_qty": None,
        "lead_time_days": None,
        "safety_days": None,
        "uom": None,
        "branches": [],
    }
    if not item_code:
        return out

    params: Dict[str, Any] = {"code": item_code}
    branch_filter = ""
    if branch:
        branch_filter = " AND branch ILIKE :branch"
        params["branch"] = f"%{branch}%"

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))

            row = conn.execute(
                text(f"""
                    SELECT SUM(available_qty) AS available_qty,
                           COUNT(*) AS branch_rows
                    FROM stock
                    WHERE item_code = :code{branch_filter}
                """),
                params,
            ).fetchone()
            if row and row[1]:
                out["available_qty"] = _to_jsonable(row[0])

            # Lead time used to come from an ab_items planning table, which no
            # longer exists. It is now OBSERVED from the item's own purchase
            # history: the gap between the date a purchase was required and the
            # date it actually landed. The median is used rather than the mean
            # so one stalled order does not set the planning figure, and the
            # conservative MAX across branches is no longer meaningful because
            # the figure is per purchase, not per branch.
            #
            # Safety days have no source in the current schema at all, so they
            # stay None and the caller reports the gap - see the reorder block
            # in response_prompt, which leads with purchase-timing when the
            # stock-based inputs are missing.
            row = conn.execute(
                text("""
                    SELECT percentile_cont(0.5) WITHIN GROUP (
                               ORDER BY (purchase - required_d)
                           )
                    FROM purchases_data
                    WHERE item_code = :code
                      AND purchase IS NOT NULL
                      AND required_d IS NOT NULL
                      AND purchase >= required_d
                """),
                {"code": item_code},
            ).fetchone()
            if row and row[0] is not None:
                out["lead_time_days"] = _to_jsonable(row[0])

            row = conn.execute(
                text(
                    "SELECT default_unit_of_measurement FROM items "
                    "WHERE item_code = :code"
                ),
                {"code": item_code},
            ).fetchone()
            if row:
                out["uom"] = _to_jsonable(row[0])

            rows = conn.execute(
                text(f"""
                    SELECT branch, available_qty FROM stock
                    WHERE item_code = :code{branch_filter} ORDER BY branch
                """),
                params,
            ).fetchall()
            out["branches"] = [
                {"branch": _to_jsonable(r[0]), "available_qty": _to_jsonable(r[1])}
                for r in rows
            ]
    except SQLAlchemyError:
        return out

    return out


def get_purchase_history(item_code: str) -> List[Dict[str, Any]]:
    """
    Past purchase events for an item, newest last: [{purchase_date, qty}, ...].

    Used to answer "when will I next have to purchase this" from the item's own
    replenishment behaviour, which works even when no current stock row exists.
    Same-day purchase orders are grouped into ONE replenishment event, because a
    batch split across several POs on one day is one buying decision, not four.
    """
    if not item_code:
        return []
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            rows = conn.execute(
                text("""
                    SELECT purchase AS purchase_date, SUM(qty) AS qty
                    FROM purchases_data
                    WHERE item_code = :code AND purchase IS NOT NULL
                    GROUP BY purchase
                    ORDER BY purchase
                """),
                {"code": item_code},
            ).fetchall()
    except SQLAlchemyError:
        return []

    return [
        {"purchase_date": _to_jsonable(r[0]), "qty": _to_jsonable(r[1])} for r in rows
    ]


def ping() -> bool:
    """True when the database is reachable. Used by the API health check."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
