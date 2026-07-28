import type { ReactNode } from 'react'
import { stageOf } from '@/lib/importsStatusData'

/**
 * Shared presentational atoms for Imports Status. Kept tiny and dependency-free
 * so both the list and detail views render status, stage and pending-info the
 * same way. Colours come from CSS custom properties defined in the theme, so
 * these follow light/dark automatically.
 */

const STAGE_STYLE: Record<string, { bg: string; fg: string; bd: string }> = {
  'Pre-shipment': { bg: 'var(--color-info-soft)', fg: 'var(--color-info)', bd: 'var(--color-info)' },
  Production: { bg: 'rgba(84,69,155,.12)', fg: '#54459B', bd: '#54459B' },
  'In transit': { bg: 'var(--color-accent-soft)', fg: 'var(--color-accent)', bd: 'var(--color-accent)' },
  Clearance: { bg: 'var(--color-warning-soft)', fg: 'var(--color-warning)', bd: 'var(--color-warning)' },
  Inbound: { bg: 'var(--color-success-soft)', fg: 'var(--color-success)', bd: 'var(--color-success)' },
  Closed: { bg: 'var(--color-success-soft)', fg: 'var(--color-success)', bd: 'var(--color-success)' },
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

export function Tag({
  children, tone = 'neutral', title,
}: {
  children: ReactNode
  tone?: 'neutral' | 'warning' | 'danger' | 'success'
  title?: string
}) {
  const map = {
    neutral: 'border-line text-muted bg-canvas-alt',
    warning: 'text-[var(--color-warning)] bg-[var(--color-warning-soft)] border-[var(--color-warning)]/30',
    danger: 'text-[var(--color-danger)] bg-[var(--color-danger-soft)] border-[var(--color-danger)]/30',
    success: 'text-[var(--color-success)] bg-[var(--color-success-soft)] border-[var(--color-success)]/30',
  }
  return (
    <span
      title={title}
      className={`inline-block rounded border px-1.5 py-0.5 text-[11px] whitespace-nowrap ${map[tone]} ${title ? 'cursor-help' : ''}`}
    >
      {children}
    </span>
  )
}

export function PaymentDot({ state }: { state: 'paid' | 'partial' | 'unpaid' }) {
  const color =
    state === 'paid' ? 'var(--color-success)' : state === 'partial' ? 'var(--color-accent)' : 'var(--color-danger)'
  return <span className="mr-1.5 inline-block h-[7px] w-[7px] rounded-full align-middle" style={{ backgroundColor: color }} />
}
