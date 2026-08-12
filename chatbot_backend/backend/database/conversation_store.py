"""
The whole conversation, as the UI renders it, kept per user.

Separate from chatbot_messages (the append-only audit log) on purpose. That one
answers "who asked what" - one immutable row per message, never edited, never
hidden. THIS one is the user's working conversation: the exact message objects
the Assistant page draws, upserted as the thread grows, so signing back in or
returning later restores the screen they left - tables, charts and all.

WHY THE WHOLE FRONTEND OBJECT. Re-deriving what the UI shows from the backend's
own response would drift the moment either side changed: the rendered message
carries client-side fields (the id, clarification options it is offering, which
message failed) that no server payload has. Storing what the client actually
renders makes "print it the same way" true by construction rather than by
keeping two shapes in step.

STATUS. Deleting a conversation is a SOFT delete - status goes to 'deleted' and
the row stays. The user stops seeing it; the audit trail and the record of what
was asked survive. Nothing here is ever hard-deleted.

SIZE. An answer can carry thousands of rows, so the stored copy caps rows per
message (MAX_ROWS_PER_MESSAGE) and records that it did. The prose, columns and
charts are always kept whole - a restored conversation may show a shorter table
than the live one did, but never a wrong one.
"""

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.config import get_engine

_TABLE = "chatbot_conversations"

# Beyond this, a restored table is scrolling rather than reading, and the JSON
# starts costing more than it returns. The live answer is unaffected; only the
# stored copy is trimmed.
MAX_ROWS_PER_MESSAGE = 2000

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    thread_id   TEXT        PRIMARY KEY,
    user_id     INTEGER     NOT NULL,
    messages    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    status      TEXT        NOT NULL DEFAULT 'active',
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS {_TABLE}_user_idx
    ON {_TABLE} (user_id, status, updated_at DESC);
"""

_ready = False


def ensure_table() -> bool:
    global _ready
    if _ready:
        return True
    try:
        with get_engine().begin() as conn:
            conn.execute(text(_DDL))
        _ready = True
    except Exception:
        _ready = False
    return _ready


def _trim(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Cap the row payload per message; keep everything else intact."""
    out = []
    for m in messages or []:
        m = dict(m)
        rows = m.get("rows")
        if isinstance(rows, list) and len(rows) > MAX_ROWS_PER_MESSAGE:
            m["rows"] = rows[:MAX_ROWS_PER_MESSAGE]
            m["rowsTruncated"] = len(rows)
        out.append(m)
    return out


def save(thread_id: str, user_id: int, messages: List[Dict[str, Any]]) -> bool:
    """
    Upsert the conversation. Returns False on any failure - saving must never
    cost the user their answer.

    Re-saving a thread the user does not own is refused rather than silently
    overwriting somebody else's conversation.
    """
    if not thread_id or user_id is None or not ensure_table():
        return False
    try:
        payload = json.dumps(_trim(messages), default=str)
        title = ""
        for m in messages or []:
            if m.get("role") == "user" and m.get("content"):
                title = str(m["content"])[:120]
                break
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {_TABLE} (thread_id, user_id, messages, title, status)
                    VALUES (:t, :u, CAST(:m AS JSONB), :ti, 'active')
                    ON CONFLICT (thread_id) DO UPDATE
                       SET messages   = EXCLUDED.messages,
                           title      = COALESCE({_TABLE}.title, EXCLUDED.title),
                           updated_at = now()
                     WHERE {_TABLE}.user_id = EXCLUDED.user_id
                    """
                ),
                {"t": thread_id, "u": user_id, "m": payload, "ti": title},
            )
        return True
    except Exception:
        return False


def append_turn(
    thread_id: str,
    user_id: Optional[int],
    question: str,
    payload: Dict[str, Any],
) -> bool:
    """
    Append one exchange to the stored conversation, server-side.

    The conversation used to be saved only when the BROWSER sent it back after
    each turn. That made persistence depend on a client call succeeding - and
    when the proxy did not route /conversation, every one of those calls 404'd
    and the table stayed empty with nothing reporting a problem. Storage should
    not hinge on the client remembering to ask.

    So the server appends as it answers. The two message objects are built in
    the shape the Assistant page renders, so a restored conversation still
    draws tables and charts exactly as it did live; the browser's PUT is now
    belt-and-braces that refines the same row rather than the only thing
    creating it.

    A conversation the user deleted is NOT resurrected: appending to a
    'deleted' thread leaves it deleted, so asking again in an old thread does
    not undo the delete.
    """
    if not thread_id or user_id is None or not ensure_table():
        return False

    rows = payload.get("rows") or []
    assistant: Dict[str, Any] = {
        "role": "assistant",
        "content": payload.get("answer", ""),
        "columns": payload.get("columns") or [],
        "rows": rows,
        "charts": payload.get("charts") or [],
        "clarificationOptions": payload.get("clarification_options") or [],
        "meta": {
            "route": payload.get("route", ""),
            "domain": payload.get("domain", ""),
            "intent": payload.get("intent", ""),
            "rowCount": payload.get("row_count"),
            "sql": payload.get("sql", ""),
            "analysisType": payload.get("analysis_type", ""),
        },
    }
    turn = _trim([{"role": "user", "content": question}, assistant])

    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {_TABLE} (thread_id, user_id, messages, title, status)
                    VALUES (:t, :u, CAST(:m AS JSONB), :ti, 'active')
                    ON CONFLICT (thread_id) DO UPDATE
                       SET messages   = {_TABLE}.messages || CAST(:m AS JSONB),
                           updated_at = now()
                     WHERE {_TABLE}.user_id = EXCLUDED.user_id
                    """
                ),
                {
                    "t": thread_id,
                    "u": user_id,
                    "m": json.dumps(turn, default=str),
                    "ti": (question or "")[:120],
                },
            )
        return True
    except Exception:
        return False


def latest(user_id: int) -> Optional[Dict[str, Any]]:
    """That user's most recent ACTIVE conversation, or None."""
    if user_id is None or not ensure_table():
        return None
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT thread_id, messages, updated_at
                    FROM {_TABLE}
                    WHERE user_id = :u AND status = 'active'
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """
                ),
                {"u": user_id},
            ).mappings().first()
        if not row:
            return None
        return {
            "thread_id": row["thread_id"],
            "messages": row["messages"] or [],
            "updated_at": row["updated_at"],
        }
    except Exception:
        return None


def soft_delete(thread_id: str, user_id: int) -> bool:
    """
    Hide a conversation from the user without losing it.

    The row stays, with status='deleted', so the record of what was asked
    survives even though the user has cleared their screen. Scoped by user_id
    so nobody can hide somebody else's conversation.
    """
    if not thread_id or user_id is None or not ensure_table():
        return False
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {_TABLE} SET status = 'deleted', updated_at = now() "
                    "WHERE thread_id = :t AND user_id = :u"
                ),
                {"t": thread_id, "u": user_id},
            )
        return True
    except Exception:
        return False


def owner(thread_id: str) -> Optional[int]:
    if not thread_id or not ensure_table():
        return None
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(f"SELECT user_id FROM {_TABLE} WHERE thread_id = :t"),
                {"t": thread_id},
            ).first()
        return row[0] if row else None
    except Exception:
        return None
