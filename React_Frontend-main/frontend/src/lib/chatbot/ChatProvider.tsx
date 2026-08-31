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
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import {
  deleteConversation,
  fetchConversationById,
  fetchConversations,
  saveConversation,
} from './api'
import type { ConversationSummary } from './types'
import { useChatState } from './useChat'

type ChatValue = ReturnType<typeof useChatState> & {
  /** Clear the OPEN conversation from view; it is soft-deleted, never dropped. */
  clearConversation: () => void
  /** The sidebar list. Empty while loading, and empty on failure - see
   *  `conversationsError`, which is what tells the two apart. */
  conversations: ConversationSummary[]
  conversationsError: boolean
  conversationsLoading: boolean
  refreshConversations: () => Promise<void>
  /** Load a past conversation onto the screen. False if it could not be
   *  loaded, in which case the current screen is left untouched. */
  openConversation: (threadId: string) => Promise<boolean>
  /** Back to the empty state. Creates nothing. */
  startNewChat: () => void
  removeConversation: (threadId: string) => Promise<void>
  /** Desktop rail collapsed? Held HERE, not in the Assistant page, because
   *  that page unmounts on navigation and the preference must outlive it —
   *  the same reason the messages and the list live here. Not localStorage:
   *  it is a per-session preference, and this environment has no persistence
   *  requirement for it. */
  sidebarCollapsed: boolean
  toggleSidebar: () => void
}

const ChatContext = createContext<ChatValue | null>(null)

export function ChatProvider({ children }: { children: ReactNode }) {
  const chat = useChatState()
  const { user } = useAuth()
  const lastUserRef = useRef<string | null | undefined>(undefined)

  // useChatState returns a FRESH OBJECT every render, so naming `chat` as an
  // effect dependency re-runs that effect on every render - and for the restore
  // below, whose cleanup aborts its own request, that was fatal: the fetch was
  // cancelled by the next render and the "already restored" guard then stopped
  // it ever being retried, so a stored conversation never came back. Reading
  // the hook through a ref lets the effects depend on the USER alone, which is
  // the only thing that should actually re-trigger them.
  const chatRef = useRef(chat)
  chatRef.current = chat

  // Declared up here because the conversation actions below close over it -
  // switching conversation has to forget what was last saved, or the save
  // effect sees an unchanged signature and skips the first turn of the thread
  // just opened.
  const lastSavedRef = useRef('')

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
      chatRef.current.resetConversation()
    }
  }, [user?.username])

  // OPENING THE ASSISTANT STARTS AN EMPTY CHAT. IT NO LONGER RESTORES ONE.
  //
  // This used to fetch GET /conversation - "the user's most recent active
  // thread" - and put it straight on screen. That was the only way to reach a
  // conversation at all, so the server had to choose one; with a sidebar the
  // user chooses, and being handed last week's thread on every sign-in is
  // simply the wrong default.
  //
  // The reset is what makes "empty" true rather than merely looking true.
  // useChatState seeds threadId from localStorage, so without this a reload
  // would show an empty screen that was still POINTING AT the old thread, and
  // the next question would silently append to a conversation the user could
  // not see. Empty screen, live thread id, is worse than either state alone.
  //
  // Runs on MOUNT, not on navigation: this provider sits above the router and
  // is not unmounted by moving between pages, so a conversation survives a trip
  // to Dashboard and back exactly as it did before. Only a real page load - or
  // signing in - lands on a new chat.
  const startedFreshRef = useRef(false)
  useEffect(() => {
    if (startedFreshRef.current) return
    startedFreshRef.current = true
    chatRef.current.resetConversation()
  }, [])

  // THE SIDEBAR LIST.
  //
  // Held here rather than in the Assistant page because the page unmounts on
  // navigation and this does not - the same reason the messages live here. It
  // also means the list is already warm when the user comes back to the tab.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const toggleSidebar = useCallback(() => setSidebarCollapsed((v) => !v), [])

  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [conversationsError, setConversationsError] = useState(false)
  const [conversationsLoading, setConversationsLoading] = useState(false)

  const refreshConversations = useCallback(async () => {
    if (!user) {
      setConversations([])
      return
    }
    setConversationsLoading(true)
    try {
      const res = await fetchConversations()
      setConversations(res.conversations ?? [])
      setConversationsError(false)
    } catch {
      // HISTORY IS A CONVENIENCE; THE CHATBOT WORKING IS NOT. A failed list
      // sets a flag the sidebar renders as a retry, and touches nothing else -
      // the user can still ask questions and still start new conversations.
      setConversationsError(true)
    } finally {
      setConversationsLoading(false)
    }
  }, [user?.username])

  // Load on sign-in, and clear on sign-out so one user's titles are never
  // shown to the next person at this machine.
  useEffect(() => {
    if (!user) {
      setConversations([])
      setConversationsError(false)
      return
    }
    void refreshConversations()
  }, [user?.username, refreshConversations])

  // Open a past conversation. Failure leaves the current screen alone rather
  // than half-clearing it - a conversation that will not load should not cost
  // the user the one they are in.
  const openConversation = useCallback(async (threadId: string) => {
    try {
      const found = await fetchConversationById(threadId)
      chatRef.current.restoreConversation(found.thread_id, found.messages ?? [])
      lastSavedRef.current = ''
      return true
    } catch {
      return false
    }
  }, [])

  // "New chat" - a UI state, not a row. Nothing is created until a message is
  // sent, which is why this only clears what is on screen.
  const startNewChat = useCallback(() => {
    chatRef.current.resetConversation()
    lastSavedRef.current = ''
  }, [])

  // Delete ONE conversation. Since C1 the server retires only the named thread
  // rather than sweeping every active one, so the rest of the list survives.
  const removeConversation = useCallback(
    async (threadId: string) => {
      setConversations((current) => current.filter((c) => c.thread_id !== threadId))
      if (chatRef.current.threadId === threadId) {
        chatRef.current.resetConversation()
        lastSavedRef.current = ''
      }
      try {
        await deleteConversation(threadId)
      } catch {
        // Put it back: the row is still there, so showing it gone would be a
        // lie the next refresh contradicts.
        void refreshConversations()
      }
    },
    [refreshConversations],
  )

  // SAVE after every completed turn, so closing the tab loses nothing.
  //
  // Keyed on the message count and the streaming flag rather than the array
  // itself: the last message is patched token by token while an answer
  // streams, and saving on every token would be one write per word.
  useEffect(() => {
    if (!user || !chat.threadId || !chat.messages.length) return
    if (chat.isSending) return  // still streaming - wait for the final text

    const signature = `${chat.threadId}:${chat.messages.length}:${
      chat.messages[chat.messages.length - 1]?.content?.length ?? 0
    }`
    if (lastSavedRef.current === signature) return
    lastSavedRef.current = signature

    const isFirstTurnOfThread = !conversations.some((c) => c.thread_id === chat.threadId)

    saveConversation(chat.threadId, chat.messages)
      .catch(() => {
        // Best effort. A failed save must never surface as a failed answer.
      })
      .finally(() => {
        // The list only changes when a thread is NEW - a further turn moves its
        // updated_at, but it is already at the top of a list ordered by exactly
        // that. Refreshing on every turn would re-fetch the whole sidebar to
        // learn nothing, and this runs after every answer.
        //
        // In .finally rather than .then because the SERVER has already
        // persisted the turn as it answered (append_turn); this PUT only
        // refines the row. So the conversation exists and belongs in the
        // sidebar whether or not the save call itself succeeded.
        if (isFirstTurnOfThread) void refreshConversations()
      })
  }, [user, chat.threadId, chat.messages, chat.isSending, conversations, refreshConversations])

  // What the "clear" control calls. The server marks the conversation deleted
  // and KEEPS the row - the user stops seeing it, the record of what was asked
  // survives, and it never comes back on a later sign-in.
  const clearConversation = useCallback(() => {
    const id = chatRef.current.threadId
    chatRef.current.resetConversation()
    lastSavedRef.current = ''
    if (id) deleteConversation(id).catch(() => {})
  }, [user?.username])

  const value = useMemo(
    () => ({
      ...chat,
      clearConversation,
      conversations,
      conversationsError,
      conversationsLoading,
      refreshConversations,
      openConversation,
      startNewChat,
      removeConversation,
      sidebarCollapsed,
      toggleSidebar,
    }),
    [
      chat, clearConversation, conversations, conversationsError,
      conversationsLoading, refreshConversations, openConversation,
      startNewChat, removeConversation, sidebarCollapsed, toggleSidebar,
    ],
  )

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
