"""
LLM call logging.

Every model call in the app goes through config.get_llm(), so attaching one
callback handler there captures them all - no agent needs to know about this.
For each call it prints, to the terminal:

  * a running call number and the session's total call count
  * the messages sent (system + human), truncated so a big schema prompt does
    not flood the terminal
  * the answer, or the structured tool-call the model returned
  * token usage for the call and the running session total

Toggle with LOG_LLM in .env; cap per-message length with LOG_LLM_MAX_CHARS.
This is a dev/observability aid - set LOG_LLM=false to silence it entirely.
"""

import sys
import threading
from itertools import count

from langchain_core.callbacks import BaseCallbackHandler

from backend.config import LOG_LLM, LOG_LLM_MAX_CHARS

_lock = threading.Lock()
_counter = count(1)
_active = {}  # run_id -> call number, to pair a start with its end
_totals = {"in": 0, "out": 0}

_LINE = "=" * 72


def _safe_print(text: str) -> None:
    """
    Print, tolerating consoles that cannot encode the text.

    Windows terminals default to the system codepage (e.g. cp1252), which
    cannot represent a lot of what shows up in real data and in this file's
    own box-drawing/emoji formatting (Ø in item specs, em dashes, …). Without
    this, a call is logged as a swallowed "Error in LLMLogger callback" and
    the line is lost entirely - better to print it with the offending
    characters replaced than not print it at all.
    """
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or "ascii"
        print(text.encode(encoding, errors="replace").decode(encoding), flush=True)


def _truncate(text: str) -> str:
    limit = LOG_LLM_MAX_CHARS
    if limit <= 0 or len(text) <= limit:
        return text
    return f"{text[:limit]}  …(+{len(text) - limit} more chars)"


def _as_text(content) -> str:
    """Flatten a message's content to text, including Responses API blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "reasoning":
                    parts.append("[reasoning omitted]")
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p)
    return str(content)


def _model_name(serialized, kwargs) -> str:
    invocation = (kwargs or {}).get("invocation_params") or {}
    if invocation.get("model"):
        return invocation["model"]
    kw = (serialized or {}).get("kwargs") or {}
    return kw.get("model") or kw.get("model_name") or "?"


class LLMLogger(BaseCallbackHandler):
    """Prints every chat-model request and response to stdout."""

    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs):
        if not LOG_LLM:
            return
        n = next(_counter)
        with _lock:
            _active[run_id] = n
            total = n

        model = _model_name(serialized, kwargs)
        lines = [
            f"\n{_LINE}",
            f"\U0001F535 LLM CALL #{n}   model={model}   (session: {total} call(s))",
            f"{'─' * 30} SENT {'─' * 36}",
        ]
        # messages is a list of prompts; each prompt is a list of messages.
        for prompt in messages:
            for msg in prompt:
                role = getattr(msg, "type", "message")
                lines.append(f"[{role}] {_truncate(_as_text(msg.content))}")
        _safe_print("\n".join(lines))

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        if not LOG_LLM:
            return
        with _lock:
            n = _active.pop(run_id, "?")

        answer, tool_calls, usage = "", [], {}
        try:
            gen = response.generations[0][0]
            answer = _as_text(getattr(gen, "text", "") or "")
            message = getattr(gen, "message", None)
            if message is not None:
                if not answer:
                    answer = _as_text(message.content)
                tool_calls = getattr(message, "tool_calls", None) or []
                usage = getattr(message, "usage_metadata", None) or {}
        except (IndexError, AttributeError):
            pass

        if not usage:
            usage = (response.llm_output or {}).get("token_usage", {}) or {}

        tokens_in = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
        tokens_out = usage.get("output_tokens") or usage.get("completion_tokens") or 0
        with _lock:
            _totals["in"] += tokens_in
            _totals["out"] += tokens_out
            run_in, run_out = _totals["in"], _totals["out"]

        lines = [f"{'─' * 29} ANSWER #{n} {'─' * 30}"]
        if tool_calls:
            for call in tool_calls:
                lines.append(
                    f"tool_call → {call.get('name', '?')} {_truncate(str(call.get('args', {})))}"
                )
        if answer:
            lines.append(_truncate(answer))
        if not tool_calls and not answer:
            lines.append("(empty response)")
        lines.append(
            f"tokens: in={tokens_in} out={tokens_out}   "
            f"(session total: in={run_in} out={run_out})"
        )
        lines.append(_LINE)
        _safe_print("\n".join(lines))

    def on_llm_error(self, error, *, run_id=None, **kwargs):
        if not LOG_LLM:
            return
        with _lock:
            n = _active.pop(run_id, "?")
        _safe_print(f"{'─' * 29} ERROR #{n} {'─' * 31}\n{error}\n{_LINE}")


# One shared instance attached to the model in config.get_llm().
llm_logger = LLMLogger()
