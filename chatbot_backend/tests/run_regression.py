"""
Run every regression case and report what broke.

    python -m tests.run_regression                 all cases
    python -m tests.run_regression --id shaft      only matching ids
    python -m tests.run_regression --repeat 3      each case N times (drift check)
    python -m tests.run_regression --no-cache      bypass the query cache

Run this after ANY change to the business terms, the semantic views, the schema
metadata or the agents. Every bug this project has shipped was found by a human
noticing a wrong number; the point of this file is that the machine notices
first.

Expected answers are recomputed from the database on every run (see cases.py),
so reloading the data does not invalidate the suite.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from langchain_core.messages import HumanMessage  # noqa: E402

from tests.cases import CASES  # noqa: E402


def _truth(sql: str):
    from sqlalchemy import text

    from backend.config import get_engine

    with get_engine().connect() as conn:
        row = conn.execute(text(sql)).fetchone()
    return None if row is None else row[0]


def _as_number(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:
        pass
    return None


def _single_value(result: Dict[str, Any]):
    rows = result.get("retrieved_data") or []
    if len(rows) == 1 and len(rows[0]) == 1:
        return next(iter(rows[0].values()))
    return None


def _numbers_in_single_row(result: Dict[str, Any]) -> List[float]:
    """
    Every numeric value on a one-row answer.

    "What is the total consumed quantity of the most consumed item" is properly
    answered with the item AND the figure - one row, several columns. Demanding
    a bare single value failed that on its SHAPE while the number was right.
    The check below passes if any number in the row matches, which tests what
    actually matters without dictating how the answer is laid out.
    """
    rows = result.get("retrieved_data") or []
    if len(rows) != 1:
        return []
    return [n for n in (_as_number(v) for v in rows[0].values()) if n is not None]


def _refused(result: Dict[str, Any]) -> bool:
    """
    The assistant declined rather than inventing an answer.

    Judged on the DATA, not the wording. Matching phrases like "not available"
    was too brittle - the same refusal gets worded a dozen ways, and a case
    would fail because the model chose "no matching records" that run. What
    matters is that it did not fabricate: an error, or no rows.
    """
    return bool(result.get("error")) or result.get("row_count", 0) == 0


# What a real user replies when the date-scope gate asks. The gate is correct
# behaviour - most questions do not state a period - so the suite has to answer
# it and carry on, or two thirds of the cases would "fail" by being asked a
# reasonable question.
_CLARIFY_REPLY = "All available dates"
_MAX_CLARIFY_TURNS = 2


def check(case: Dict[str, Any], result: Dict[str, Any]) -> tuple[bool, str]:
    kind = case["check"]

    if kind == "refuses":
        return (_refused(result), "declined" if _refused(result)
                else f"answered anyway with {result.get('row_count')} row(s)")

    if kind == "clarifies":
        ok = result.get("route") == "clarify"
        return ok, "asked" if ok else f"route={result.get('route')}, did not ask"

    if result.get("error"):
        return False, f"errored: {' '.join(str(result['error']).split())[:70]}"

    if kind == "rowcount":
        expected = _as_number(_truth(case["truth_sql"]))
        got = result.get("row_count")
        return got == expected, f"expected {expected} rows, got {got}"

    got_value = _single_value(result)
    got = _as_number(got_value)

    if kind == "nonzero":
        ok = got is not None and got > 0
        return ok, f"got {got_value!r}" + ("" if ok else " (expected a positive number)")

    if kind == "not_equal":
        # For traps where several answers are defensible but ONE is definitely
        # wrong - e.g. "Qadbros Engineering" may or may not include Unit-II, but
        # it must never return Qadri Engineering's figure.
        forbidden = _as_number(_truth(case["truth_sql"]))
        values = ([got] if got is not None else []) + _numbers_in_single_row(result)
        hit = [v for v in values if v is not None and abs(v - forbidden) < 1e-6]
        if hit:
            return False, f"returned the forbidden value {forbidden:,.0f}"
        shown = values[0] if values else result.get("row_count")
        return True, f"{shown:,.0f}" if isinstance(shown, float) else f"{shown}"

    if kind == "scalar":
        expected = _as_number(_truth(case["truth_sql"]))

        def matches(value: float) -> bool:
            # Tolerance for float noise only; integers must match exactly.
            return abs(value - expected) < max(1e-6, abs(expected) * 1e-9)

        if got is not None:
            return matches(got), (f"{got:,.0f}" if matches(got)
                                  else f"expected {expected:,.0f}, got {got:,.0f}")

        candidates = _numbers_in_single_row(result)
        for value in candidates:
            if matches(value):
                return True, f"{value:,.0f}"

        if candidates:
            return False, (f"expected {expected:,.0f}, row had "
                           + ", ".join(f"{v:,.0f}" for v in candidates))
        return False, (f"expected {expected:,.0f}, but got "
                       f"{result.get('row_count')} row(s) with no number in them")

    return False, f"unknown check type {kind!r}"


def _ask(graph, case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ask the question, answering the date-scope gate if it fires.

    Runs on ONE thread with the checkpointer, so the follow-up reply lands in
    the same conversation - which is also what exercises the follow-up path
    rather than a series of unrelated first turns.

    A case whose whole point is that the assistant SHOULD ask is left alone.
    """
    thread = f"rg-{case['id']}-{time.time()}"
    message = case["question"]

    for _ in range(_MAX_CLARIFY_TURNS + 1):
        result = graph.invoke(
            {"user_query": message,
             "messages": [HumanMessage(content=message)],
             "sql_attempts": 0, "sql_error": "", "error": ""},
            config={"configurable": {"thread_id": thread}},
        )
        if result.get("route") != "clarify" or case["check"] == "clarifies":
            return result
        message = _CLARIFY_REPLY

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="", help="only cases whose id contains this")
    parser.add_argument("--repeat", type=int, default=1, help="runs per case")
    parser.add_argument("--no-cache", action="store_true", help="bypass the query cache")
    args = parser.parse_args()

    if args.no_cache:
        import backend.config as config

        config.ENABLE_QUERY_CACHE = False

    from backend.graph.memory import get_checkpointer
    from backend.graph.workflow import build_graph

    # With memory, so answering the date-scope gate continues the SAME
    # conversation instead of starting a fresh one that has forgotten the
    # question.
    graph = build_graph(checkpointer=get_checkpointer())

    cases = [c for c in CASES if args.id.lower() in c["id"].lower()]
    if not cases:
        print(f"no cases match {args.id!r}")
        return 2

    failures: List[str] = []
    unstable: List[str] = []
    started = time.time()

    print(f"running {len(cases)} case(s)"
          + (f" x{args.repeat}" if args.repeat > 1 else "") + "\n")

    for case in cases:
        outcomes, details = set(), []
        for _ in range(args.repeat):
            try:
                result = _ask(graph, case)
                ok, detail = check(case, result)
            except Exception as exc:
                ok, detail = False, f"EXCEPTION {type(exc).__name__}: {exc}"
            outcomes.add(ok)
            details.append(detail)

        passed = all(outcomes)
        drifted = len(outcomes) > 1

        mark = "PASS" if passed else "FAIL"
        if drifted:
            mark = "DRIFT"
            unstable.append(case["id"])
        if not passed and not drifted:
            failures.append(case["id"])

        print(f"  [{mark:5}] {case['id']:26} {details[0]}")
        if drifted or not passed:
            print(f"          Q: {case['question']}")
            print(f"          why this case exists: {case['why']}")
            for i, d in enumerate(details[1:], 2):
                print(f"          run {i}: {d}")

    total = len(cases)
    bad = len(failures) + len(unstable)
    print(f"\n{total - bad}/{total} passed in {time.time() - started:.0f}s")
    if failures:
        print(f"  failed:   {', '.join(failures)}")
    if unstable:
        print(f"  unstable: {', '.join(unstable)}  (same question, different verdicts)")

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
