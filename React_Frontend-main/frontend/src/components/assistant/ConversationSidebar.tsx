import { useState } from 'react'
import {
  AlertCircle, ChevronLeft, ChevronRight, MessageSquare, Plus, Trash2, X,
} from 'lucide-react'

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

/**
 * The list itself, shared by the desktop rail and the mobile drawer.
 *
 * TWO REGIONS, AND THE SPLIT IS THE POINT: a `shrink-0` header that never
 * scrolls, and a `min-h-0 flex-1 overflow-y-auto` list that scrolls inside it.
 * Without `min-h-0` the list refuses to shrink below its content — a flex
 * child defaults to min-height:auto — so the whole column grows instead and
 * the scrollbar never appears where it is wanted.
 */
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
      <div className="flex h-full min-h-0 flex-col">
        {/* PINNED. Outside the scrolling region below, so "New chat" is
            reachable however far down the list the user has scrolled. */}
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
                    // THE FULL STORED TITLE, which the rail is too narrow to
                    // show: it is truncated twice over, once to 60 characters
                    // by derive_title and again by this column's width. A
                    // native title attribute rather than a component, because
                    // components/ui/ has no tooltip and one row in a list does
                    // not justify inventing one.
                    title={c.title}
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

/**
 * The desktop rail.
 *
 * STICKY, NOT FIXED. The app shell is a flex column whose single scroll region
 * is `main > div.overflow-y-auto` (AppLayout), and pinned regions elsewhere in
 * this app — the data-table headers, the filter search boxes — are all
 * `sticky`. position:fixed would take this out of that flow and need offsets
 * that duplicate the shell's own measurements.
 *
 * `self-start` stops the flex row stretching it to the height of a long
 * conversation, which is what would make it scroll away with the page. The
 * height is then the visible region rather than the content: 100dvh less the
 * 4rem nav and the shell's 2rem top and bottom padding. dvh rather than vh so
 * a mobile browser's collapsing address bar does not leave it overhanging.
 */
export function ConversationSidebar() {
  const { sidebarCollapsed, toggleSidebar } = useChat()

  return (
    <aside
      className={cn(
        'sticky top-0 hidden h-[calc(100dvh-8rem)] shrink-0 self-start',
        // Width is what animates. The list is hidden at the same time, so the
        // panel does not reflow its contents into a 2.5rem column on the way.
        'overflow-hidden transition-[width] duration-300 ease-out lg:block',
        sidebarCollapsed ? 'w-10' : 'w-60 border-r border-line',
      )}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div
          className={cn(
            'mb-2 flex shrink-0 items-center',
            // Collapsed, the toggle is the only thing left, so it centres in
            // the narrow rail instead of hugging one edge.
            sidebarCollapsed ? 'justify-center' : 'justify-between pr-3',
          )}
        >
          {!sidebarCollapsed && (
            <p className="font-display text-sm font-bold text-ink">Your chats</p>
          )}

          {/* THE TOGGLE LIVES IN THE RAIL, AND THE RAIL NEVER FULLY LEAVES.
              Collapsing to w-10 rather than w-0 is what keeps this reachable —
              a control that disappears with the panel it controls cannot bring
              it back. */}
          <button
            type="button"
            onClick={toggleSidebar}
            title={sidebarCollapsed ? 'Show conversations' : 'Hide conversations'}
            aria-label={sidebarCollapsed ? 'Show conversations' : 'Hide conversations'}
            aria-expanded={!sidebarCollapsed}
            className="shrink-0 rounded-lg p-1.5 text-muted transition-colors hover:bg-canvas-alt hover:text-ink"
          >
            {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* Unmounted while collapsed rather than merely hidden: it holds a
            confirm dialog and a scroll position, neither of which should be
            live behind a 2.5rem strip. */}
        {!sidebarCollapsed && (
          <div className="min-h-0 flex-1 pr-3">
            <SidebarBody />
          </div>
        )}
      </div>
    </aside>
  )
}

/** The same list as a drawer, for narrow viewports — a 240px rail beside the
 *  chat on a phone leaves neither readable, so below `lg` it hides behind the
 *  toggle in the Assistant header.
 *
 *  Separate open state from the desktop rail's `sidebarCollapsed`, because the
 *  two want opposite defaults: the rail sits open beside the chat and costs
 *  nothing, while this covers the conversation and must start shut. One
 *  boolean cannot default to both. They share this body and the provider's
 *  list, which is the part worth sharing. */
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
