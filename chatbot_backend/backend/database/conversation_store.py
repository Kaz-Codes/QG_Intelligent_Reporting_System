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

# How many conversations a user keeps. Beyond this the oldest are retired by
# prune_old - retired, not removed: the row and its audit trail stay, the user
# simply stops being offered it in the sidebar.
KEEP_CONVERSATIONS = 10

# Sidebar width, essentially. Long enough that two questions about the same
# table are still tellable apart, short enough not to wrap.
TITLE_MAX_CHARS = 60

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


def derive_title(messages: List[Dict[str, Any]]) -> str:
    """Name a conversation after the first thing the user asked in it.

    DELIBERATELY NOT AN LLM CALL. A generated title would read a little better
    and would cost a request, a latency budget and a failure mode on every new
    conversation - for a label. This is deterministic, free, and cannot fail:
    the worst case is a blunt title, not a missing one.

    Newlines are flattened because a pasted multi-line question would otherwise
    make one sidebar row as tall as the rest of the list. The ellipsis is
    included IN the limit, so the result is never wider than TITLE_MAX_CHARS.
    """
    for m in messages or []:
        if m.get("role") != "user":
            continue

        content = m.get("content")
        if not content:
            continue

        # Any whitespace run - newline, tab, double space - becomes one space.
        text_value = " ".join(str(content).split())
        if not text_value:
            continue

        if len(text_value) <= TITLE_MAX_CHARS:
            return text_value

        return text_value[:TITLE_MAX_CHARS - 1].rstrip() + "…"

    # Lazy creation means a stored conversation always has a user message, so
    # this is for a caller asking before anything was said - a draft that has
    # not been persisted yet.
    return "New chat"


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
        # Only used when this INSERT is the one that creates the row - the
        # ON CONFLICT below keeps whatever title is already stored.
        title = derive_title(messages)
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO {_TABLE} (thread_id, user_id, messages, title, status)
                    VALUES (:t, :u, CAST(:m AS JSONB), :ti, 'active')
                    ON CONFLICT (thread_id) DO UPDATE
                       SET messages   = EXCLUDED.messages,
                           -- TITLE IS SET ONCE AND NEVER OVERWRITTEN. A chat's
                           -- name should stay put as it grows, and when
                           -- renaming arrives the user's own title must not be
                           -- silently replaced by the first question again.
                           -- COALESCE also backfills a row stored before
                           -- titles were derived.
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
                           -- COALESCE, not assignment: fills in a title only
                           -- where the row has none (one stored before titles
                           -- existed), and leaves any existing one alone.
                           title      = COALESCE({_TABLE}.title, EXCLUDED.title),
                           updated_at = now()
                     WHERE {_TABLE}.user_id = EXCLUDED.user_id
                    """
                ),
                {
                    "t": thread_id,
                    "u": user_id,
                    "m": json.dumps(turn, default=str),
                    # Same derivation save() uses, so a conversation is
                    # named identically whichever path created it. Read only
                    # on INSERT - the ON CONFLICT above deliberately does not
                    # touch title.
                    "ti": derive_title([{"role": "user", "content": question}]),
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


def list_conversations(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """That user's active conversations, newest first - what the sidebar draws.

    NO MESSAGES PAYLOAD, deliberately. A sidebar needs a name and a date; the
    messages column holds every table the assistant has ever returned, capped
    at MAX_ROWS_PER_MESSAGE *per message*, so selecting it for fifty rows could
    pull tens of megabytes to render a list of titles. The count comes from the
    database instead - get_conversation fetches the body when one is opened.

    Served entirely by the (user_id, status, updated_at DESC) index: the WHERE
    matches its first two columns and the ORDER BY its third, so this is an
    index range scan however large the table becomes.

    Returns [] on failure rather than raising, like everything else here. A
    chatbot with no history is usable; a chatbot that will not load is not.
    """
    if user_id is None or not ensure_table():
        return []
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT thread_id,
                           title,
                           updated_at,
                           created_at,
                           -- Guarded rather than a bare jsonb_array_length:
                           -- that raises on a non-array, and one malformed row
                           -- would take the WHOLE sidebar down with it. The
                           -- column is NOT NULL DEFAULT '[]' and only ever
                           -- written from a list, so this should never fire -
                           -- but degrading one row to 0 beats degrading the
                           -- list to nothing.
                           CASE WHEN jsonb_typeof(messages) = 'array'
                                THEN jsonb_array_length(messages)
                                ELSE 0
                           END AS message_count
                    FROM {_TABLE}
                    WHERE user_id = :u AND status = 'active'
                    ORDER BY updated_at DESC
                    LIMIT :n
                    """
                ),
                {"u": user_id, "n": limit},
            ).mappings().all()

        return [
            {
                "thread_id": r["thread_id"],
                # A row stored before titles were derived has none; name it
                # here rather than letting the sidebar render a blank line.
                "title": r["title"] or "Untitled chat",
                "updated_at": r["updated_at"],
                "created_at": r["created_at"],
                "message_count": r["message_count"],
            }
            for r in rows
        ]
    except Exception:
        return []


def get_conversation(thread_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    """One conversation in full - what opening a sidebar entry loads.

    SCOPED BY user_id IN THE WHERE CLAUSE, not checked after the fetch. A
    thread_id is a guessable opaque string and this returns the entire contents
    of a conversation, so ownership is part of the question asked of the
    database rather than a comparison somebody can later refactor away. A
    thread that does not exist and one belonging to somebody else are the same
    None, which is also what stops this being used to probe for valid ids.

    Deleted threads are not returned: the user cleared it, so it is not theirs
    to reopen from the sidebar. The row itself survives - see the module note.
    """
    if not thread_id or user_id is None or not ensure_table():
        return None
    try:
        with get_engine().connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT thread_id, title, messages, created_at, updated_at
                    FROM {_TABLE}
                    WHERE thread_id = :t
                      AND user_id = :u
                      AND status = 'active'
                    """
                ),
                {"t": thread_id, "u": user_id},
            ).mappings().first()

        if not row:
            return None

        return {
            "thread_id": row["thread_id"],
            "title": row["title"] or "Untitled chat",
            "messages": row["messages"] or [],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    except Exception:
        return None


def prune_old(user_id: int, keep: int = KEEP_CONVERSATIONS) -> int:
    """Retire this user's conversations beyond the most recent `keep`.

    RETIRES, NEVER DELETES. status goes to 'deleted' and the row stays, the
    same as a user clearing one by hand - the module note and the ON DELETE
    RESTRICT on the users FK both say history outlives the user's own view of
    it. A DELETE FROM here would quietly make that untrue for the oldest
    conversations of every busy user.

    ONE STATEMENT, not a select followed by a loop of updates. A loop reads a
    list and then acts on it, and anything arriving in between - the user
    asking a question in another tab, which moves a thread's updated_at - is
    acted on with a stale idea of the order. Here the subquery evaluates
    against the same snapshot as the update.

    Returns how many were retired.
    """
    if user_id is None or not ensure_table():
        return 0
    try:
        with get_engine().begin() as conn:
            result = conn.execute(
                text(
                    f"""
                    UPDATE {_TABLE}
                       SET status = 'deleted', updated_at = now()
                     WHERE user_id = :u
                       AND status = 'active'
                       AND thread_id NOT IN (
                             SELECT thread_id
                             FROM {_TABLE}
                             WHERE user_id = :u AND status = 'active'
                             ORDER BY updated_at DESC
                             LIMIT :k
                           )
                    """
                ),
                {"u": user_id, "k": keep},
            )
        return result.rowcount or 0
    except Exception:
        return 0


def soft_delete(thread_id: str, user_id: int) -> bool:
    """
    Hide ONE conversation from its owner without losing it.

    The row stays, with status='deleted', so the record of what was asked
    survives even though the user has cleared it from their sidebar. Scoped by
    user_id so nobody can hide somebody else's conversation.

    THIS USED TO RETIRE EVERY ACTIVE THREAD OF THEIRS, and the reason is worth
    keeping. The user was shown exactly one conversation - restore served the
    most recently updated ACTIVE row - and there was no UI anywhere for
    reaching an older one. Clearing only the thread on screen therefore left
    earlier conversations active with nothing able to select them, and the next
    sign-in simply promoted the next one up: the user pressed clear, came back,
    and found a chat still sitting there. It looked like the delete had not
    worked, or worse like a deleted conversation had come back. Sweeping them
    all was the only way to make "clear" mean what it said.

    THE SIDEBAR REMOVES THE CONDITION THAT MADE THAT NECESSARY. Every active
    conversation is now reachable and selectable, so an untouched older thread
    is not orphaned - it is simply the next row in a list the user can see. The
    sweep would now be the surprising behaviour: deleting one chat would take
    the other nine with it.

    So this deletes the named thread and nothing else. What has not changed is
    that nothing is ever destroyed - the row, and the audit log beside it, are
    kept either way.
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
                       AND thread_id = :t
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
