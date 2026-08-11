"""
What the data ACTUALLY contains, read from the database instead of hand-written.

Every status list, value vocabulary and "this column is mostly empty" note used
to be typed into schema.py by hand. That does not survive a reload. When the
logistics loaders started writing 'Transportation' / 'On Water' instead of the
ERP's enum names 'Gate Out' / 'Sailing', the prompt kept naming the old values
and every in-transit query matched ZERO rows and reported it as an answer -
no error, just a confident wrong number. Three separate status lists were wrong
the same way, and nobody could have known without querying the database.

So this module derives them. Load a new workbook, add a branch, rename a status:
the profile changes with it and the prompt is right again with no edit.

Two things are derived, because they are the two the model gets wrong:

  * VALUE VOCABULARIES - for every low-cardinality text column, the values that
    exist and how many rows each has. A model cannot invent 'Sailing' when the
    prompt lists what is really there.
  * COLUMN FILL RATES - how often a numeric column is actually populated. SUM
    silently skips NULLs, so summing a 17%-populated column reports a total over
    a sixth of the rows while looking like a total over all of them.

Cached on disk against a fingerprint of the table row counts, so it costs one
cheap query per startup and only recomputes when the data actually changed -
which is precisely when it should.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy import text

from backend.config import get_engine

PROFILE_PATH = Path(__file__).with_name("data_profile.json")

# Above this many distinct values a column is free text (an item name, a
# reference), not a vocabulary, and listing it would be noise.
MAX_VOCABULARY = 25

# Report a numeric column's fill rate only when it is patchy enough to mislead a
# SUM. A fully populated column needs no warning.
PATCHY_BELOW = 0.95

# The business tables. System/audit tables carry nothing a business question
# needs and would only spend prompt budget.
TABLES = [
    "items", "suppliers", "branches", "ports", "clearing_agents", "customers",
    "stock", "issuance", "store_requisition", "purchases_data",
    "consignments", "consignment_items", "payments",
    "logistics_consignments", "logistics_items", "logistics_packages",
    "logistics_containers",
    "trucking_consignments", "trucking_vehicles",
]

# Never profile these as vocabularies even if they happen to be low-cardinality:
# ids and flags are plumbing, and a surrogate key that currently has 12 values
# is not a vocabulary, it is a coincidence.
SKIP_COLUMNS = {"id", "is_deleted", "is_active", "is_verified", "is_locked",
                "created_by_id", "deleted_by_id", "created_at", "updated_at",
                "deleted_at"}


def _tables_with_updated_at(conn) -> set:
    """Which of our tables actually carry updated_at.

    Asked once, from information_schema, because PROBING for the column is not
    safe: a failed statement aborts the transaction in Postgres and every query
    after it on the same connection fails. That is not hypothetical - it rebuilt
    this profile to empty and silently disabled the guards.
    """
    try:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'updated_at'"
            )
        ).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _fingerprint(conn) -> str:
    """
    Cheap signature of the data. Moves when rows are added, reloaded or EDITED.

    Row counts alone miss an edit: changing a consignment's status through the
    ERP screens changes no count, so a count-only fingerprint kept serving a
    stale profile. MAX(updated_at) catches most edits.

    It is NOT airtight - editing an older row does not move a table's MAX - so
    the guards no longer trust this cache on its own: sql_guards confirms a
    suspect value against the live database before blocking anything.
    """
    stamped = _tables_with_updated_at(conn)
    parts = []
    for table in TABLES:
        try:
            n = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        except Exception:
            parts.append(f"{table}:-1")
            continue

        touched = ""
        if table in stamped:
            try:
                touched = conn.execute(
                    text(f"SELECT MAX(updated_at) FROM {table}")
                ).scalar() or ""
            except Exception:
                touched = ""

        parts.append(f"{table}:{n}:{touched}")
    return "|".join(parts)


def _columns(conn, table: str) -> List[Dict[str, str]]:
    rows = conn.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t "
            "ORDER BY ordinal_position"
        ),
        {"t": table},
    ).fetchall()
    return [{"name": r[0], "type": r[1]} for r in rows]


def _build(conn) -> Dict[str, Any]:
    profile: Dict[str, Any] = {
        "fingerprint": _fingerprint(conn),
        "tables": {},
    }

    for table in TABLES:
        try:
            total = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        except Exception:
            continue
        if not total:
            profile["tables"][table] = {"rows": 0, "vocabularies": {}, "patchy": {}}
            continue

        entry: Dict[str, Any] = {"rows": total, "vocabularies": {}, "patchy": {}}

        for col in _columns(conn, table):
            name, dtype = col["name"], col["type"]
            if name in SKIP_COLUMNS or name.endswith("_id"):
                continue

            if dtype in ("text", "character varying", "character"):
                # One query settles both questions: is it a vocabulary, and what
                # is in it. Asking for MAX_VOCABULARY + 1 means "more than the
                # limit" is visible without a second COUNT(DISTINCT) scan.
                try:
                    rows = conn.execute(
                        text(
                            f"SELECT {name} AS v, count(*) AS n FROM {table} "
                            f"WHERE {name} IS NOT NULL "
                            f"GROUP BY 1 ORDER BY 2 DESC LIMIT {MAX_VOCABULARY + 1}"
                        )
                    ).fetchall()
                except Exception:
                    continue
                if rows and len(rows) <= MAX_VOCABULARY:
                    entry["vocabularies"][name] = [
                        {"value": r[0], "rows": r[1]} for r in rows
                    ]

            elif dtype in ("numeric", "integer", "bigint", "double precision", "real"):
                try:
                    filled = conn.execute(
                        text(f"SELECT count({name}) FROM {table}")
                    ).scalar()
                except Exception:
                    continue
                rate = (filled or 0) / total
                if rate < PATCHY_BELOW:
                    entry["patchy"][name] = round(rate, 4)

        profile["tables"][table] = entry

    return profile


def get_profile(force: bool = False) -> Dict[str, Any]:
    """The profile, rebuilt only when the data changed."""
    engine = get_engine()
    with engine.connect() as conn:
        current = _fingerprint(conn)

        if not force and PROFILE_PATH.exists():
            try:
                cached = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
                if cached.get("fingerprint") == current:
                    return cached
            except Exception:
                pass  # a corrupt cache just means rebuild

        profile = _build(conn)

    tmp = PROFILE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(profile, indent=2, default=str), encoding="utf-8")
    tmp.replace(PROFILE_PATH)
    return profile


def profile_text(max_chars: int = 9000) -> str:
    """The profile as a block for the SQL prompt."""
    try:
        profile = get_profile()
    except Exception:
        return ""  # never take the chatbot down over a profile

    lines = [
        "=== WHAT THE DATA ACTUALLY CONTAINS (read from the database) ===",
        "",
        "Generated from the live database, not written by hand. These are THE",
        "VALUES THAT EXIST. If a value you are about to filter on is not listed",
        "here, it is not in the data and your query will match zero rows and",
        "return a confident, wrong answer. Filter on what is listed.",
        "",
    ]

    for table, entry in profile.get("tables", {}).items():
        vocabularies = entry.get("vocabularies") or {}
        patchy = entry.get("patchy") or {}
        if not vocabularies and not patchy:
            continue

        lines.append(f"{table} ({entry.get('rows', 0):,} rows)")
        for col, values in vocabularies.items():
            rendered = " | ".join(f"'{v['value']}' {v['rows']:,}" for v in values)
            lines.append(f"    {col}: {rendered}")
        for col, rate in patchy.items():
            lines.append(
                f"    {col} is populated on {rate * 100:.0f}% of rows "
                f"- SUM skips the rest"
            )
        lines.append("")

    text_block = "\n".join(lines)
    if len(text_block) > max_chars:
        text_block = text_block[:max_chars].rsplit("\n", 1)[0] + "\n    ...(truncated)"
    return text_block


if __name__ == "__main__":
    import sys

    profile = get_profile(force="--force" in sys.argv)
    vocab = sum(len(t.get("vocabularies") or {}) for t in profile["tables"].values())
    patchy = sum(len(t.get("patchy") or {}) for t in profile["tables"].values())
    print(f"tables profiled : {len(profile['tables'])}")
    print(f"vocabularies    : {vocab}")
    print(f"patchy columns  : {patchy}")
    print(f"prompt block    : {len(profile_text()):,} chars")
    print(f"written to      : {PROFILE_PATH}")
