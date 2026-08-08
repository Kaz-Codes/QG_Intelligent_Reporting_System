// Polls the chatbot backend's health endpoint for the "Online" dot on the
// Assistant page. Purely cosmetic — if this fails, the chat still works and
// surfaces its own errors.

import { useEffect, useState } from 'react'
import { fetchChatHealth } from './api'

// Two cadences, because the two situations want opposite things: while up, a
// slow poll is plenty; while down, the backend is most likely still starting
// (~15s to build the LangGraph graph before it binds the port), so retry
// quickly at first and ease off rather than reading as broken for 20s.
const POLL_OK_MS = 20000
const RETRY_MIN_MS = 1000
const RETRY_MAX_MS = 10000

export function useChatHealth() {
  const [status, setStatus] = useState<'unknown' | 'online' | 'offline'>('unknown')
  const [database, setDatabase] = useState('unknown')

  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout>
    let retryMs = RETRY_MIN_MS

    const probe = async () => {
      let nextMs: number
      try {
        const data = await fetchChatHealth()
        if (!active) return
        setStatus('online')
        setDatabase(data.database || 'unknown')
        retryMs = RETRY_MIN_MS
        nextMs = POLL_OK_MS
      } catch {
        if (!active) return
        setStatus('offline')
        setDatabase('unknown')
        nextMs = retryMs
        retryMs = Math.min(retryMs * 2, RETRY_MAX_MS)
      }
      timer = setTimeout(probe, nextMs)
    }

    probe()
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [])

  return { status, database }
}
