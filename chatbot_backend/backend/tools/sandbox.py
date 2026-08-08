"""
Sandboxed execution of LLM-generated analysis code.

This is what lets the assistant build its own tool for a question and run it:
the compute agent writes a short Python snippet, and this module validates and
executes it against the query results.

SAFETY MODEL
The code is written by our own LLM, not an external attacker, so the goal is to
stop it doing anything dumb or destructive - not to withstand a determined
adversary. The guards, in layers:

  1. AST validation rejects imports, `while` loops, access to dunder attributes
     (the usual sandbox-escape path), and a blocklist of dangerous names.
  2. Execution uses a curated __builtins__ - open/exec/eval/getattr/etc. simply
     do not exist in the namespace, so even a missed AST case fails with
     NameError rather than doing harm.
  3. Only safe libraries are pre-injected (pandas, numpy, math, statistics).
     There is no `import`, so nothing else is reachable.
  4. A worker-thread timeout bounds runaway code.

It is NOT a substitute for OS-level isolation. Keep ENABLE_COMPUTE off if you do
not want any generated code to run.
"""

import ast
import builtins
import math
import statistics
import threading
from typing import Any, List

import numpy as np
import pandas as pd

from backend.tools.postgres_tools import _to_jsonable as to_jsonable


class SafeExecutionError(RuntimeError):
    """Raised when generated code is rejected or fails to run safely."""


# Names that must never appear, even though most are also absent from the
# curated builtins. Belt and braces.
_FORBIDDEN_NAMES = frozenset(
    {
        "open", "exec", "eval", "compile", "__import__", "input", "globals",
        "locals", "vars", "getattr", "setattr", "delattr", "breakpoint",
        "memoryview", "help", "dir", "exit", "quit", "object", "super",
        "classmethod", "staticmethod", "property", "type", "os", "sys",
        "subprocess", "socket", "shutil", "pathlib", "importlib", "builtins",
        "ctypes", "signal", "threading", "multiprocessing", "gc", "inspect",
    }
)

# The only builtins the code may use. Everything else (open, exec, __import__,
# getattr, ...) is simply not present.
_ALLOWED_BUILTINS = frozenset(
    {
        "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter",
        "float", "format", "int", "len", "list", "map", "max", "min", "pow",
        "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple",
        "zip", "isinstance", "print",
    }
)


class _Validator(ast.NodeVisitor):
    """Walks the AST and raises on anything outside the safe subset."""

    def visit_Import(self, node):  # noqa: N802
        raise SafeExecutionError("imports are not allowed in computation code")

    def visit_ImportFrom(self, node):  # noqa: N802
        raise SafeExecutionError("imports are not allowed in computation code")

    def visit_While(self, node):  # noqa: N802
        # Vectorised pandas/numpy never needs while; blocking it removes the
        # easiest way to write an infinite loop.
        raise SafeExecutionError("while loops are not allowed")

    def visit_Attribute(self, node):  # noqa: N802
        # Dunder attribute access (__globals__, __class__, __subclasses__, ...)
        # is the classic escape from a restricted namespace.
        if isinstance(node.attr, str) and node.attr.startswith("_"):
            raise SafeExecutionError(f"access to attribute '{node.attr}' is not allowed")
        self.generic_visit(node)

    def visit_Name(self, node):  # noqa: N802
        if node.id in _FORBIDDEN_NAMES:
            raise SafeExecutionError(f"use of '{node.id}' is not allowed")
        self.generic_visit(node)


def validate_code(code: str) -> ast.Module:
    """Parse and validate. Returns the AST, or raises SafeExecutionError."""
    try:
        tree = ast.parse(code, filename="<computation>", mode="exec")
    except SyntaxError as exc:
        raise SafeExecutionError(f"syntax error: {exc}") from exc
    _Validator().visit(tree)
    return tree


def _safe_builtins() -> dict:
    return {name: getattr(builtins, name) for name in _ALLOWED_BUILTINS}


def _coerce_result(value: Any) -> Any:
    """
    Turn whatever the code produced into something JSON-serialisable.

    No row cap on a DataFrame/Series result - the app shows the user
    everything, same as a SQL result. (The response agent's own prompt takes a
    separate small sample of a table result for its own reasoning - see
    response_prompt.build_response_prompt - so an enormous computed table
    still costs little in tokens; this is what the user actually gets back.)
    """
    if value is None:
        return None
    if isinstance(value, pd.DataFrame):
        return {
            "kind": "table",
            "columns": list(value.columns.astype(str)),
            "rows": [
                {str(k): to_jsonable(v) for k, v in record.items()}
                for record in value.to_dict(orient="records")
            ],
        }
    if isinstance(value, pd.Series):
        return {str(k): to_jsonable(v) for k, v in value.to_dict().items()}
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _coerce_result(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_result(v) for v in value]
    return to_jsonable(value)


def run_code(code: str, rows: List[dict], timeout: float = 10.0) -> Any:
    """
    Validate and execute `code`, returning its `result` variable, coerced to a
    JSON-serialisable value.

    The code runs with `df` (a DataFrame of `rows`), `pd`, `np`, `math` and
    `statistics` available, and must assign its answer to a variable named
    `result`. Raises SafeExecutionError on rejection, error or timeout.
    """
    validate_code(code)

    namespace = {
        "__builtins__": _safe_builtins(),
        "pd": pd,
        "np": np,
        "math": math,
        "statistics": statistics,
        "df": pd.DataFrame(rows or []),
        "rows": rows or [],
        "columns": list(rows[0].keys()) if rows else [],
    }

    outcome: dict = {}

    def _worker():
        try:
            exec(compile(code, "<computation>", "exec"), namespace)  # noqa: S102
            outcome["value"] = namespace.get("result", None)
        except Exception as exc:  # surface the real error for a retry
            outcome["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        # The thread cannot be force-killed, but the restricted namespace limits
        # what a runaway can touch. Report it as a failure.
        raise SafeExecutionError(f"computation exceeded the {timeout:g}s time limit")

    if "error" in outcome:
        raise SafeExecutionError(outcome["error"])

    if "value" not in outcome or outcome["value"] is None:
        raise SafeExecutionError("code did not assign a `result` value")

    return _coerce_result(outcome["value"])
