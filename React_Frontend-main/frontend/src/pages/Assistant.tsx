import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Sparkles, Trash2 } from 'lucide-react'
import { DataTable } from '@/components/DataTable'
import { Donut } from '@/components/charts/Donut'
import { askQadriBot, SUGGESTED_QUERIES, type BotAnswer } from '@/lib/mockData/assistant'
import logo from '@/assets/qadri_logo_transparent.png'
import { cn } from '@/lib/utils'

const BOT_NAME = 'QG-IRS'

interface Message {
  role: 'user' | 'bot'
  text: string
  answer?: BotAnswer
}

function BotAvatar({ size = 36 }: { size?: number }) {
  return (
    <img
      src={logo}
      alt={BOT_NAME}
      width={size}
      height={size}
      className="shrink-0 rounded-xl shadow-sm ring-1 ring-line"
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

function BotResult({ answer }: { answer: BotAnswer }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm leading-relaxed text-ink" dangerouslySetInnerHTML={{ __html: mdBold(answer.text) }} />
      {answer.table && (
        <DataTable columns={answer.table.columns} rows={answer.table.rows} height={320} />
      )}
      {answer.chart && (
        <div className="rounded-xl border border-line p-2">
          <Donut labels={answer.chart.labels} values={answer.chart.values} height={260} />
        </div>
      )}
    </div>
  )
}

// Tiny **bold** -> <strong> so canned answers can emphasize numbers without a
// full markdown dependency. Input is our own trusted mock text, not user input.
function mdBold(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
}

export function Assistant() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, thinking])

  function send(question: string) {
    const q = question.trim()
    if (!q || thinking) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', text: q }])
    setThinking(true)
    // Simulated latency so the typing indicator reads as "working," not instant.
    window.setTimeout(() => {
      const answer = askQadriBot(q)
      setMessages((m) => [...m, { role: 'bot', text: answer.text, answer }])
      setThinking(false)
    }, 650)
  }

  const empty = messages.length === 0

  const inputBar = (
    <form
      onSubmit={(e) => { e.preventDefault(); send(input) }}
      className="flex items-center gap-2 rounded-2xl border border-line bg-surface p-2 shadow-sm focus-within:border-brand focus-within:ring-2 focus-within:ring-brand/20"
    >
      <Sparkles size={18} className="ml-2 shrink-0 text-brand-light" />
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder={`Message ${BOT_NAME}…`}
        autoFocus
        className="flex-1 bg-transparent px-1 text-sm text-ink outline-none placeholder:text-muted"
      />
      <button
        type="submit"
        disabled={!input.trim() || thinking}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand text-white transition-transform hover:scale-105 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <ArrowUp size={18} />
      </button>
    </form>
  )

  // Landing state — one centered block (logo, name, the input itself, a few
  // quick-start prompts) filling the whole page, nothing else. No header,
  // no chrome: the Google-homepage moment for the app's default landing
  // page. It switches to the full chat layout below the instant a message
  // is sent.
  if (empty) {
    return (
      <div className="flex h-[calc(100vh-4rem)] flex-col items-center justify-center px-4">
        <div className="animate-fade-in-up w-full max-w-xl text-center">
          <div className="mx-auto mb-5 w-fit rounded-2xl shadow-lg" style={{ boxShadow: '0 10px 28px rgba(79,70,229,.28)' }}>
            <BotAvatar size={64} />
          </div>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-navy">{BOT_NAME}</h1>
          <p className="mt-2 text-sm text-muted">Purchases, inventory, imports, or logistics — in plain language.</p>

          <div className="mt-6">{inputBar}</div>

          <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
            {SUGGESTED_QUERIES.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
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
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {/* Header — only shown once a conversation is underway. */}
      <div className="flex items-center justify-between pb-4">
        <div className="flex items-center gap-3">
          <BotAvatar size={40} />
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-display text-xl font-bold text-navy">{BOT_NAME}</h1>
              <span className="inline-flex items-center gap-1 rounded-full bg-healthy-bg px-2 py-0.5 text-xs font-semibold text-healthy">
                <span className="h-1.5 w-1.5 rounded-full bg-healthy" /> Online
              </span>
            </div>
            <p className="text-xs text-muted">Supply-chain assistant · sample data</p>
          </div>
        </div>
        <button
          onClick={() => setMessages([])}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-canvas-alt hover:text-risk"
        >
          <Trash2 size={13} /> Clear
        </button>
      </div>

      {/* Conversation */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="flex flex-col gap-5 pb-4">
          {messages.map((m, i) => (
            <div
              key={i}
              className={cn('animate-fade-in-up flex gap-3', m.role === 'user' ? 'justify-end' : 'justify-start')}
            >
              {m.role === 'bot' && <BotAvatar />}
              <div
                className={cn(
                  'max-w-[85%] rounded-2xl px-4 py-3',
                  m.role === 'user'
                    ? 'bg-brand text-white'
                    : 'border border-line bg-surface',
                )}
              >
                {m.role === 'user'
                  ? <p className="text-sm leading-relaxed">{m.text}</p>
                  : m.answer && <BotResult answer={m.answer} />}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="animate-fade-in flex gap-3">
              <BotAvatar />
              <div className="rounded-2xl border border-line bg-surface px-4 py-3">
                <TypingDots />
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="mt-3">{inputBar}</div>
    </div>
  )
}
