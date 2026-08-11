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

import { createContext, useContext, type ReactNode } from 'react'
import { useChatState } from './useChat'

type ChatValue = ReturnType<typeof useChatState>

const ChatContext = createContext<ChatValue | null>(null)

export function ChatProvider({ children }: { children: ReactNode }) {
  const chat = useChatState()
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
