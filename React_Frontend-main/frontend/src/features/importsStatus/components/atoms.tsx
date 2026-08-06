import type { ReactNode } from 'react'
import { stageOf } from '@/lib/importsStatusData'

/**
 * Shared presentational atoms for Imports Status.
 *
 * FIX: this file previously referenced CSS custom properties that don't exist
 * in this theme — --color-warning, --color-danger, --color-success,
 * --color-accent, and every "-soft" suffix. The real tokens (see index.css)
 * are --color-risk / --color-watch / --color-healthy / --color-info, each with
 * a matching "-bg". Because none of the old names resolved, every status pill,
 * tag and payment dot rendered with a transparent/inherited colour — nothing
 * was visibly broken in markup, but nothing was ever visibly coloured either.
 *
 * Mapping used throughout this file and everywhere that imports it:
 *   danger  -> risk     (red)    late, unpaid, overdue, off-track
 *   warning -> watch    (amber)  pending, in progress, revised, needs review
 *   success -> healthy  (green)  paid, cleared, on time, complete
 *   info    -> info     (blue)   neutral / informational, no urgency implied
 */

const STAGE_STYLE: Record<string, { bg: string; fg: string; bd: string }> = {
  'Pre-shipment': { bg: 'var(--color-info-bg)', fg: 'var(--color-info)', bd: 'var(--color-info)' },
  Production: { bg: 'var(--color-watch-bg)', fg: 'var(--color-watch)', bd: 'var(--color-watch)' },
  'In transit': { bg: 'var(--color-info-bg)', fg: 'var(--color-info)', bd: 'var(--color-info)' },
  Clearance: { bg: 'var(--color-watch-bg)', fg: 'var(--color-watch)', bd: 'var(--color-watch)' },
  Inbound: { bg: 'var(--color-healthy-bg)', fg: 'var(--color-healthy)', bd: 'var(--color-healthy)' },
  Closed: { bg: 'var(--color-healthy-bg)', fg: 'var(--color-healthy)', bd: 'var(--color-healthy)' },
}

export function StatusPill({ status }: { status: string }) {
  const s = STAGE_STYLE[stageOf(status)] ?? STAGE_STYLE['Pre-shipment']
  return (
    <span
      className="inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap"
      style={{ backgroundColor: s.bg, color: s.fg, borderColor: s.bd }}
    >
      {status}
    </span>
  )
}

export type Tone = 'neutral' | 'warning' | 'danger' | 'success' | 'info'

const TONE_STYLE: Record<Exclude<Tone, 'neutral'>, { bg: string; fg: string }> = {
  danger: { bg: 'var(--color-risk-bg)', fg: 'var(--color-risk)' },
  warning: { bg: 'var(--color-watch-bg)', fg: 'var(--color-watch)' },
  success: { bg: 'var(--color-healthy-bg)', fg: 'var(--color-healthy)' },
  info: { bg: 'var(--color-info-bg)', fg: 'var(--color-info)' },
}

export function Tag({
  children, tone = 'neutral', title,
}: {
  children: ReactNode
  tone?: Tone
  title?: string
}) {
  if (tone === 'neutral') {
    return (
      <span
        title={title}
        className={`inline-block rounded border border-line bg-canvas-alt px-1.5 py-0.5 text-[11px] text-muted whitespace-nowrap ${title ? 'cursor-help' : ''}`}
      >
        {children}
      </span>
    )
  }
  const s = TONE_STYLE[tone]
  return (
    <span
      title={title}
      className={`inline-block rounded border px-1.5 py-0.5 text-[11px] whitespace-nowrap ${title ? 'cursor-help' : ''}`}
      style={{ backgroundColor: s.bg, color: s.fg, borderColor: s.fg }}
    >
      {children}
    </span>
  )
}

export function PaymentDot({ state }: { state: 'paid' | 'partial' | 'unpaid' }) {
  const color =
    state === 'paid' ? 'var(--color-healthy)' : state === 'partial' ? 'var(--color-watch)' : 'var(--color-risk)'
  return <span className="mr-1.5 inline-block h-[7px] w-[7px] rounded-full align-middle" style={{ backgroundColor: color }} />
}
