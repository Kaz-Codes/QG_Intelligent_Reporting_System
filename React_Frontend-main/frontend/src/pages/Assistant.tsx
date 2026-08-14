import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Sparkles, Trash2 } from 'lucide-react'
import { AssistantChart } from '@/components/assistant/AssistantChart'
import { AssistantDataTable } from '@/components/assistant/AssistantDataTable'
import { AssistantMarkdown } from '@/components/assistant/AssistantMarkdown'
import { ClarifyOptions } from '@/components/assistant/ClarifyOptions'
import { DevDetailsPanel } from '@/components/assistant/DevDetailsPanel'
import { useChat } from '@/lib/chatbot/ChatProvider'
import { useChatHealth } from '@/lib/chatbot/useHealth'
import type { AssistantMessage } from '@/lib/chatbot/types'
// Tightly cropped from qadri_logo_transparent.webp — that source has ~75px
// of transparent padding baked into its square canvas (top/bottom), which
// stacked with this page's own spacing read as a large gap before "QG-IRS".
import logo from '@/assets/qadri_logo_tight.webp'
// Dedicated dark-theme mark — a glowing gold/orange ring on black, which
// reads correctly against the dark canvas where the flat-black light mark
// would disappear.
import logoDark from '@/assets/qadri_logo_tight_dark.png'
import { cn } from '@/lib/utils'
import { useTheme } from '@/theme/ThemeContext'

const BOT_NAME = 'QG-IRS'

const SUGGESTED_QUERIES = [
  'Which purchase orders are delayed?',
  'Which supplier has the most delays?',
  'Which items are below reorder level?',
  'Show imports pending clearance',
]

// The mark is a transparent cut-out, so it gets no tile treatment — a rounded
// card + ring + shadow would draw a box around the empty space in the logo's
// corners rather than around the logo itself.
function BotAvatar({ size = 44 }: { size?: number }) {
  const { dark } = useTheme()
  return (
    <img
      src={dark ? logoDark : logo}
      alt={BOT_NAME}
      width={size}
      height={size}
      className="shrink-0 object-contain"
      style={{ width: size, height: size }}
    />
  )
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 animate-bounce rounded-full bg-muted"
          style={{ animationDelay: `${i * 150}ms`, animationDuration: '900ms' }}
        />
      ))}
    </div>
  )
}

function AssistantResult({
  message,
  onOptionClick,
  disabled,
}: {
  message: AssistantMessage
  onOptionClick: (option: string) => void
  disabled: boolean
}) {
  const { content, meta, rows = [], columns, charts = [], clarificationOptions = [] } = message
  const hasData = rows.length > 0
  const chartList = hasData ? charts.filter((c) => c && c.type && c.type !== 'none') : []
  const computedTable =
    meta?.computationResult &&
    typeof meta.computationResult === 'object' &&
    (meta.computationResult as { kind?: string }).kind === 'table'
      ? (meta.computationResult as { columns?: string[]; rows?: Record<string, unknown>[] })
      : null

  return (
    <div className="flex flex-col gap-3">
      <AssistantMarkdown content={content} />

      <ClarifyOptions options={clarificationOptions} onPick={onOptionClick} disabled={disabled} />

      {chartList.map((spec, i) => (
        <AssistantChart key={i} spec={spec} rows={rows} />
      ))}

      {hasData && <AssistantDataTable columns={columns} rows={rows} />}

      {computedTable && (
        <div>
          <p className="mb-1 text-xs font-medium text-muted">
            Computed result{meta?.computationExplanation ? ` — ${meta.computationExplanation}` : ''}
          </p>
          <AssistantDataTable columns={computedTable.columns} rows={computedTable.rows ?? []} />
        </div>
      )}

      {meta && <DevDetailsPanel meta={meta} />}
    </div>
  )
}

export function Assistant() {
  const { messages, isSending, status, error, send, clearConversation } = useChat()
  const { status: connection } = useChatHealth()
  const [input, setInput] = useState('')
  // An empty sentinel at the end of the message list, scrolled into view
  // rather than scrolling the container directly — works whichever element
  // ends up being the actual scroll parent.
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, status])

  function handleSend(question: string) {
    setInput('')
    void send(question)
  }

  const empty = messages.length === 0

  const inputBar = (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (input.trim()) handleSend(input)
      }}
      className="flex w-full items-center gap-2 rounded-2xl border border-line bg-surface p-2 shadow-sm focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20"
    >
      <Sparkles size={18} className="ml-2 shrink-0 text-brand-light" />
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        // ENTER SENDS - with or without Shift.
        //
        // A single-line input has no second line to go to, but the browser
        // only submits a form on a bare Enter: press Shift+Enter and the
        // keystroke is swallowed, so the message just sits there looking
        // ignored. Handling the key directly makes both send.
        onKeyDown={(e) => {
          if (e.key !== 'Enter' || e.nativeEvent.isComposing) return
          e.preventDefault()
          if (input.trim() && !isSending) handleSend(input)
        }}
        placeholder={`Message ${BOT_NAME}…`}
        autoFocus
        className="flex-1 bg-transparent px-1 text-sm text-ink outline-none placeholder:text-muted"
      />
      <button
        type="submit"
        disabled={!input.trim() || isSending}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand text-on-brand transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <ArrowUp size={18} />
      </button>
    </form>
  )

  // Landing state — one centered block (logo, name, the input itself, a few
  // quick-start prompts) filling the whole page, nothing else. No header, no
  // chrome. Switches to the full chat layout below the instant a message is
  // sent.
  if (empty) {
    return (
      // min-h-full (see AppLayout): fills the available viewport for
      // centering without a page-specific height calc, and simply grows —
      // no clipping, no forced overflow — if it ever needs more than that.
      <div className="flex min-h-full flex-col items-center justify-center px-4">
        <div className="animate-fade-in-up w-full max-w-xl text-center">
          {/* No drop shadow on the wrapper: with a transparent mark it renders
              as a rectangular glow behind empty space. */}
          <div className="mx-auto mb-3 w-fit">
            <BotAvatar size={210} />
          </div>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-navy">{BOT_NAME}</h1>
          <p className="mt-2 text-sm text-muted">Purchases, inventory, imports, or logistics — in plain language.</p>

          <div className="mt-6">{inputBar}</div>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {SUGGESTED_QUERIES.map((s) => (
              <button
                key={s}
                onClick={() => handleSend(s)}
                className="rounded-xl border border-line bg-surface px-4 py-3 text-left text-sm text-ink shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-light hover:shadow-md"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    // min-h-full (see AppLayout) — at least the full available viewport, so
    // the input bar below sits at the bottom of the SCREEN even with only one
    // or two messages, not right after them. Grows past that for a longer
    // conversation, scrolling in the app's one shared scroll region — this
    // page has no scroll container of its own.
    <div className="flex min-h-full flex-col">
      {/* Header — only shown once a conversation is underway. */}
      <div className="flex items-center justify-between pb-4">
        <div className="flex items-center gap-3">
          <BotAvatar size={92} />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-xl font-bold text-navy">{BOT_NAME}</h1>
              {connection === 'online' ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-healthy-bg px-2 py-0.5 text-xs font-semibold text-healthy">
                  <span className="h-1.5 w-1.5 rounded-full bg-healthy" /> Online
                </span>
              ) : connection === 'offline' ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-risk-bg px-2 py-0.5 text-xs font-semibold text-risk">
                  <span className="h-1.5 w-1.5 rounded-full bg-risk" /> Offline
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-watch-bg px-2 py-0.5 text-xs font-semibold text-watch">
                  <span className="h-1.5 w-1.5 rounded-full bg-watch" /> Connecting…
                </span>
              )}
            </div>
            <p className="text-xs text-muted">Purchases, inventory, imports and logistics — live from the database</p>
          </div>
        </div>
        <button
          onClick={clearConversation}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-canvas-alt hover:text-risk"
        >
          <Trash2 size={13} /> Clear
        </button>
      </div>

      {/* Conversation — flex-1 so it (not the input bar) absorbs the space
          between header and input when there are few messages, pushing the
          input to the bottom of the screen. No overflow/scroll of its own:
          this page scrolls in the app's one shared scroll region, same as
          every other page. */}
      <div className="flex flex-1 flex-col gap-5 pb-4">
        {messages.map((m) => {
          const isUser = m.role === 'user'
          // An assistant message exists from the moment the stream starts;
          // don't render an empty bubble before the first token arrives.
          if (!isUser && m.streaming && !m.content) return null
          return (
            <div key={m.id} className={cn('animate-fade-in-up flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
              {!isUser && <BotAvatar />}
              <div
                className={cn(
                  'max-w-[85%] rounded-2xl px-4 py-3',
                  isUser ? 'bg-brand text-on-brand' : m.failed ? 'border border-risk/40 bg-risk-bg' : 'border border-line bg-surface',
                )}
              >
                {isUser ? (
                  <p className="text-sm leading-relaxed">{m.content}</p>
                ) : m.failed ? (
                  <span className="text-sm text-risk">That message could not be answered. Please try again.</span>
                ) : (
                  <AssistantResult message={m} onOptionClick={handleSend} disabled={isSending} />
                )}
              </div>
            </div>
          )
        })}
        {isSending && !messages[messages.length - 1]?.content && (
          <div className="animate-fade-in flex gap-3">
            <BotAvatar />
            <div className="rounded-2xl border border-line bg-surface px-4 py-3">
              {status ? <p className="text-xs text-muted">{status}</p> : <TypingDots />}
            </div>
          </div>
        )}
        {/* Scrolled into view on every new message. */}
        <div ref={bottomRef} />
      </div>

      {error && <p className="mb-2 mt-2 text-xs text-risk">{error}</p>}
      {/* Sticky, not fixed: pins to the bottom of the app's one shared scroll
          region as it scrolls (see AppLayout's min-h-full), rather than to
          the browser viewport — a `fixed` bar would sit on top of that
          region regardless of scroll position and ignore its own padding. */}
      <div className="fixed bottom-0 left-0 right-0 z-50  px-8 pb-4 pt-3">
        {inputBar}
      </div>
    </div>
  )
}
