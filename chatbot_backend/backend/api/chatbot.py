"""
Chat API routes.

One endpoint does the work: POST /chat. The client sends a message and a
thread_id; the thread_id is what gives the conversation memory - reuse it for
follow-up questions in the same chat, generate a new one for a new chat.
"""

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from pydantic import BaseModel, Field

from backend.graph.memory import get_checkpointer
from backend.api.identity import current_user_id
from backend.database import chat_log, conversation_store
from backend.graph.workflow import build_graph
from backend.tools.postgres_tools import ping

router = APIRouter()

# What each graph node is doing, in the user's language. Shown as a live status
# line while the turn runs, so a 10-second answer is visibly progressing rather
# than a silent wait. Nodes absent from this map emit no status.
_NODE_LABELS = {
    "understand": "Understanding your question…",
    "resolve_item": "Checking which item you mean…",
    "context": "Looking up business terms…",
    "knowledge": "Working out what that means…",
    "generate_sql": "Writing the query…",
    "execute_sql": "Querying the database…",
    "analyze": "Analysing the results…",
    "forecast": "Running the forecast…",
    "compute": "Running calculations…",
    "retrieve_docs": "Searching documents…",
    "learn": "Remembering that…",
    "respond": "Writing the answer…",
}

# Built once at import: compiling the graph on every request would be wasteful,
# and the checkpointer has to be shared for memory to work.
_graph = build_graph(checkpointer=get_checkpointer())


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, description="The user's question.")
    thread_id: Optional[str] = Field(
        default=None,
        description="Conversation id. Omit to start a new conversation.",
    )


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    route: str = ""
    intent: str = ""
    domain: str = ""
    # When route == "clarify", the assistant is asking the user to confirm
    # something. clarification_options are tappable answer choices, if any.
    clarification_options: List[str] = []
    # The actual data behind a data answer, so the UI can render a real table
    # alongside the prose. Empty for docs/smalltalk answers.
    columns: List[str] = []
    rows: List[Dict[str, Any]] = []
    row_count: int = 0
    # Zero or more {type, x, y[], title} charts to draw from `rows`. The UI
    # renders each; rows and charts travel together.
    charts: List[Dict[str, Any]] = []
    # Debug fields - useful while building, hide them in the production UI.
    sql: str = ""
    tables_used: List[str] = []
    knowledge_inferred: bool = False
    analysis_type: str = ""
    forecast: Optional[Dict[str, Any]] = None
    forecast_skipped_reason: str = ""
    # When will we run out / need to reorder - dates and inputs computed from
    # current stock, lead time and purchase behaviour. None unless the question
    # asked about reorder/replenishment timing.
    reorder: Optional[Dict[str, Any]] = None
    # Dynamic computation: the code the assistant wrote and ran, and its output.
    computation_code: str = ""
    computation_explanation: str = ""
    computation_result: Any = None
    error: str = ""


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    thread_id = request.thread_id or str(uuid.uuid4())
    user_id = current_user_id(http_request)

    # A thread belongs to whoever started it. Refusing to continue somebody
    # else's is what stops a thread id left in a shared browser handing the
    # next person the previous user's conversation.
    owner = chat_log.thread_owner(thread_id)
    if owner is not None and user_id is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="That conversation belongs to another user.")

    try:
        result = _graph.invoke(
            {
                "user_query": request.message,
                # Scopes learned-term retrieval to this user.
                "user_id": user_id,
                "messages": [HumanMessage(content=request.message)],
                # Reset per-turn scratch fields so a retry budget or error from
                # the previous turn does not leak into this one.
                "sql_attempts": 0,
                "sql_error": "",
                "error": "",
            },
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc

    _maybe_persist_learned(result)
    _maybe_cache_query(result)
    response = _build_response(thread_id, result)
    chat_log.log_turn(
        thread_id=thread_id,
        user_id=user_id,
        question=request.message,
        answer=response.answer,
        route=result.get("route", ""),
        sql_text=result.get("sql", ""),
        row_count=result.get("row_count"),
        meta={"intent": result.get("intent", ""), "domain": result.get("domain", "")},
    )
    return response


def _build_response(thread_id: str, result: Dict[str, Any]) -> ChatResponse:
    """Shape the finished graph state into the API payload."""
    return ChatResponse(
        thread_id=thread_id,
        answer=result.get("final_response", ""),
        route=result.get("route", ""),
        intent=result.get("intent", ""),
        domain=result.get("domain", ""),
        clarification_options=result.get("clarification_options", []),
        columns=result.get("columns", []),
        rows=result.get("retrieved_data", []),
        row_count=result.get("row_count", 0),
        charts=result.get("charts", []),
        sql=result.get("sql", ""),
        tables_used=result.get("tables_used", []),
        knowledge_inferred=result.get("knowledge_inferred", False),
        analysis_type=result.get("analysis_type", ""),
        forecast=result.get("forecast_result"),
        forecast_skipped_reason=result.get("forecast_skipped_reason", ""),
        reorder=result.get("reorder_result") or None,
        computation_code=result.get("computation_code", ""),
        computation_explanation=result.get("computation_explanation", ""),
        computation_result=result.get("computation_result"),
        error=result.get("error", ""),
    )


def _chunk_text(message) -> str:
    """
    Plain text out of a streamed chunk.

    The Responses API streams content BLOCKS, not a bare string, and reasoning
    blocks must never reach the user - same filtering the response agent does
    on the final message, applied per chunk.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def _sse(payload: Dict[str, Any]) -> str:
    """One Server-Sent Event. `ensure_ascii=False` keeps real units/± intact."""
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def _event_stream(
    request: ChatRequest, thread_id: str, user_id: Optional[int] = None
) -> AsyncIterator[str]:
    """
    Run the graph, emitting progress as it goes.

    Two interleaved streams from LangGraph: "updates" fires as each node
    finishes (-> the status line) and "messages" carries the response agent's
    tokens (-> the answer typing in). Everything that is only known once the
    graph finishes - rows, charts, the forecast - rides in the final `done`
    event.
    """
    config = {"configurable": {"thread_id": thread_id}}
    yield _sse({"type": "start", "thread_id": thread_id})

    # "updates" only fires once a node has FINISHED, so the first real status
    # would not arrive until understanding completes - several seconds of
    # silence, which is exactly what streaming is meant to remove. Announce the
    # first step up front, then let node completions drive the rest (skipping
    # `understand` below so it is not shown twice).
    yield _sse({"type": "status", "node": "understand", "label": _NODE_LABELS["understand"]})
    # Hand control back to the event loop so the two events above are actually
    # written to the socket NOW. Without this the generator runs straight into
    # the blocking graph call and both events sit in the buffer until the first
    # node finishes - measured at 4s, which defeats the point of announcing the
    # first step up front.
    await asyncio.sleep(0)

    streamed_any_token = False
    try:
        async for mode, chunk in _graph.astream(
            {
                "user_query": request.message,
                # Scopes learned-term retrieval to this user.
                "user_id": user_id,
                "messages": [HumanMessage(content=request.message)],
                "sql_attempts": 0,
                "sql_error": "",
                "error": "",
            },
            config=config,
            stream_mode=["updates", "messages"],
        ):
            if mode == "updates":
                for node in chunk or {}:
                    if node == "understand":
                        continue  # already announced before the loop
                    label = _NODE_LABELS.get(node)
                    if label:
                        yield _sse({"type": "status", "node": node, "label": label})
            elif mode == "messages":
                message, meta = chunk
                # Only the response agent writes prose the user should see; every
                # other node uses structured output for internal decisions.
                if (meta or {}).get("langgraph_node") != "respond":
                    continue
                # The node ALSO returns the finished AIMessage into state, and
                # that full message is emitted here too - appending the whole
                # answer a second time after its own tokens. Only incremental
                # chunks are real stream output.
                if not isinstance(message, AIMessageChunk):
                    continue
                text = _chunk_text(message)
                if text:
                    streamed_any_token = True
                    yield _sse({"type": "token", "text": text})
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Chat failed: {exc}"})
        return

    try:
        snapshot = _graph.get_state(config)
        result = dict(snapshot.values) if snapshot else {}
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Could not read the result: {exc}"})
        return

    _maybe_persist_learned(result)
    _maybe_cache_query(result)
    payload = _build_response(thread_id, result).model_dump()
    # Clarification and teach replies short-circuit the LLM, so no tokens were
    # streamed - the client uses `answer` from here in that case.
    payload["streamed"] = streamed_any_token

    # Logged as the stream closes, so the record carries the answer the user
    # actually saw rather than a half-written one.
    chat_log.log_turn(
        thread_id=thread_id,
        user_id=user_id,
        question=request.message,
        answer=payload.get("answer", ""),
        route=payload.get("route", ""),
        sql_text=(result or {}).get("sql", ""),
        row_count=payload.get("row_count"),
        meta={"intent": payload.get("intent", ""), "domain": payload.get("domain", "")},
    )

    yield _sse({"type": "done", **payload})


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """
    Same turn as POST /chat, streamed as Server-Sent Events.

    Total time is unchanged; the point is that the user sees progress within a
    second and can start reading the answer as it is written, instead of
    staring at a spinner for the whole turn. POST /chat is kept for
    non-streaming clients.
    """
    thread_id = request.thread_id or str(uuid.uuid4())
    user_id = current_user_id(http_request)

    # A thread belongs to whoever started it. This is what stops a thread id
    # left in a shared browser continuing the previous user's conversation.
    owner = chat_log.thread_owner(thread_id)
    if owner is not None and user_id is not None and owner != user_id:
        raise HTTPException(status_code=403, detail="That conversation belongs to another user.")

    return StreamingResponse(
        _event_stream(request, thread_id, user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx-style proxies buffering the stream into one blob.
            "X-Accel-Buffering": "no",
        },
    )


def _maybe_persist_learned(result: Dict[str, Any]) -> None:
    """
    Save an inferred mapping only when it earned its place.

    The review gate: the Knowledge Agent had to derive the mapping (nothing was
    documented), it was CONFIDENT, and the query it fed actually ran cleanly and
    returned rows. A confident inference that produced real data is a strong
    signal the mapping was right - anything weaker is not persisted, so we do not
    pollute the store with guesses.
    """
    if not (
        result.get("knowledge_inferred")
        and result.get("knowledge_confident")
        and result.get("knowledge_notes")
        and result.get("sql")
        and not result.get("error")
        and not result.get("sql_error")
        and result.get("row_count", 0) > 0
    ):
        return

    from backend.tools.vector_tools import persist_learned_term

    try:
        persist_learned_term(
            result.get("rewritten_query") or result.get("user_query", ""),
            result["knowledge_notes"],
            confident=True,
            # Scoped to the asker: an inference made while answering one
            # person's question should not silently answer another's.
            user_id=result.get("user_id"),
        )
    except Exception:
        # Persistence is best-effort - never fail a good answer over it.
        pass


def _maybe_cache_query(result: Dict[str, Any]) -> None:
    """
    Remember the SQL that answered this, so the same question replays it.

    The gate is deliberately strict, because a cached query is replayed
    verbatim and a bad one would be wrong forever rather than once:

      * a query actually ran and returned ROWS - an empty result is the shape
        every silent filter bug takes, and is never worth making permanent
      * nothing errored, at either the generation or execution step
      * the zero-row guard did not have to intervene; if it did, the first
        attempt was wrong and the turn is not a clean example
      * it was not itself served from the cache, which would just rewrite the
        entry it came from
    """
    from backend.agents.sql_agent import _looks_empty

    if not (
        result.get("sql")
        and result.get("row_count", 0) > 0
        # A COUNT that came back 0 is one row, so row_count alone would let it
        # through - and a "nothing matched" query is the last thing worth
        # making permanent.
        and not _looks_empty(result.get("retrieved_data") or [])
        and not result.get("error")
        and not result.get("sql_error")
        and not result.get("zero_row_retried")
        and not result.get("sql_from_cache")
    ):
        return

    from backend.tools.query_cache import is_self_contained, remember

    raw = result.get("user_query", "")
    rewritten = result.get("rewritten_query") or raw

    # Stored under what the USER typed - the rewrite is worded differently every
    # run, so keying on it produced a new entry each time instead of a hit. A
    # follow-up ("write their names") only means something next to the previous
    # turn, so it is not stored at all.
    if not is_self_contained(raw, rewritten):
        return

    try:
        remember(
            raw,
            result.get("entities"),
            result["sql"],
            tables_used=result.get("tables_used", []),
            limit_is_user_requested=result.get("limit_is_user_requested", False),
        )
    except Exception:
        pass


@router.get("/chat/{thread_id}/history")
def history(thread_id: str, http_request: Request) -> Dict[str, Any]:
    """Replay a conversation - but only for the user it belongs to.

    This used to hand any thread to anyone holding its id, which is how a
    thread id surviving logout in localStorage showed the next user the
    previous one's conversation.
    """
    user_id = current_user_id(http_request)
    owner = chat_log.thread_owner(thread_id)
    if owner is not None and owner != user_id:
        # Empty, not 403: the client asks for history on every page load, and a
        # stale id from a previous session is an ordinary event, not an error
        # worth showing the user.
        return {"thread_id": thread_id, "messages": []}

    snapshot = _graph.get_state({"configurable": {"thread_id": thread_id}})
    messages = snapshot.values.get("messages", []) if snapshot else []
    return {
        "thread_id": thread_id,
        "messages": [
            {"role": "user" if m.type == "human" else "assistant", "content": m.content}
            for m in messages
        ],
    }


@router.get("/health")
def health() -> Dict[str, Any]:
    """
    Liveness for the UI's connection indicator.

    `warm` reports whether the background start-up warm-up has finished. It is
    informational only - the API answers questions either way, just a few
    seconds slower while cold - so the UI must NOT gate "connected" on it.
    """
    from backend.app import main as app_main

    return {
        "status": "ok",
        "database": "up" if ping() else "down",
        "warm": getattr(app_main, "_WARM", False),
    }


# ---------------------------------------------------------------------------
# The user's own conversation: saved as they go, restored when they come back.
#
# Separate from /chat/{id}/history, which replays the graph checkpointer and so
# only ever has prose. These carry the rendered messages - tables, charts, the
# clarification chips - so a restored screen looks exactly like the one they
# left rather than a transcript of it.
# ---------------------------------------------------------------------------


class ConversationBody(BaseModel):
    thread_id: str
    messages: List[Dict[str, Any]] = Field(default_factory=list)


@router.put("/conversation")
def save_conversation(body: ConversationBody, http_request: Request) -> Dict[str, Any]:
    """Upsert the signed-in user's conversation."""
    user_id = current_user_id(http_request)
    if user_id is None:
        # Nothing to attach it to. Not an error - an anonymous session simply
        # has no conversation to restore later.
        return {"saved": False, "reason": "not signed in"}

    existing = conversation_store.owner(body.thread_id)
    if existing is not None and existing != user_id:
        raise HTTPException(status_code=403, detail="That conversation belongs to another user.")

    return {"saved": conversation_store.save(body.thread_id, user_id, body.messages)}


@router.get("/conversation")
def restore_conversation(http_request: Request) -> Dict[str, Any]:
    """
    The signed-in user's most recent conversation, or an empty one.

    Only status='active' is returned, so a conversation the user deleted stays
    deleted for them however many times they sign back in.
    """
    user_id = current_user_id(http_request)
    if user_id is None:
        return {"thread_id": None, "messages": []}

    found = conversation_store.latest(user_id)
    if not found:
        return {"thread_id": None, "messages": []}
    return {
        "thread_id": found["thread_id"],
        "messages": found["messages"],
        "updated_at": str(found.get("updated_at") or ""),
    }


@router.delete("/conversation/{thread_id}")
def delete_conversation(thread_id: str, http_request: Request) -> Dict[str, Any]:
    """
    Clear it from the user's screen, keep it in the database.

    A soft delete: status becomes 'deleted' and the row stays, so what was
    asked is still on record even though the user has cleared their view.
    """
    user_id = current_user_id(http_request)
    if user_id is None:
        return {"deleted": False, "reason": "not signed in"}
    return {"deleted": conversation_store.soft_delete(thread_id, user_id)}
