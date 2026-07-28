import type { ReactNode } from 'react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'

/**
 * Small field wrappers shared by every wizard step, so all seven look identical
 * and error handling is written once. These use their Label/Input primitives
 * and the `text-risk` token their scaffold already uses for errors.
 */

export function Field({
  label, htmlFor, error, hint, required, span, children,
}: {
  label: string
  htmlFor?: string
  error?: string
  hint?: string
  required?: boolean
  span?: boolean
  children: ReactNode
}) {
  return (
    <div className={`flex flex-col gap-1.5 ${span ? 'sm:col-span-2 lg:col-span-4' : ''}`}>
      <Label htmlFor={htmlFor}>
        {label}
        {required && <span className="ml-0.5 text-brand">*</span>}
      </Label>
      {children}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-risk">{error}</p>}
    </div>
  )
}

/** Native select styled to match their Input. */
export function Select({
  id, value, onChange, children, ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      id={id}
      value={value}
      onChange={onChange}
      className="flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
      {...rest}
    >
      {children}
    </select>
  )
}

export { Label, Input }

/** Amber "still pending" strip. Never blocks progress — states that plainly. */
export function PendingBanner({ items, note }: { items: string[]; note?: string }) {
  if (items.length === 0) return null
  return (
    <div className="rounded-r border-l-4 border-[var(--color-warning,#B4531A)] bg-[var(--color-warning-soft,#FBEDE2)] px-3.5 py-2.5 text-sm text-[var(--color-warning,#B4531A)]">
      <b className="font-semibold">Pending:</b> {items.join('; ')}.{' '}
      {note ?? 'This does not block submission.'}
    </div>
  )
}

/** Brass explanatory note, for the "why is this per item" style asides. */
export function Callout({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-r border-l-4 border-brand bg-brand/5 px-3.5 py-2.5 text-sm text-ink/70">
      {children}
    </div>
  )
}

/** A read-only strip of key header fields, so later steps show which
 *  consignment is being edited. */
export function CarriedContext({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="flex flex-wrap gap-x-6 gap-y-2 rounded-lg border border-line bg-canvas-alt px-3.5 py-2.5">
      {items.map((it) => (
        <div key={it.label}>
          <div className="text-[10px] uppercase tracking-wide text-muted">{it.label}</div>
          <div className="text-[13px] font-medium">{it.value || '—'}</div>
        </div>
      ))}
    </div>
  )
}
