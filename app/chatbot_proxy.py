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

import os

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

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


@router.post("/chat")
async def chat(request: Request):
    body = await request.body()
    upstream = await _client.post(
        "/api/chat", content=body, headers=_forward_headers(request.headers)
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.post("/chat/stream")
async def chat_stream(request: Request):
    body = await request.body()

    async def relay():
        async with _client.stream(
            "POST", "/api/chat/stream", content=body, headers=_forward_headers(request.headers)
        ) as upstream:
            async for chunk in upstream.aiter_bytes():
                yield chunk

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
    # The cookie has to travel: the chatbot decides whether this caller owns
    # the thread, and without it every request looks anonymous.
    upstream = await _client.get(
        f"/api/chat/{thread_id}/history", headers=_forward_headers(request.headers)
    )
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
    body = await request.body()
    upstream = await _client.put(
        "/api/conversation", content=body, headers=_forward_headers(request.headers)
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.get("/conversation")
async def restore_conversation(request: Request):
    upstream = await _client.get(
        "/api/conversation", headers=_forward_headers(request.headers)
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


@router.delete("/conversation/{thread_id}")
async def delete_conversation(thread_id: str, request: Request):
    upstream = await _client.delete(
        f"/api/conversation/{thread_id}", headers=_forward_headers(request.headers)
    )
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=_forward_headers(upstream.headers),
        media_type=upstream.headers.get("content-type"),
    )


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
