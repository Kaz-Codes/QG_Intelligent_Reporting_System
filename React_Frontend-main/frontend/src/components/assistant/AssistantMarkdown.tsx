import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Renders the assistant's answer text. Markdown, not plain text — answers
// carry **bold** numbers, bullet breakdowns and (for an analytical question)
// four "### Descriptive - what the data shows" style lens headings. No
// @tailwindcss/typography in this app, so every element is styled by hand
// here, using the same tokens (text-ink, text-muted, border-line) as the
// rest of the page.

// The backend writes each lens heading as "### Descriptive - what the data
// shows" - the NAME is what the section-header pattern (descriptive /
// diagnostic / forecasting / prescriptive, one full-width label per section)
// needs; the phrase after the dash is prompt-writing guidance for the model,
// not something a reader needs repeated on screen, so only the name renders.
const LENS_SPLIT = /^\s*([A-Za-z]+)\s+[-–—]\s+(.*)$/

// A lens with nothing grounded renders as this exact word (see
// response_prompt.py's "THE HEADING ITSELF IS NEVER OMITTED" rule) - style it
// as a quiet placeholder rather than a normal sentence.
function isNotApplicable(children: unknown): boolean {
  const text = Array.isArray(children) ? children.join('') : String(children ?? '')
  return text.trim().toUpperCase() === 'N/A'
}

const components: Components = {
  h1: ({ children }) => <h2 className="mt-3 mb-1.5 text-base font-bold text-ink first:mt-0">{children}</h2>,
  h2: ({ children }) => <h3 className="mt-3 mb-1.5 text-sm font-bold text-ink first:mt-0">{children}</h3>,
  h3: ({ children }) => {
    const [first] = Array.isArray(children) ? children : [children]
    const match = typeof first === 'string' ? first.match(LENS_SPLIT) : null
    if (!match) {
      return <h3 className="mt-3 mb-1 text-sm font-bold text-ink first:mt-0">{children}</h3>
    }
    const [, lens] = match
    return (
      <h3 className="mt-5 mb-2 border-b border-line pb-1.5 text-xs font-bold tracking-wide text-brand uppercase first:mt-0">
        {lens}
      </h3>
    )
  },
  p: ({ children }) =>
    isNotApplicable(children) ? (
      <p className="text-sm text-muted italic [&:not(:first-child)]:mt-2">N/A</p>
    ) : (
      <p className="text-sm leading-relaxed text-ink [&:not(:first-child)]:mt-2">{children}</p>
    ),
  ul: ({ children }) => <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm leading-relaxed text-ink">{children}</ul>,
  ol: ({ children }) => <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-sm leading-relaxed text-ink">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-canvas-alt px-1 py-0.5 font-mono text-[0.8em] text-ink">{children}</code>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-brand underline underline-offset-2 hover:text-brand-deep">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="mt-2 overflow-x-auto rounded-lg border border-line">
      <table className="w-full text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-canvas-alt">{children}</thead>,
  th: ({ children }) => <th className="whitespace-nowrap px-2 py-1 text-left font-semibold text-muted">{children}</th>,
  td: ({ children }) => <td className="whitespace-nowrap px-2 py-1 text-ink">{children}</td>,
  tr: ({ children }) => <tr className="odd:bg-canvas">{children}</tr>,
  hr: () => <hr className="my-3 border-line" />,
  blockquote: ({ children }) => (
    <blockquote className="mt-2 border-l-2 border-line pl-3 text-sm text-muted italic">{children}</blockquote>
  ),
}

export function AssistantMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  )
}
