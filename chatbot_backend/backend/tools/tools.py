"""
SQL safety checks.

This is the last gate before generated SQL touches the database. It is
deliberately strict: anything it is not sure about, it rejects.

This is defence in depth, not the only defence. The real guarantee is a
read-only Postgres role plus the read-only transaction and statement_timeout
applied in postgres_tools.run_query(). See backend/tools/postgres_tools.py.
"""

import re

from backend.config import SQL_ROW_LIMIT

# Whole-word match, so a table called "updates" is not mistaken for an UPDATE.
FORBIDDEN = (
    "insert", "update", "delete", "drop", "alter", "truncate", "create",
    "grant", "revoke", "comment", "merge", "call", "do", "copy", "vacuum",
    "refresh", "reindex", "listen", "notify", "execute", "prepare",
    "set", "reset", "begin", "commit", "rollback", "savepoint",
)

FORBIDDEN_RE = re.compile(r"\b(" + "|".join(FORBIDDEN) + r")\b", re.IGNORECASE)

# pg_sleep and friends are read-only but can hang a connection.
DANGEROUS_FUNCTIONS_RE = re.compile(
    r"\b(pg_sleep|pg_read_file|pg_read_binary_file|pg_ls_dir|lo_import|lo_export|dblink)\s*\(",
    re.IGNORECASE,
)


class UnsafeQueryError(ValueError):
    """Raised when generated SQL fails a safety check."""


def strip_sql_noise(sql: str) -> str:
    """Remove markdown fences and comments so checks see the real statement."""
    text = sql.strip()

    # ```sql ... ``` fences the model sometimes adds despite being told not to
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()

    text = re.sub(r"--[^\n]*", " ", text)          # line comments
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)  # block comments
    return text.strip().rstrip(";").strip()


# Single-quoted string literal, with '' as the SQL-standard escaped quote.
_STRING_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")


def _mask_string_literals(sql: str) -> str:
    """
    Blank out the contents of '...' string literals, keeping length and quotes.

    Item names and notes can legitimately contain words like "Set Screw" or
    "do not ship". Without this, the keyword/function scans below treat the
    SET or DO inside those literals as real SQL and reject a harmless query.
    """
    return _STRING_LITERAL_RE.sub(lambda m: "'" + " " * (len(m.group(0)) - 2) + "'", sql)


def validate_sql(sql: str) -> str:
    """
    Return the cleaned statement, or raise UnsafeQueryError.

    Checks, in order: non-empty, single statement, starts with SELECT or WITH,
    no write keywords, no dangerous functions.
    """
    statement = strip_sql_noise(sql)

    if not statement:
        raise UnsafeQueryError("No SQL was produced.")

    # Scan a version with string-literal contents blanked out, so values like
    # 'Set Screw' or 'do not ship' aren't mistaken for SQL syntax.
    masked = _mask_string_literals(statement)

    # After stripping the trailing semicolon, any remaining one means the model
    # tried to chain a second statement.
    if ";" in masked:
        raise UnsafeQueryError("Only one statement is allowed.")

    if not re.match(r"^\s*(select|with)\b", statement, re.IGNORECASE):
        raise UnsafeQueryError("Only SELECT (or WITH ... SELECT) queries are allowed.")

    match = FORBIDDEN_RE.search(masked)
    if match:
        raise UnsafeQueryError(f"Disallowed keyword in query: {match.group(1).upper()}")

    if DANGEROUS_FUNCTIONS_RE.search(masked):
        raise UnsafeQueryError("Disallowed function in query.")

    return statement


def enforce_limit(sql: str, limit: int = SQL_ROW_LIMIT) -> str:
    """
    Append a LIMIT when the outer query has none - unless `limit` is 0 (no
    cap), in which case the query runs exactly as generated.

    Only looks at the tail of the statement, so a LIMIT inside a subquery or CTE
    does not count as the outer one.
    """
    if limit <= 0:
        return sql
    if re.search(r"\blimit\s+\d+\s*$", sql, re.IGNORECASE):
        return sql
    return f"{sql}\nLIMIT {limit}"


# Trailing LIMIT (optionally with OFFSET) on the OUTER query only - tail-anchored,
# so a LIMIT inside a subquery/CTE is left alone.
_OUTER_LIMIT_RE = re.compile(
    r"\s+limit\s+\d+\s*(?:offset\s+\d+\s*)?$", re.IGNORECASE
)


def strip_outer_limit(sql: str) -> str:
    """
    Remove a trailing LIMIT the model added out of habit.

    Used in no-cap mode (SQL_ROW_LIMIT <= 0) when the user did NOT ask for a
    specific top-N: the app shows every row, so a stray `LIMIT 100` would
    silently hide data and make counts inconsistent between otherwise-identical
    questions. Tail-anchored, so a legitimate LIMIT inside a subquery survives.
    """
    return _OUTER_LIMIT_RE.sub("", sql).rstrip()


def prepare_sql(
    sql: str, limit: int = SQL_ROW_LIMIT, strip_uncapped_limit: bool = False
) -> str:
    """
    Validate, then apply the row-cap policy. Raises UnsafeQueryError if unsafe.

    - limit > 0  : append a LIMIT if the query has none (hard cap).
    - limit <= 0 : no cap. If `strip_uncapped_limit` is set (the user did not
      ask for a top-N), remove any stray outer LIMIT the model added so the full
      result set comes back.
    """
    statement = validate_sql(sql)
    if limit <= 0:
        return strip_outer_limit(statement) if strip_uncapped_limit else statement
    return enforce_limit(statement, limit)
