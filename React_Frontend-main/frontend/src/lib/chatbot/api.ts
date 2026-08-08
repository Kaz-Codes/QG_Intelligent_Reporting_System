// The one and only bridge to the chatbot backend.
//
// This is a SEPARATE service from this app's own FastAPI backend (app/, see
// lib/api/client.ts) — a different stack entirely (LangGraph + OpenAI text-
// to-SQL) that lives in its own folder (chatbot_backend/) and runs on its
// own port. No cookies, no shared auth — a plain unauthenticated JSON/SSE
// API. If that ever changes, this is the only file that needs to.
//
// Contract (see chatbot_backend/backend/api/chatbot.py):
//   POST /api/chat                       { message, thread_id? } -> ChatResponse
//   POST /api/chat/stream                 same body, Server-Sent Events
//   GET  /api/chat/{thread_id}/history                            -> ChatHistory
//   GET  /api/health                                              -> HealthResponse

import type { ChatHistory, ChatResponse, HealthResponse, StreamEvent } from './types'

const CHATBOT_BASE_URL = (
  import.meta.env.VITE_CHATBOT_API_BASE_URL ?? 'http://127.0.0.1:8010/api'
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
