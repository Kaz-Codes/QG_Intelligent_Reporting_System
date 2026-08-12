"""
Every question and answer, on disk, against the user who asked it.

Two things this fixes.

AUDIT. Conversations lived only in LangGraph's InMemorySaver, so they vanished
on restart and nobody could answer "who asked what about our data". This table
is the record: one row per message, with the user id, the thread, and - for an
assistant reply - the route taken, the SQL that ran and how many rows came back.
That last part matters when somebody disputes a number weeks later: the query
that produced it is right there.

OWNERSHIP. Because every row carries a user_id, history can be scoped to the
person asking. Before this, /chat/{thread_id}/history replayed any thread to
anyone holding the id, and a thread id left in localStorage survived logout - so
the next person to sign in on that machine was shown the previous user's
conversation.

Deliberately NOT in the ERP's models: this is the chatbot's own data, and
app/loading/scripts/load_all.py drops the tables it owns on every reload. Being
outside that list is what stops a data reload wiping the audit trail.

Writes are best-effort. A failure to log must never cost the user their answer,
so every function here swallows its exceptions - the log is evidence, not part
of the request path.
"""

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.config import get_engine

_TABLE = "chatbot_messages"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id          BIGSERIAL PRIMARY KEY,
    thread_id   TEXT        NOT NULL,
    user_id     INTEGER,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    route       TEXT,
    sql_text    TEXT,
    row_count   INTEGER,
    meta        JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS {_TABLE}_thread_idx  ON {_TABLE} (thread_id, id);
CREATE INDEX IF NOT EXISTS {_TABLE}_user_idx    ON {_TABLE} (user_id, created_at DESC);
"""

_ready = False


def ensure_table() -> bool:
    """Create the table if absent. Cheap enough to call on every write."""
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


def log_turn(
    thread_id: str,
    user_id: Optional[int],
    question: str,
    answer: str,
    route: str = "",
    sql_text: str = "",
    row_count: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Record one exchange. Never raises."""
    if not ensure_table():
        return
    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {_TABLE} "
                    "(thread_id, user_id, role, content) "
                    "VALUES (:t, :u, 'user', :c)"
                ),
                {"t": thread_id, "u": user_id, "c": question},
            )
            conn.execute(
                text(
                    f"INSERT INTO {_TABLE} "
                    "(thread_id, user_id, role, content, route, sql_text, row_count, meta) "
                    "VALUES (:t, :u, 'assistant', :c, :r, :s, :n, CAST(:m AS JSONB))"
                ),
                {
                    "t": thread_id,
                    "u": user_id,
                    "c": answer,
                    "r": route or None,
                    "s": sql_text or None,
                    "n": row_count,
                    "m": json.dumps(meta or {}, default=str),
                },
            )
    except Exception:
        pass


def thread_owner(thread_id: str) -> Optional[int]:
    """
    The user this thread belongs to, or None if unknown/unowned.

    Whoever asked the FIRST question owns it. A thread with no owner (created
    before this table existed, or by an anonymous request) returns None and the
    caller decides.
    """
    if not ensure_table():
        return None
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    f"SELECT user_id FROM {_TABLE} "
                    "WHERE thread_id = :t AND user_id IS NOT NULL "
                    "ORDER BY id LIMIT 1"
                ),
                {"t": thread_id},
            ).first()
        return row[0] if row else None
    except Exception:
        return None


def recent_threads(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """That user's own conversations, most recent first."""
    if not ensure_table():
        return []
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT thread_id,
                           MIN(created_at) AS started_at,
                           MAX(created_at) AS last_at,
                           COUNT(*) FILTER (WHERE role = 'user') AS questions,
                           (ARRAY_AGG(content ORDER BY id)
                              FILTER (WHERE role = 'user'))[1] AS first_question
                    FROM {_TABLE}
                    WHERE user_id = :u
                    GROUP BY thread_id
                    ORDER BY MAX(created_at) DESC
                    LIMIT :n
                    """
                ),
                {"u": user_id, "n": limit},
            ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        return []
