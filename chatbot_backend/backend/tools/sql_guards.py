"""
Automatic checks on generated SQL, run before it reaches the user.

WHY THIS EXISTS

Until now, every wrong answer was found the same way: the user read a number,
knew it was wrong, and a rule was hand-written into a prompt afterwards. That
does not scale and it cannot be deployed - it makes the user the error detector
and a developer the fix. Worse, a prompt rule is advice the model may or may not
follow on any given run; the same question has produced four different queries
on four runs.

These guards are not advice. They are deterministic checks that run on every
generated query, read the LIVE DATA PROFILE rather than anything hand-written,
and so keep working when new data is loaded and new values appear. Nothing here
names an item, a status or a table.

WHAT IS CHECKED

  1. FILTERING ON A VALUE THAT DOES NOT EXIST. The single most dangerous class,
     because it fails silently: `WHERE current_status = 'Sailing'` matched zero
     rows for months and the answer confidently said zero. The profile knows
     every value in every low-cardinality column, so a literal that is not among
     them is caught BEFORE the query runs - and the real values (plus the
     closest match) are handed back so the retry can fix itself.

  2. SUMMING A COLUMN THAT IS MOSTLY EMPTY. SUM skips NULLs, so a total over a
     7%-populated column looks like a total over everything. The profile knows
     each column's fill rate.

  3. DISTINCT WHILE LISTING RECORDS. Two genuinely different rows that agree on
     the selected columns silently become one - this dropped a real import line
     and nobody could have noticed from the answer.

A guard returns a HINT, not a hard failure. The existing retry loop feeds it
back to the model exactly as it already does with database errors, so a caught
mistake costs one extra call rather than a wrong answer.
"""

import re
from difflib import get_close_matches
from typing import Dict, List, Optional, Tuple

# A column whose vocabulary is this large is a long tail (supplier names,
# cities). A literal missing from it is quite possibly a real value that simply
# is not in the top-N, so do not cry wolf.
MAX_CHECKABLE_VOCABULARY = 25

# Columns whose values are free text by nature. Even when a small table makes
# them look low-cardinality, a filter on them is a search, not a category match.
FREE_TEXT_HINTS = ("name", "detail", "description", "remark", "item_name",
                   "customer", "supplier", "transporter", "works", "origin",
                   "city", "address", "number", "no", "ref", "code")


def _vocabularies(profile: Dict) -> Dict[str, Dict[str, List[str]]]:
    """column name -> {table: [values]}, for columns worth checking."""
    out: Dict[str, Dict[str, List[str]]] = {}
    for table, entry in (profile.get("tables") or {}).items():
        for column, values in (entry.get("vocabularies") or {}).items():
            if len(values) > MAX_CHECKABLE_VOCABULARY:
                continue
            if any(h in column.lower() for h in FREE_TEXT_HINTS):
                continue
            out.setdefault(column, {})[table] = [
                str(v["value"]) for v in values if v.get("value") is not None
            ]
    return out


# `alias.column = 'literal'` / `column IN ('a', 'b')`. Deliberately simple: the
# aim is to catch the obvious equality filter, not to parse SQL.
_EQ = re.compile(r"(?:(\w+)\.)?(\w+)\s*=\s*'([^']*)'")
_IN = re.compile(r"(?:(\w+)\.)?(\w+)\s+IN\s*\(([^)]*)\)", re.IGNORECASE)
_LITERAL = re.compile(r"'([^']*)'")


def _exists_in_db(column: str, value: str, tables: List[str]) -> bool:
    """
    Does this value actually exist in that column right now?

    The profile can be stale - a status set through the ERP UI changes no row
    count, so the cached vocabulary may not list it yet. Blocking on a stale
    cache would refuse a correct query, so the database gets the final word.
    Runs at most once per suspect literal, and only when the profile already
    disagrees, so the normal path costs nothing.
    """
    if not tables:
        return False
    try:
        from sqlalchemy import text

        from backend.config import get_engine

        with get_engine().connect() as conn:
            for table in tables:
                # Identifiers come from the profile (our own column/table names),
                # never from the user; the VALUE is bound as a parameter.
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table) or \
                   not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", column):
                    continue
                hit = conn.execute(
                    text(
                        f"SELECT 1 FROM {table} WHERE {column} = :v LIMIT 1"
                    ),
                    {"v": value},
                ).first()
                if hit:
                    return True
    except Exception:
        # If the lookup itself fails, do not block on a guess.
        return True
    return False


def check_literals(sql: str, profile: Dict) -> List[str]:
    """Literals filtered on that do not exist in that column. Silent killers."""
    vocab = _vocabularies(profile)
    problems: List[str] = []
    seen: set = set()

    def examine(column: str, literal: str) -> None:
        key = (column.lower(), literal)
        if key in seen or not literal:
            return
        seen.add(key)

        tables = vocab.get(column.lower()) or vocab.get(column)
        if not tables:
            return

        # Present in ANY table's version of this column is good enough - the
        # same column name recurs across tables with different vocabularies.
        every = {v for values in tables.values() for v in values}
        if literal in every:
            return

        # Case-only mismatch is worth its own message: it is invisible on
        # screen and matches nothing in Postgres.
        # The profile says no. Confirm against the live database before
        # blocking - the cache may simply predate this value.
        if _exists_in_db(column, literal, list(tables.keys())):
            return

        lowered = {v.lower(): v for v in every}
        if literal.lower() in lowered:
            problems.append(
                f"`{column} = '{literal}'` is the wrong CASE - the stored value "
                f"is '{lowered[literal.lower()]}'. Postgres `=` is "
                f"case-sensitive, so this matches zero rows."
            )
            return

        near = get_close_matches(literal, sorted(every), n=3, cutoff=0.6)
        listing = ", ".join(f"'{v}'" for v in sorted(every)[:12])
        if len(every) > 12:
            listing += ", ..."
        suggestion = f" Did you mean {' or '.join(repr(n) for n in near)}?" if near else ""
        problems.append(
            f"`{column} = '{literal}'` matches NOTHING - '{literal}' is not a "
            f"value of {column}. The values that exist are: {listing}.{suggestion}"
        )

    for alias, column, literal in _EQ.findall(sql):
        examine(column, literal)
    for alias, column, body in _IN.findall(sql):
        for literal in _LITERAL.findall(body):
            examine(column, literal)

    return problems


_SUM = re.compile(r"\bSUM\s*\(\s*(?:DISTINCT\s+)?(?:(\w+)\.)?(\w+)\s*\)", re.IGNORECASE)


def check_sums(sql: str, profile: Dict, threshold: float = 0.6) -> List[str]:
    """SUM over a column the data barely populates."""
    patchy: Dict[str, float] = {}
    for entry in (profile.get("tables") or {}).values():
        for column, rate in (entry.get("patchy") or {}).items():
            # Worst case across tables - a warning is the safe direction.
            patchy[column.lower()] = min(patchy.get(column.lower(), 1.0), rate)

    problems: List[str] = []
    for _alias, column in _SUM.findall(sql):
        rate = patchy.get(column.lower())
        if rate is not None and rate < threshold:
            problems.append(
                f"`SUM({column})` covers only {rate * 100:.0f}% of rows - "
                f"{column} is NULL on the rest and SUM skips them silently, so "
                f"the total will look like a total over everything when it is "
                f"not. Either return COUNT({column}) alongside it so the answer "
                f"can say how many rows the total covers, or count records "
                f"instead if that is what was asked."
            )
    return problems


def check_distinct(sql: str) -> List[str]:
    """SELECT DISTINCT on a listing query - merges genuinely different rows."""
    if not re.search(r"\bSELECT\s+DISTINCT\b", sql, re.IGNORECASE):
        return []
    # DISTINCT inside an aggregate (COUNT(DISTINCT x)) is the legitimate use.
    if re.search(r"\b(?:COUNT|SUM|AVG|STRING_AGG|ARRAY_AGG)\s*\(\s*DISTINCT",
                 sql, re.IGNORECASE):
        return []
    return [
        "`SELECT DISTINCT` on a listing query DELETES REAL RECORDS: two "
        "different records that happen to agree on every selected column "
        "collapse into one, silently, and the count comes out short. If you "
        "need the rows, drop DISTINCT, or select the row's own id so genuinely "
        "separate records stay separate."
    ]


_FULL_JOIN = re.compile(r"\bFULL\s+(?:OUTER\s+)?JOIN\b", re.IGNORECASE)
_RIGHT_JOIN = re.compile(r"\bRIGHT\s+(?:OUTER\s+)?JOIN\b", re.IGNORECASE)
_CROSS_JOIN = re.compile(r"\bCROSS\s+JOIN\b", re.IGNORECASE)


def check_joins(sql: str) -> List[str]:
    """
    FULL OUTER / RIGHT / CROSS joins, which here mean a row explosion.

    Every table in this schema is joined child-to-parent, so an answer is built
    by NARROWING from one side. A FULL OUTER JOIN does the opposite: it keeps
    the unmatched rows of BOTH sides, so joining a filtered set to an unfiltered
    view drags the whole view in.

    Measured, on "show the resin import records and the resin items": 15 resin
    import lines FULL OUTER JOINed to v_item_demand_picture returned 4,776 rows
    - every item in the company - because only the import side was filtered.
    Two of the 15 lines actually matched. A LEFT JOIN returns 15. The answer
    opened with "the result contains 4,776 combined rows", and the response call
    cost 94,829 input tokens instead of ~8,000.

    Blocking, not advisory: the query is valid SQL that runs cleanly, so nothing
    downstream can catch it, and one wasted retry is far cheaper than an answer
    built on the entire item master.
    """
    problems: List[str] = []

    if _FULL_JOIN.search(sql):
        problems.append(
            "`FULL OUTER JOIN` keeps the unmatched rows of BOTH sides, so a "
            "filtered set joined to an unfiltered table returns that whole "
            "table. This exact query shape returned 4,776 rows - every item in "
            "the company - when the honest answer was 15. Anchor the query on "
            "the side the question is about and LEFT JOIN the rest, or filter "
            "BOTH sides on the same material before combining them. If you "
            "genuinely need two independent result sets, UNION ALL them with a "
            "literal label column saying which side each row came from."
        )

    if _RIGHT_JOIN.search(sql):
        problems.append(
            "`RIGHT JOIN` keeps every row of the RIGHT-hand table, including "
            "those matching nothing on the left - so the table you are joining "
            "TO decides the row count, not the one you are asking about. Swap "
            "the operands and use LEFT JOIN, which makes the anchor table "
            "obvious to anyone reading it."
        )

    if _CROSS_JOIN.search(sql):
        problems.append(
            "`CROSS JOIN` multiplies both sides together. It is legitimate only "
            "against a single-row helper (a date window, a constant). Against "
            "anything else it is a cartesian product - give the join an ON "
            "condition."
        )

    return problems


def inspect(sql: str, profile: Optional[Dict] = None) -> Tuple[List[str], List[str]]:
    """
    Check a query. Returns (blocking, advisory).

    BLOCKING problems would produce a confidently wrong answer - a filter on a
    value that does not exist returns zero rows and reports it as fact. Those
    are worth spending a retry on.

    ADVISORY problems are worth telling the model about but do not by
    themselves invalidate the answer.
    """
    if not sql or not sql.strip():
        return [], []

    if profile is None:
        try:
            from backend.metadata.data_profile import get_profile

            profile = get_profile()
        except Exception:
            return [], []

    # check_joins is blocking: the query runs cleanly and returns a whole table,
    # so nothing after this point can tell it was wrong.
    blocking = check_literals(sql, profile) + check_joins(sql)
    advisory = check_sums(sql, profile) + check_distinct(sql)
    return blocking, advisory


def as_hint(problems: List[str]) -> str:
    """Render problems as the correction message the retry loop feeds back."""
    if not problems:
        return ""
    body = "\n".join(f"  - {p}" for p in problems)
    return (
        "Your query was checked before running and these problems were found:\n"
        f"{body}\n"
        "Rewrite it to address each one. Where a real value is listed above, use "
        "one of those rather than guessing another, or drop the filter if the "
        "question did not ask for it. Do not work around a problem by widening "
        "the query - the point is to answer the question that was asked."
    )
