"""
Reverse proxy onto the chatbot backend (chatbot_backend/, a separate FastAPI
service - different dependency stack, own port, no shared auth).

The frontend should only ever need ONE base URL (this server's). Every
/chatbot/* request here is forwarded to CHATBOT_BACKEND_URL and the response
(including a streamed one) is passed straight back, so the two services stay
independent processes while looking like one to the browser.

Not merged into the main app on purpose: chatbot_backend pulls in LangGraph,
the OpenAI SDK, ChromaDB and statsmodels - a much heavier and faster-moving
stack than this app's plain SQLAlchemy backend. Keeping it a separate process
means a stuck LLM call or a chatbot crash can't take the ERP app down with it.
"""

import json
import logging
import os

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.accounts.permissions import CAN_USE_ASSISTANT
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

CHATBOT_BACKEND_URL = os.getenv("CHATBOT_BACKEND_URL", "http://127.0.0.1:8010").rstrip("/")

# One client, reused for every request - opening a new connection pool per
# call is the usual way this kind of proxy ends up slow.
_client = httpx.AsyncClient(base_url=CHATBOT_BACKEND_URL, timeout=120.0)

# Hop-by-hop headers a proxy must strip before relaying either direction -
# they describe THIS connection, not the one being forwarded.
_HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
    "content-encoding", "host",
}


def _forward_headers(headers) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP}


#-------------------------------------------
# THE GATE
#
# EVERY /chatbot ROUTE BUT /health AUTHENTICATES HERE. This proxy used to
# forward the cookie and let the chatbot decide - and the chatbot answered
# anonymous callers, so anyone who could reach this port could ask the
# assistant questions and get answers built from live consignments, suppliers,
# values and stock, with no login at all.
#
# Do not be reassured by grepping this file for "authenticate": the string
# also appears in _HOP_BY_HOP above as "proxy-authenticate", which is an HTTP
# header name and not an auth call. That false positive is how the gap read as
# closed once already.
#
# Same two calls, in the same order, as every other route in this app (see
# app/imports/routes/get_consignment.py): authenticate() resolves the session
# cookie or raises 401, authorize() checks the permission or raises 403. The
# chatbot is gated on CAN_USE_ASSISTANT, which is the permission the account
# screen already offers and the nav already hides the page behind.
#
# DEFENCE IN DEPTH, NOT A SINGLE GATE. The chatbot refuses anonymous callers
# on its own side too, so reaching :8010 directly does not get past it either.
# Neither layer is load-bearing alone.
#-------------------------------------------

def _require_assistant_access(request: Request):
    """401 if not signed in, 403 without CAN_USE_ASSISTANT. Returns the user."""
    db = SessionLocal()
    try:
        return authorize(authenticate(request), CAN_USE_ASSISTANT, db)
    finally:
        db.close()


def _sse(payload: str) -> bytes:
    """One server-sent-event frame: `data: <json>` then the blank line.

    The terminating blank line is what tells the client the event is complete;
    without it the frame sits in the parser's buffer and is never delivered.
    """
    return f"data: {payload}\n\n".encode()


def _unavailable() -> Response:
    """The chatbot is not answering - say so plainly.

    503 with a readable message rather than the 500 and stack trace a bare
    httpx.RequestError produced. The chatbot is a separate process by design
    (see the module docstring); it being down is an expected state of the
    system, not an error in this one.
    """
    return Response(
        content=json.dumps({"detail": "The assistant is currently unavailable."}),
        status_code=503,
        media_type="application/json",
    )


@router.post("/chat")
async def chat(request: Request):
    _require_assistant_access(request)
    body = await request.body()
    try:
        upstream = await _client.post(
            "/api/chat", content=body, headers=_forward_headers(request.headers)
        )
    except httpx.RequestError:
        return _unavailable()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.post("/chat/stream")
async def chat_stream(request: Request):
    _require_assistant_access(request)
    body = await request.body()

    async def relay():
        # THE FAILURE IS REPORTED IN-BAND, not as a status code. By the time
        # this generator runs the response has already begun with 200 and
        # text/event-stream headers, so there is no status left to change. The
        # client's parser already understands {"type":"error"} (see
        # lib/chatbot/types.ts StreamEvent), so a chatbot that is down arrives
        # as a rendered error message rather than a stream that simply stops
        # mid-answer with nothing said.
        try:
            async with _client.stream(
                "POST", "/api/chat/stream", content=body, headers=_forward_headers(request.headers)
            ) as upstream:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
        except httpx.RequestError:
            logger.warning("Chatbot unreachable during /chat/stream")
            frame = json.dumps({
                "type": "error",
                "message": "The assistant is currently unavailable.",
            })
            yield _sse(frame)

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx-style proxies (and this one) buffering the stream.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/{thread_id}/history")
async def chat_history(thread_id: str, request: Request):
    _require_assistant_access(request)
    # The cookie STILL has to travel even though this proxy has already checked
    # it: the chatbot decides whether this caller owns the thread, which is a
    # different question from whether they may use the assistant at all.
    try:
        upstream = await _client.get(
            f"/api/chat/{thread_id}/history", headers=_forward_headers(request.headers)
        )
    except httpx.RequestError:
        return _unavailable()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


# The user's saved conversation. Forwarded like everything else so the session
# cookie reaches the chatbot, which is what scopes a conversation to its owner.
@router.put("/conversation")
async def save_conversation(request: Request):
    _require_assistant_access(request)
    body = await request.body()
    try:
        upstream = await _client.put(
            "/api/conversation", content=body, headers=_forward_headers(request.headers)
        )
    except httpx.RequestError:
        return _unavailable()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


# GET /conversation - the restore-latest passthrough - USED TO BE HERE, and
# went with the upstream route it forwarded to (see the note in
# chatbot_backend/backend/api/chatbot.py). Restoring the most recent thread on
# load is what made every sign-in resume mid-conversation; the sidebar replaced
# it with GET /conversations and GET /conversations/{thread_id}, both proxied
# below.


@router.get("/conversations")
async def list_conversations(request: Request):
    _require_assistant_access(request)
    try:
        upstream = await _client.get(
            "/api/conversations", headers=_forward_headers(request.headers)
        )
    except httpx.RequestError:
        return _unavailable()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str, request: Request):
    _require_assistant_access(request)
    try:
        upstream = await _client.get(
            f"/api/conversations/{thread_id}", headers=_forward_headers(request.headers)
        )
    except httpx.RequestError:
        return _unavailable()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.delete("/conversation/{thread_id}")
async def delete_conversation(thread_id: str, request: Request):
    _require_assistant_access(request)
    try:
        upstream = await _client.delete(
            f"/api/conversation/{thread_id}", headers=_forward_headers(request.headers)
        )
    except httpx.RequestError:
        return _unavailable()
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


# DELIBERATELY UNAUTHENTICATED - the one exception in this file.
#
# The connection indicator polls this before anyone has signed in, and its
# whole job is to answer "is the assistant reachable". Gating it would make a
# signed-out browser show the assistant as down rather than as unavailable to
# them, and would make the indicator useless on the login screen.
#
# It is safe to leave open because it returns NO BUSINESS DATA: a status
# string, whether the database answered, and whether warm-up has finished.
# Nothing about a consignment, a supplier or a user. Do not "fix" this.
@router.get("/health")
async def chatbot_health():
    try:
        upstream = await _client.get("/api/health", timeout=5.0)
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=_forward_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )
    except httpx.RequestError:
        # The chatbot backend isn't up - report that plainly rather than
        # letting the request hang or 500 with a stack trace.
        return Response(
            content=b'{"status":"down","database":"unknown","warm":false}',
            status_code=200,
            media_type="application/json",
        )
