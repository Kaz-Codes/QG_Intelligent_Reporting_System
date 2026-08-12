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

import { createContext, useContext, useEffect, useRef, type ReactNode } from 'react'
import { useAuth } from '@/features/auth/AuthContext'
import { useChatState } from './useChat'

type ChatValue = ReturnType<typeof useChatState>

const ChatContext = createContext<ChatValue | null>(null)

export function ChatProvider({ children }: { children: ReactNode }) {
  const chat = useChatState()
  const { user } = useAuth()
  const lastUserRef = useRef<string | null | undefined>(undefined)

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
    }
  }, [user?.username, chat])

  return <ChatContext.Provider value={chat}>{children}</ChatContext.Provider>
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
