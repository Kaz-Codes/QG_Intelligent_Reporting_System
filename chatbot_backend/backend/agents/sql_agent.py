"""
SQL agent - two nodes, not one.

    generate_sql : question + business context + schema -> a SELECT statement
    execute_sql  : validate, run it, and on failure hand the database's own
                   error back to generate_sql for another attempt

Splitting them is what makes the retry loop possible. Generated SQL fails often
on a real schema (wrong column, bad join, type mismatch), and the error message
is usually enough for the model to fix itself. The graph wires
execute_sql -> generate_sql for up to SQL_MAX_RETRIES attempts.
"""

from typing import List

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from backend.config import (
    EFFORT_ACCURATE, SQL_MAX_RETRIES, SQL_ROW_LIMIT, ZERO_ROW_RETRY, structured_llm,
)
from backend.metadata.data_profile import profile_text
from backend.metadata.schema import get_schema_text
from backend.prompts.sql_prompt import SQL_SYSTEM_PROMPT, build_limit_rule, build_sql_prompt
from backend.tools import query_cache
from backend.tools.postgres_tools import QueryExecutionError, run_query
from backend.tools.sql_guards import as_hint as guard_hint, inspect as inspect_sql
from backend.tools.tools import UnsafeQueryError, prepare_sql


class GeneratedSQL(BaseModel):
    sql: str = Field(
        description="A single PostgreSQL SELECT statement. Empty if not answerable."
    )
    explanation: str = Field(
        description="One line on what the query returns, or why none was written."
    )
    tables_used: List[str] = Field(
        default_factory=list, description="Tables referenced by the query."
    )
    limit_is_user_requested: bool = Field(
        default=False,
        description=(
            "True ONLY if the query contains a LIMIT that reflects a specific "
            "top-N count the USER explicitly asked for (e.g. 'top 5', 'the 3 "
            "highest'). False when there is no LIMIT, or a LIMIT was added out of "
            "habit rather than because the user asked for exactly that many rows."
        ),
    )


def generate_sql(state: dict) -> dict:
    question = state.get("rewritten_query") or state.get("user_query", "")

    # A question answered before replays its stored query instead of being
    # re-written from scratch. That is what makes a repeat question return the
    # same number - the model produced up to five different queries for one
    # question across five runs - and it skips the slowest call in the turn.
    #
    # Skipped on a retry (sql_error set) and after a zero-row retry, because in
    # both cases the whole point is to get something DIFFERENT from what the
    # cache would hand back.
    # Keyed on what the USER typed, not on `question` (the rewrite), because the
    # rewrite is regenerated each turn and worded differently every time - three
    # runs of one question produced three different keys. A follow-up whose
    # meaning lives in the previous turn is skipped entirely; see
    # is_self_contained.
    raw_question = state.get("user_query", "") or question

    if (
        not state.get("sql_error")
        and not state.get("zero_row_retried")
        and query_cache.is_self_contained(raw_question, question)
    ):
        cached = query_cache.lookup(raw_question, state.get("entities"))
        if cached:
            return {
                "sql": cached["sql"],
                "sql_explanation": "Reused the stored query for this question.",
                "tables_used": cached.get("tables_used", []),
                "limit_is_user_requested": cached.get("limit_is_user_requested", False),
                "sql_from_cache": True,
                # Needed to evict THIS entry if the replay comes back empty -
                # see the zero-row branch in execute_sql.
                "sql_cache_fingerprint": cached.get("fingerprint", ""),
                "sql_error": "",
            }

    # The schema says what the columns ARE; the profile says what is IN them,
    # read from the live database. Hand-written value lists go stale the moment
    # a loader changes - three status vocabularies in schema.py were already
    # wrong, and every query filtering on them matched zero rows silently.
    system_prompt = SQL_SYSTEM_PROMPT.format(
        limit_rule=build_limit_rule(SQL_ROW_LIMIT),
        schema=get_schema_text() + "\n\n" + profile_text(),
    )

    # item_resolution_agent's finding (which exact item_code(s) a named item
    # resolved to) lives in a separate field from the business-terminology
    # context - see state.item_context - but the SQL agent needs both together.
    # The zero-row guard's feedback, if the last attempt came back empty. Passed
    # in the `error` slot so it lands in the same "here is what went wrong, fix
    # it" section of the prompt the retry loop already uses.
    zero_hint = state.get("zero_row_hint", "")
    sql_error = state.get("sql_error", "")
    previous_sql = state.get("sql", "")
    context_blocks = [*state.get("item_context", []), *state.get("context", [])]

    # A zero-row retry is NOT a failure, and must not be rendered as one.
    # Passing the hint through `error` put it under build_sql_prompt's
    # "Your previous query FAILED. Fix it. ... Do not repeat the same mistake"
    # header, which flatly contradicts the hint's own closing instruction to
    # return the SAME query when the empty result is genuine - so a correct
    # "nothing matches" got broadened into a wrong non-zero answer.
    # It cannot go through `previous_sql` either: that renders the FOLLOW-UP
    # block, which says to keep the previous FROM/JOIN/WHERE exactly - the
    # opposite of what this retry is for. So it rides in as context, carrying
    # the offending query with it, and both other branches stay switched off.
    if zero_hint and not sql_error:
        context_blocks = [
            *context_blocks,
            f"{zero_hint}\n\nThe query that returned nothing:\n{previous_sql}",
        ]
        previous_sql = ""

    prompt = build_sql_prompt(
        question=question,
        intent=state.get("intent", ""),
        entities=state.get("entities", {}),
        context=context_blocks,
        previous_sql=previous_sql,
        error=sql_error,
    )

    try:
        llm = structured_llm(GeneratedSQL, effort=EFFORT_ACCURATE)
        result = llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
        )
    except Exception as exc:
        return {"sql": "", "error": f"Could not generate a query: {exc}"}

    if not result.sql.strip():
        # The model decided the schema cannot answer this.
        #
        # Sometimes true. But it is also how the worst wrong answer so far was
        # produced: asked to "show scrap data" it declared no scrap is recorded,
        # for a material with 93 item codes and 10,311 issuance lines - because
        # it was looking for a scrap TABLE rather than scrap ITEMS. A refusal is
        # the one answer a user cannot check, so challenge it once before
        # passing it on.
        if ZERO_ROW_RETRY and not state.get("zero_row_retried"):
            return {
                "sql": "",
                "sql_explanation": result.explanation,
                "zero_row_retried": True,
                "zero_row_hint": _NO_SQL_HINT.format(
                    reason=result.explanation or "(no reason given)"
                ),
            }

        return {
            "sql": "",
            "sql_explanation": result.explanation,
            "zero_row_hint": "",
            "error": result.explanation or "This question cannot be answered from the available data.",
        }

    return {
        "sql": result.sql,
        "sql_explanation": result.explanation,
        "tables_used": result.tables_used,
        "limit_is_user_requested": result.limit_is_user_requested,
        "sql_from_cache": False,
        # Consumed - clear it so execute_sql does not route back here forever.
        "zero_row_hint": "",
        # Clear the previous error so a successful retry does not look failed.
        "sql_error": "",
    }


def _looks_empty(rows: list) -> bool:
    """
    True when the result says "nothing", in either shape it can take.

    No rows at all is the obvious one. The subtler - and far more common - one
    is a bare aggregate: SELECT COUNT(*) always returns exactly ONE row, and
    when nothing matched that row contains 0. Every silent filter bug seen here
    was a COUNT, so a guard that only looked for an empty row list would have
    missed all of them.

    Only single-row, single-column results count: a real breakdown that happens
    to contain a zero somewhere is a legitimate answer, not a suspicious one.
    """
    if not rows:
        return True
    if len(rows) != 1 or len(rows[0]) != 1:
        return False
    value = next(iter(rows[0].values()))
    return value is None or (isinstance(value, (int, float)) and value == 0)


def execute_sql(state: dict) -> dict:
    attempts = state.get("sql_attempts", 0) + 1
    sql = state.get("sql", "")

    if not sql.strip():
        return {"sql_attempts": attempts, "retrieved_data": [], "row_count": 0}

    try:
        # In no-cap mode, strip a stray outer LIMIT unless the user explicitly
        # asked for a top-N - so the user reliably gets EVERY matching row and
        # counts stay consistent between identical questions.
        strip_uncapped_limit = not state.get("limit_is_user_requested", False)
        safe_sql = prepare_sql(
            sql, SQL_ROW_LIMIT, strip_uncapped_limit=strip_uncapped_limit
        )
    except UnsafeQueryError as exc:
        # Feed this back like any other error; the model usually rewrites it
        # into a proper SELECT on the next pass.
        return {"sql_attempts": attempts, "sql_error": f"Rejected by safety check: {exc}"}

    # CORRECTNESS check, not a safety one, and it runs BEFORE the query does.
    # A filter on a value the column does not contain is valid SQL: it runs
    # cleanly, returns nothing, and the answer states that nothing as fact.
    # `current_status = 'Sailing'` did exactly that for months. The guards read
    # the live data profile, so they keep working when new data arrives and no
    # prompt has to be edited to teach them a new value.
    blocking, advisory = inspect_sql(safe_sql)
    if blocking and attempts <= SQL_MAX_RETRIES:
        return {
            "sql_attempts": attempts,
            "sql_error": guard_hint(blocking + advisory),
            "sql_guard_tripped": True,
        }

    try:
        columns, rows = run_query(safe_sql)
    except QueryExecutionError as exc:
        return {"sql_attempts": attempts, "sql_error": str(exc)}

    # A bare aggregate (MAX/SUM/COUNT with no GROUP BY) always returns exactly
    # one row even when nothing matched - every column comes back NULL. That
    # carries no information; treat it as no data so a table of dashes is
    # never shown under "not available" wording, and so row_count == 0 takes
    # the same "no rows matched" path everywhere else already does.
    if rows and all(all(v is None for v in row.values()) for row in rows):
        rows = []

    out = {
        "sql": safe_sql,
        "sql_attempts": attempts,
        "sql_error": "",
        "columns": columns,
        "retrieved_data": rows,
        "row_count": len(rows),
        "truncated": SQL_ROW_LIMIT > 0 and len(rows) >= SQL_ROW_LIMIT,
    }

    # NOTHING CAME BACK. That is a legitimate answer sometimes, but it is also
    # how every silent filter bug has shown up so far: an item_code pinned to
    # the wrong item, a doubled backslash that matched a literal backslash, and
    # AND where OR was meant. All three returned a confident 0 with no error,
    # so nothing questioned them. Give the model exactly one more attempt with
    # its own empty result as evidence, then take the second answer as real.
    if ZERO_ROW_RETRY and _looks_empty(rows) and not state.get("zero_row_retried"):
        out["zero_row_retried"] = True
        out["zero_row_hint"] = _ZERO_ROW_HINT
        # A cached query that now returns nothing has gone stale (the data
        # moved, or it was wrong all along) - drop it so it is not replayed.
        # Evict by FINGERPRINT, not by question text: the hit may have come from
        # the embedding near-match path, where the stored question is worded
        # differently from this turn's, so forgetting by text removes nothing
        # and the bad entry is replayed on every future ask. Matching on text
        # also ignores entities, so it can delete a different item's entry.
        if state.get("sql_from_cache"):
            try:
                query_cache.forget(
                    state.get("sql_cache_fingerprint")
                    or state.get("user_query", "")
                    or state.get("rewritten_query", "")
                )
            except Exception:
                pass

    return out


_NO_SQL_HINT = """You returned NO QUERY, saying:

    {reason}

Check that before it is reported to the user as "we do not hold this data",
which is the one answer they cannot verify for themselves.

The usual mistake is looking for a TABLE named after the thing asked about,
when it is really a row IN a table:

- Materials and products are ITEMS, not tables. Scrap, resin, shafts, bars,
  sand, electrodes - all of them are rows in `items`, found by name, and their
  movements are in issuance / purchases_data / stock / store_requisition via
  item_code. There is no scrap table, and there does not need to be. This exact
  mistake declared "no scrap is recorded" for a material with 93 item codes and
  10,311 issuance lines against it.
- Statuses, departments, branches and suppliers are VALUES in a column, not
  tables of their own.
- A category or grouping the user names is usually items.category, or a word
  inside items.name.

So: can the question be answered by matching a NAME or a VALUE in a table that
does exist? If yes, write that query.

Only genuinely absent things stay absent - export paperwork status is the real
example, because no table has a document-status column at all. If after this
check the data really is not there, return empty sql again with the reason, and
it will be reported as such."""


_ZERO_ROW_HINT = """Your previous query ran without error but returned NO ROWS.

That is sometimes the true answer. More often it means the query was too
narrow. Before concluding there is genuinely no data, re-read it for these,
which are the ways this has actually gone wrong here:

- AND where OR was meant. Alternatives ("bar" OR "shaft", "in transit" OR
  "sailing") joined with AND require one row to satisfy all of them, which
  almost nothing does.
- An item filter pinned to ONE item_code when the question was about a
  category or a count across many items.
- A regex that matches nothing: a backslash escape written doubled ('\\\\y')
  looks for a literal backslash. Use '[[:<:]]word[[:>:]]' for whole words.
- A status or category literal that does not exist. Only use values named in
  the business context; never invent one.
- A date window with no data in it, or a join that should be LEFT.

Write a corrected query. If, having checked all of the above, you are satisfied
the answer really is "nothing matches", return the SAME query again - that is a
valid outcome and it will be reported as a genuine zero."""
