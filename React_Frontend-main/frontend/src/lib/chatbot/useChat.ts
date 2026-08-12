// Conversation state, decoupled from the UI — port of the original chatbot
// frontend's useChat.js. Owns the message list, the thread id (persisted so
// a refresh keeps the same conversation), the in-flight state, and errors.
// The Assistant page reads this and renders; it never calls the API client
// directly.

import { useCallback, useRef, useState } from 'react'
import { streamMessage } from './api'
import type { AssistantMessage } from './types'

const THREAD_STORAGE_KEY = 'qgirs-chatbot-thread-id'

let messageSeq = 0
const nextId = () => `m${Date.now()}-${messageSeq++}`

// Renamed from useChat: this is the IMPLEMENTATION, called exactly once by
// ChatProvider. Components consume it through useChat() from ChatProvider,
// which is mounted above the router so navigation cannot unmount it.
export function useChatState() {
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [threadId, setThreadId] = useState<string | null>(
    () => window.localStorage.getItem(THREAD_STORAGE_KEY) || null,
  )
  const [isSending, setIsSending] = useState(false)
  // Live progress label from the stream ("Writing the query…").
  const [status, setStatus] = useState('')
  const [error, setError] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)

  // RESTORING ON LOAD IS ChatProvider's JOB, NOT THIS HOOK'S.
  //
  // This used to replay fetchChatHistory(threadId) for a thread id kept in
  // localStorage. Two things were wrong with it once conversations were stored
  // per user in the database:
  //
  //   * IT RACED THE REAL RESTORE. ChatProvider fetches the saved conversation
  //     and calls restoreConversation(); this effect fetched the same thread's
  //     history in parallel and called setMessages() on whatever came back.
  //     Whichever request finished LAST won, so the outcome varied run to run.
  //
  //   * IT WON WITH LESS. The history endpoint returns {role, content} only -
  //     no rows, no columns, no charts. When it won the race it replaced a
  //     fully restored conversation with a text-only copy of itself, silently
  //     dropping every table the user was looking at.
  //
  // The database copy is authoritative: it survives a backend restart, which
  // the in-memory graph history does not, and it carries what the page renders.
  // So there is exactly one restore path now, and it is the one that holds the
  // whole message.

  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || isSending) return

      setError(null)
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const userMessage: AssistantMessage = { id: nextId(), role: 'user', content: trimmed }
      setMessages((prev) => [...prev, userMessage])
      setIsSending(true)

      // The assistant's message exists from the start and is filled in as
      // the stream arrives, so text appears as it is written.
      const replyId = nextId()
      setMessages((prev) => [
        ...prev,
        { id: replyId, role: 'assistant', content: '', streaming: true },
      ])

      const patchReply = (patch: Partial<AssistantMessage>) =>
        setMessages((prev) => prev.map((m) => (m.id === replyId ? { ...m, ...patch } : m)))

      let streamedText = ''
      try {
        await streamMessage(
          trimmed,
          threadId,
          (ev) => {
            if (ev.type === 'start') {
              if (ev.thread_id && ev.thread_id !== threadId) {
                setThreadId(ev.thread_id)
                window.localStorage.setItem(THREAD_STORAGE_KEY, ev.thread_id)
              }
            } else if (ev.type === 'status') {
              setStatus(ev.label || '')
            } else if (ev.type === 'token') {
              streamedText += ev.text || ''
              patchReply({ content: streamedText })
            } else if (ev.type === 'error') {
              throw new Error(ev.message || 'Something went wrong.')
            } else if (ev.type === 'done') {
              setStatus('')
              patchReply({
                streaming: false,
                // Clarify/teach replies short-circuit the model, so nothing
                // was streamed — fall back to the finished answer.
                content: ev.streamed && streamedText ? streamedText : ev.answer || '(no answer)',
                clarificationOptions: ev.clarification_options || [],
                columns: ev.columns || [],
                rows: ev.rows || [],
                charts: ev.charts || [],
                meta: {
                  route: ev.route,
                  domain: ev.domain,
                  intent: ev.intent,
                  rowCount: ev.row_count,
                  sql: ev.sql,
                  tablesUsed: ev.tables_used,
                  knowledgeInferred: ev.knowledge_inferred,
                  analysisType: ev.analysis_type,
                  forecast: ev.forecast,
                  computationCode: ev.computation_code,
                  computationExplanation: ev.computation_explanation,
                  computationResult: ev.computation_result,
                  error: ev.error,
                },
              })
            }
          },
          { signal: controller.signal },
        )
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message = err instanceof Error ? err.message : 'Something went wrong.'
        setError(message)
        patchReply({ streaming: false, failed: !streamedText })
      } finally {
        setStatus('')
        setIsSending(false)
      }
    },
    [threadId, isSending],
  )

  const restoreConversation = useCallback(
    (restoredThreadId: string, restored: AssistantMessage[]) => {
      setThreadId(restoredThreadId)
      window.localStorage.setItem(THREAD_STORAGE_KEY, restoredThreadId)
      setMessages(restored)
      setError(null)
      setStatus('')
    },
    [],
  )

  const resetConversation = useCallback(() => {
    abortRef.current?.abort()
    window.localStorage.removeItem(THREAD_STORAGE_KEY)
    setThreadId(null)
    setMessages([])
    setError(null)
    setStatus('')
    setIsSending(false)
  }, [])

  return {
    messages,
    isSending,
    status,
    error,
    threadId,
    send,
    resetConversation,
    // Used by ChatProvider to put a stored conversation back on screen when the
    // user signs in again. Not for general use - the message list is otherwise
    // owned entirely by this hook.
    restoreConversation,
  }
}
