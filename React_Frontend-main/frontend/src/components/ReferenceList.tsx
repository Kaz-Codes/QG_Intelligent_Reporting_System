import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { List } from 'lucide-react'

/**
 * "Which records is this number about?"
 *
 * A headline count cannot be checked or acted on by itself — "19 delayed" gives
 * nobody anything to chase. This puts the actual references one click away, so
 * a figure on a dashboard leads to the payment reference, GD number and works
 * you need to go and look the consignment up.
 *
 * Portalled and positioned for the same reason MetricInfo is: KpiCard is
 * `overflow-hidden` for its rounded corners and coloured edge, which would clip
 * a panel rendered inside it.
 *
 * Click, not hover: this is a list you read and scroll, so it stays open until
 * dismissed rather than vanishing when the pointer moves onto it.
 */

export interface ReferenceItem {
  id: number
  reference: string
  gd_number?: string | null
  supplier?: string | null
  works?: string | null
  status?: string | null
}

export interface ReferenceSet {
  total: number
  shown: number
  items: ReferenceItem[]
}

const PANEL_WIDTH = 340
const GAP = 8
const MARGIN = 8

export function ReferenceList({ label, refs }: { label: string; refs?: ReferenceSet }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const id = useId()

  const place = useCallback(() => {
    const trigger = triggerRef.current
    if (!trigger) return

    const rect = trigger.getBoundingClientRect()
    const height = panelRef.current?.offsetHeight ?? 0

    const spaceBelow = window.innerHeight - rect.bottom
    const below = spaceBelow >= height + GAP + MARGIN || spaceBelow >= rect.top
    const top = below ? rect.bottom + GAP : Math.max(MARGIN, rect.top - height - GAP)

    const ideal = rect.right - PANEL_WIDTH
    const left = Math.min(
      Math.max(MARGIN, ideal),
      Math.max(MARGIN, window.innerWidth - PANEL_WIDTH - MARGIN),
    )

    setPos({ top, left })
  }, [])

  useEffect(() => {
    if (!open) return
    place()

    const onMove = () => place()
    window.addEventListener('scroll', onMove, true)
    window.addEventListener('resize', onMove)

    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)

    const onOutside = (e: PointerEvent) => {
      const t = e.target as Node
      if (triggerRef.current?.contains(t) || panelRef.current?.contains(t)) return
      setOpen(false)
    }
    document.addEventListener('pointerdown', onOutside)

    return () => {
      window.removeEventListener('scroll', onMove, true)
      window.removeEventListener('resize', onMove)
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onOutside)
    }
  }, [open, place])

  // Nothing behind the number means nothing to show.
  if (!refs || refs.total === 0) return null

  return (
    <span className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Show the ${refs.total} records behind ${label}`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
        onClick={() => setOpen((v) => !v)}
      >
        <List size={14} />
      </button>

      {open && createPortal(
        <div
          ref={panelRef}
          id={id}
          style={{
            position: 'fixed',
            top: pos?.top ?? -9999,
            left: pos?.left ?? -9999,
            width: PANEL_WIDTH,
            visibility: pos ? 'visible' : 'hidden',
          }}
          className="z-[100] rounded-lg border border-line bg-surface shadow-lg"
        >
          <div className="flex items-baseline justify-between border-b border-line px-3 py-2">
            <p className="text-xs font-semibold text-ink">{label}</p>
            <p className="text-[11px] text-muted">
              {refs.shown < refs.total
                ? `first ${refs.shown} of ${refs.total}`
                : `${refs.total} record${refs.total === 1 ? '' : 's'}`}
            </p>
          </div>

          {/* Scrollable, because a KPI can sit over hundreds of records. */}
          <div className="max-h-72 overflow-y-auto">
            {refs.items.map((r) => (
              <div key={r.id} className="border-b border-line px-3 py-2 last:border-b-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-xs font-semibold text-ink">{r.reference}</span>
                  {r.status && <span className="shrink-0 text-[11px] text-muted">{r.status}</span>}
                </div>
                <p className="mt-0.5 truncate text-[11px] text-muted">
                  {[r.supplier, r.works, r.gd_number && `GD ${r.gd_number}`]
                    .filter(Boolean)
                    .join(' · ') || '—'}
                </p>
              </div>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </span>
  )
}
