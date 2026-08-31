import { useState } from 'react'
import { AlertCircle, MessageSquare, Plus, Trash2, X } from 'lucide-react'

import { useChat } from '@/lib/chatbot/ChatProvider'
import { dayGroupLabel, relativeTime } from '@/lib/api/notifications'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { cn } from '@/lib/utils'

/**
 * The list of past conversations.
 *
 * HISTORY IS A CONVENIENCE; THE CHATBOT WORKING IS NOT. Every failure path in
 * here ends with the chat still usable — a list that will not load shows a
 * retry and nothing else, and "New chat" is reachable in every state including
 * that one. Nothing in this component can stop somebody asking a question.
 */

/** "2h ago" / "Yesterday" / "12 Aug 2026".
 *
 *  Composed from the two helpers the notification panel already uses rather
 *  than written again — relativeTime for anything recent, and dayGroupLabel
 *  purely to catch the day boundary, because "1d ago" reads worse than
 *  "Yesterday" for something the user did last night. */
function conversationTime(iso: string): string {
  if (!iso) return ''
  if (dayGroupLabel(iso) === 'Yesterday') return 'Yesterday'
  return relativeTime(iso)
}

function SidebarBody({ onPick }: { onPick?: () => void }) {
  const {
    conversations,
    conversationsError,
    conversationsLoading,
    refreshConversations,
    openConversation,
    startNewChat,
    removeConversation,
    threadId,
  } = useChat()

  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const pending = conversations.find((c) => c.thread_id === pendingDelete)

  return (
    <>
      <div className="flex h-full flex-col">
        <button
          type="button"
          onClick={() => {
            startNewChat()
            onPick?.()
          }}
          className="mb-3 flex shrink-0 items-center justify-center gap-1.5 rounded-xl border border-line bg-surface px-3 py-2 text-sm font-semibold text-ink transition-colors hover:border-brand-light hover:bg-canvas-alt"
        >
          <Plus size={15} />
          New chat
        </button>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {/* The error state REPLACES the list but not the button above it, so
              a user whose history is unreachable can still start a new chat. */}
          {conversationsError && (
            <div className="rounded-lg border border-line bg-canvas-alt px-3 py-3 text-center">
              <AlertCircle size={16} className="mx-auto mb-1 text-watch" />
              <p className="text-xs font-semibold text-ink">Could not load history</p>
              <p className="mt-0.5 text-[11px] text-muted">
                Your past chats are safe — this is just the list.
              </p>
              <button
                type="button"
                onClick={() => void refreshConversations()}
                className="mt-1.5 text-[11px] font-semibold text-brand hover:underline"
              >
                Try again
              </button>
            </div>
          )}

          {!conversationsError && conversationsLoading && conversations.length === 0 && (
            <div className="space-y-2" aria-hidden>
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-11 animate-pulse rounded-lg bg-line/60" />
              ))}
            </div>
          )}

          {!conversationsError && !conversationsLoading && conversations.length === 0 && (
            <div className="px-2 py-8 text-center">
              <MessageSquare size={22} className="mx-auto mb-2 text-muted" />
              <p className="text-xs font-semibold text-ink">No conversations yet</p>
              <p className="mt-1 text-[11px] leading-relaxed text-muted">
                Ask something and it will be saved here so you can pick it back up.
              </p>
            </div>
          )}

          <div className="flex flex-col gap-0.5">
            {conversations.map((c) => {
              const active = c.thread_id === threadId
              return (
                <div
                  key={c.thread_id}
                  className={cn(
                    'group relative flex items-center gap-1 rounded-lg pr-1 transition-colors',
                    active ? 'bg-brand-soft' : 'hover:bg-canvas-alt',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => {
                      void openConversation(c.thread_id)
                      onPick?.()
                    }}
                    className="min-w-0 flex-1 px-2.5 py-2 text-left"
                  >
                    <span
                      className={cn(
                        'block truncate text-[13px] leading-tight text-ink',
                        active && 'font-semibold',
                      )}
                    >
                      {c.title}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-muted">
                      {conversationTime(c.updated_at)}
                      {c.message_count ? ` · ${c.message_count} messages` : ''}
                    </span>
                  </button>

                  {/* Always in the DOM, revealed on hover or focus — mounting
                      it on hover would put it out of reach of a keyboard and
                      it would never appear at all on a touch screen. */}
                  <button
                    type="button"
                    onClick={() => setPendingDelete(c.thread_id)}
                    title="Delete this conversation"
                    aria-label={`Delete ${c.title}`}
                    className="shrink-0 rounded p-1.5 text-muted opacity-0 transition-opacity hover:text-risk focus:opacity-100 group-hover:opacity-100"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Confirmed, because deleting is not reversible from anywhere in this
          UI — the row survives in the database, but nothing here can bring it
          back onto the user's screen. */}
      <ConfirmDialog
        open={pendingDelete != null}
        title="Delete this conversation?"
        description={
          pending ? (
            <>
              <span className="font-medium text-ink">{pending.title}</span> will be
              removed from your history. Your other conversations are not affected.
            </>
          ) : (
            <>This conversation will be removed from your history.</>
          )
        }
        confirmLabel="Delete"
        danger
        confirmingLabel="Deleting…"
        confirming={deleting}
        onConfirm={() => {
          if (!pendingDelete) return
          setDeleting(true)
          void removeConversation(pendingDelete).finally(() => {
            setDeleting(false)
            setPendingDelete(null)
          })
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  )
}

/** Fixed rail on a wide screen. */
export function ConversationSidebar() {
  return (
    <aside className="hidden w-60 shrink-0 border-r border-line pr-3 lg:block">
      <SidebarBody />
    </aside>
  )
}

/** The same list as a drawer, for narrow viewports — a 240px rail beside the
 *  chat on a phone leaves neither usable, so below `lg` it hides behind the
 *  toggle in the Assistant header. */
export function ConversationDrawer({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div
        className="animate-fade-in absolute inset-0 bg-navy-deep/30"
        onClick={onClose}
        aria-hidden
      />
      <div className="animate-scale-in absolute left-0 top-0 flex h-full w-72 max-w-[85vw] flex-col border-r border-line bg-surface p-3 shadow-lg">
        <div className="mb-2 flex shrink-0 items-center justify-between">
          <p className="font-display text-sm font-bold text-ink">Your chats</p>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-canvas-alt hover:text-ink"
            aria-label="Close"
          >
            <X size={15} />
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <SidebarBody onPick={onClose} />
        </div>
      </div>
    </div>
  )
}
