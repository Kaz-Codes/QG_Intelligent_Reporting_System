// The one and only bridge to the chatbot backend.
//
// The chatbot itself is a SEPARATE service (a different stack entirely —
// LangGraph + OpenAI text-to-SQL — living in its own folder, chatbot_backend/,
// on its own port), but the browser never talks to it directly: this app's
// own FastAPI backend (app/) reverse-proxies /chatbot/* through to it
// (see app/chatbot_proxy.py), so the frontend only ever needs ONE base URL —
// the same one lib/api/client.ts uses. Two independent processes stay two
// independent processes; the browser just can't tell.
//
// Contract (see app/chatbot_proxy.py, which mirrors chatbot_backend/backend/api/chatbot.py):
//   POST /chatbot/chat                       { message, thread_id? } -> ChatResponse
//   POST /chatbot/chat/stream                 same body, Server-Sent Events
//   GET  /chatbot/chat/{thread_id}/history                            -> ChatHistory
//   GET  /chatbot/health                                              -> HealthResponse

import type { ChatHistory, ChatResponse, HealthResponse, StreamEvent } from './types'

// Defaults to riding on the main API's own origin + /chatbot (the proxy).
// VITE_CHATBOT_API_BASE_URL still works as an override — e.g. to talk to
// chatbot_backend directly on :8010 while developing on it in isolation.
const CHATBOT_BASE_URL = (
  import.meta.env.VITE_CHATBOT_API_BASE_URL ??
  `${(import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')}/chatbot`
).replace(/\/$/, '')

export class ChatbotApiError extends Error {
  status: number
  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ChatbotApiError'
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${CHATBOT_BASE_URL}${path}`, {
      ...init,
      // The chatbot sits on the API's origin, not the dev server's, so the
      // session cookie is NOT sent by default. Without this the backend sees
      // every request as anonymous - no owner on a conversation, nothing to
      // restore, and no audit trail.
      credentials: 'include',
      headers: init.body ? { 'Content-Type': 'application/json', ...init.headers } : init.headers,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ChatbotApiError('Cannot reach the assistant. Is the chatbot backend running?')
  }

  if (!response.ok) {
    let detail = ''
    try {
      const data = await response.json()
      detail = data?.detail ?? ''
    } catch {
      /* body was not JSON */
    }
    throw new ChatbotApiError(detail || `Request failed (${response.status})`, response.status)
  }

  return response.json() as Promise<T>
}

/** Send a message and get the assistant's reply in one shot (no streaming). */
export function sendMessage(
  message: string,
  threadId: string | null,
  opts: { signal?: AbortSignal } = {},
): Promise<ChatResponse> {
  return request('/chat', {
    method: 'POST',
    body: JSON.stringify({ message, thread_id: threadId || undefined }),
    signal: opts.signal,
  })
}

/**
 * Send a message and receive the turn as it happens over SSE.
 *
 * EventSource cannot POST, so this reads the response body as a stream and
 * parses SSE frames itself — same approach as the original chatbot frontend.
 */
export async function streamMessage(
  message: string,
  threadId: string | null,
  onEvent: (event: StreamEvent) => void,
  opts: { signal?: AbortSignal } = {},
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${CHATBOT_BASE_URL}/chat/stream`, {
      method: 'POST',
      // Same reason as request(): cross-origin, so the session cookie only
      // travels when asked for. This is the endpoint the UI actually uses.
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, thread_id: threadId || undefined }),
      signal: opts.signal,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ChatbotApiError('Cannot reach the assistant. Is the chatbot backend running?')
  }

  if (!response.ok || !response.body) {
    throw new ChatbotApiError(`Request failed (${response.status})`, response.status)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const line = frame.split('\n').find((l) => l.startsWith('data: '))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(6)) as StreamEvent)
      } catch {
        /* ignore a malformed frame rather than killing the stream */
      }
    }
  }
}

/** Replay a conversation's messages from the backend's memory. */
export function fetchChatHistory(
  threadId: string,
  opts: { signal?: AbortSignal } = {},
): Promise<ChatHistory> {
  return request(`/chat/${encodeURIComponent(threadId)}/history`, { signal: opts.signal })
}

/** Chatbot backend + database health, for the connection indicator. */
export function fetchChatHealth(opts: { signal?: AbortSignal } = {}): Promise<HealthResponse> {
  return request('/health', { signal: opts.signal })
}


/** The user's saved conversation, restored when they sign back in. */
export async function saveConversation(
  threadId: string,
  messages: unknown[],
): Promise<{ saved: boolean }> {
  return request('/conversation', {
    method: 'PUT',
    body: JSON.stringify({ thread_id: threadId, messages }),
  })
}

export async function fetchConversation(
  opts: { signal?: AbortSignal } = {},
): Promise<{ thread_id: string | null; messages: unknown[] }> {
  return request('/conversation', { signal: opts.signal })
}

/** Clears it from the user's view. The row stays in the database. */
export async function deleteConversation(threadId: string): Promise<{ deleted: boolean }> {
  return request(`/conversation/${encodeURIComponent(threadId)}`, { method: 'DELETE' })
}
