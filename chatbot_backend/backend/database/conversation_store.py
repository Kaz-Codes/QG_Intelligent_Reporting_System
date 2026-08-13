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

# user_id IS users.id - the same value the ERP puts in the session token - so a
# conversation joins straight to its owner:
#
#   SELECT u.username, c.title, c.updated_at
#     FROM chatbot_conversations c JOIN users u ON u.id = c.user_id
#
# The foreign key makes that relationship real rather than conventional: a row
# can no longer be written against a user who does not exist, which is what
# keeps "whose chat is this" answerable months later.
#
# RESTRICT, not CASCADE. Deleting a user must not silently delete the record of
# what they asked - the whole point of soft-deleting conversations is that the
# history outlives the user's own clearing of it. Deactivate users
# (users.is_active) rather than removing them.
_FK = f"""
ALTER TABLE {_TABLE}
  ADD CONSTRAINT {_TABLE}_user_fk
  FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE RESTRICT
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
    if _ready:
        _link_to_users()
    return _ready


def _link_to_users() -> None:
    """
    Add the users foreign key if it is not already there.

    Deliberately separate from ensure_table and deliberately silent on failure.
    The constraint is an integrity improvement, not a precondition for storing
    a conversation - if the users table lives elsewhere, or existing rows do
    not satisfy it, the right outcome is an unlinked table that still saves
    chats, not a chatbot that has quietly stopped remembering anything.
    """
    try:
        with get_engine().begin() as conn:
            exists = conn.execute(
                text(
                    "SELECT 1 FROM pg_constraint WHERE conname = :n "
                    "AND conrelid = CAST(:t AS regclass)"
                ),
                {"n": f"{_TABLE}_user_fk", "t": _TABLE},
            ).first()
            if not exists:
                conn.execute(text(_FK))
    except Exception:
        pass


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
    # ensure_table FIRST, deliberately. Written as
    # `user_id is None or not ensure_table()` this short-circuits, so on a
    # machine where nobody can be identified - a mismatched JWT secret, say -
    # the table was never created at all. That turned one configuration fault
    # into two symptoms that look unrelated: no conversations AND no table to
    # put them in, which sends you looking for a schema or migration problem
    # that does not exist. The schema should not depend on who is asking.
    ready = ensure_table()
    if not ready or not thread_id or user_id is None:
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
    Hide this user's conversation from them without losing it.

    The rows stay, with status='deleted', so the record of what was asked
    survives even though the user has cleared their screen. Scoped by user_id
    so nobody can hide somebody else's conversation.

    RETIRES EVERY ACTIVE THREAD OF THEIRS, not only the named one. The user is
    shown exactly one conversation - restore serves the most recently updated
    ACTIVE row - and there is no UI anywhere for reaching an older one. So
    clearing only the thread on screen left earlier conversations active with
    nothing to select them, and the next sign-in simply promoted the next one
    up: the user pressed clear, came back, and found a chat still sitting
    there. It looked like the delete had not worked, or worse like a deleted
    conversation had come back.

    "Clear" therefore means what it says - this person's chat history stops
    being shown - while every row, and the audit log beside it, is kept.
    """
    if not thread_id or user_id is None or not ensure_table():
        return False
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    f"""
                    UPDATE {_TABLE}
                       SET status = 'deleted', updated_at = now()
                     WHERE user_id = :u
                       AND (thread_id = :t OR status = 'active')
                    """
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
