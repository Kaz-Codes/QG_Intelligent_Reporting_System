// Holds the conversation ABOVE the router, so it outlives the Assistant page.
//
// The problem this fixes: useChat used to be called inside <Assistant />.
// Navigating to any other tab unmounts that page, which tears the hook's state
// down with it - so a question still being answered lost the component that was
// waiting for it. The stream had nowhere to deliver to, the answer never
// appeared, and coming back showed an empty conversation. In practice: ask
// something slow, glance at Dashboard, lose the answer.
//
// Mounted once inside <BrowserRouter> and outside <Routes>, this provider is
// never unmounted by navigation, so the fetch keeps streaming and the messages
// keep updating while the user is on another page. Come back and the finished
// answer is simply there.
//
// It is deliberately NOT a global singleton or a store library - the state is
// the same hook it always was, just mounted somewhere that does not get
// destroyed.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { deleteConversation, fetchConversation, saveConversation } from './api'
import type { AssistantMessage } from './types'
import { useChatState } from './useChat'

type ChatValue = ReturnType<typeof useChatState> & {
  /** Clear from view; the conversation is soft-deleted, never dropped. */
  clearConversation: () => void
}

const ChatContext = createContext<ChatValue | null>(null)

export function ChatProvider({ children }: { children: ReactNode }) {
  const chat = useChatState()
  const { user } = useAuth()
  const lastUserRef = useRef<string | null | undefined>(undefined)
  const restoredForRef = useRef<string | null>(null)

  // THE CONVERSATION BELONGS TO THE PERSON WHO IS SIGNED IN.
  //
  // Sitting above the router is what lets an in-flight answer survive
  // navigation - but it also means logging out does NOT unmount this, so
  // without the reset below the messages simply stayed on screen and the next
  // person to sign in on that machine was shown the previous user's
  // conversation. The thread id in localStorage made it worse: even after a
  // refresh the client would fetch that thread's history back.
  //
  // Watching the identity rather than hooking logout() covers every way the
  // user can change - signing out, signing in as somebody else, and a session
  // expiring underneath us.
  useEffect(() => {
    const id = user?.username ?? null
    if (lastUserRef.current === undefined) {
      // First render. Adopt the current identity without wiping a conversation
      // that legitimately belongs to it (a page refresh mid-thread).
      lastUserRef.current = id
      return
    }
    if (lastUserRef.current !== id) {
      lastUserRef.current = id
      // Aborts anything in flight, drops the messages and clears the stored
      // thread id, so nothing of the previous session survives.
      chat.resetConversation()
      restoredForRef.current = null
    }
  }, [user?.username, chat])

  // RESTORE the signed-in user's own conversation.
  //
  // Runs once per signed-in user: on sign-in, and on a page reload while
  // signed in. Only their own ACTIVE conversation comes back - one they
  // deleted stays gone for them however often they return, because the server
  // only serves status='active'.
  useEffect(() => {
    const id = user?.username ?? null
    if (!id || restoredForRef.current === id) return
    restoredForRef.current = id

    const controller = new AbortController()
    fetchConversation({ signal: controller.signal })
      .then((saved) => {
        const messages = (saved?.messages ?? []) as AssistantMessage[]
        if (saved?.thread_id && messages.length) {
          chat.restoreConversation(saved.thread_id, messages)
        }
      })
      .catch(() => {
        // A conversation that cannot be restored is not worth an error on
        // screen - the user simply starts a fresh one.
      })
    return () => controller.abort()
  }, [user?.username, chat])

  // SAVE after every completed turn, so closing the tab loses nothing.
  //
  // Keyed on the message count and the streaming flag rather than the array
  // itself: the last message is patched token by token while an answer
  // streams, and saving on every token would be one write per word.
  const lastSavedRef = useRef('')
  useEffect(() => {
    if (!user || !chat.threadId || !chat.messages.length) return
    if (chat.isSending) return  // still streaming - wait for the final text

    const signature = `${chat.threadId}:${chat.messages.length}:${
      chat.messages[chat.messages.length - 1]?.content?.length ?? 0
    }`
    if (lastSavedRef.current === signature) return
    lastSavedRef.current = signature

    saveConversation(chat.threadId, chat.messages).catch(() => {
      // Best effort. A failed save must never surface as a failed answer.
    })
  }, [user, chat.threadId, chat.messages, chat.isSending])

  // What the "clear" control calls. The server marks the conversation deleted
  // and KEEPS the row - the user stops seeing it, the record of what was asked
  // survives, and it never comes back on a later sign-in.
  const clearConversation = useCallback(() => {
    const id = chat.threadId
    chat.resetConversation()
    restoredForRef.current = user?.username ?? null
    lastSavedRef.current = ''
    if (id) deleteConversation(id).catch(() => {})
  }, [chat, user?.username])

  const value = useMemo(() => ({ ...chat, clearConversation }), [chat, clearConversation])

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat(): ChatValue {
  const ctx = useContext(ChatContext)
  if (!ctx) {
    // Loud on purpose: rendering the Assistant outside the provider would
    // silently reintroduce the bug this file exists to fix.
    throw new Error('useChat must be used inside <ChatProvider>')
  }
  return ctx
}
