import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Info } from 'lucide-react'

/**
 * The "what does this number mean" affordance that sits on every KPI.
 *
 * A dashboard figure is only trustworthy if the reader knows three things, and
 * a bare label tells them none of it:
 *
 *   what     — what the number is trying to say
 *   how      — how it is worked out, in the business's own terms
 *   differs  — how it differs from the similar-looking figure next to it
 *              (this is the one that stops "Delayed" and "Delay %" being read
 *              as the same thing)
 *   basis    — the denominator, supplied by the API rather than written here,
 *              so it can never drift from the data
 *
 * RENDERED IN A PORTAL, on purpose. KpiCard is `overflow-hidden` (it needs to
 * be, for the rounded corners and the coloured left border), which clipped an
 * absolutely-positioned panel to the inside of the card — the tooltip appeared
 * cut off. A portal to document.body escapes every ancestor's overflow and
 * stacking context, so the panel cannot be clipped by anything, on any page.
 *
 * Position is therefore computed from the trigger's own rect and set as fixed
 * coordinates: clamped to the viewport so it never runs off the right edge, and
 * flipped above the icon when there is no room below.
 *
 * Opens on hover AND on keyboard focus, and is reachable by tab, because a
 * hover-only explanation is no explanation for anyone using a keyboard. The
 * panel is `role="tooltip"` and referenced by aria-describedby, so a screen
 * reader announces it with the figure rather than as a stray paragraph.
 */

export interface MetricHelp {
  /** What the number is telling you. */
  what: string
  /** How it is calculated. */
  how: string
  /** How it differs from a similar KPI on the same screen, if any. */
  differs?: string
  /** Coverage/denominator — pass through from the API, never hardcode. */
  basis?: string
}

const PANEL_WIDTH = 288 // w-72
const GAP = 8
const MARGIN = 8

export function MetricInfo({ help, label }: { help: MetricHelp; label: string }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  // One timer shared by the icon and the panel, so moving the pointer from one
  // to the other does not close it mid-travel.
  const closeTimer = useRef<number | undefined>(undefined)
  const id = useId()

  const place = useCallback(() => {
    const trigger = triggerRef.current
    if (!trigger) return

    const rect = trigger.getBoundingClientRect()
    const height = panelRef.current?.offsetHeight ?? 0

    // Prefer below; flip above when the panel would run off the bottom.
    const spaceBelow = window.innerHeight - rect.bottom
    const below = spaceBelow >= height + GAP + MARGIN || spaceBelow >= rect.top
    const top = below ? rect.bottom + GAP : Math.max(MARGIN, rect.top - height - GAP)

    // Right-align to the icon, then clamp so it stays fully on screen.
    const ideal = rect.right - PANEL_WIDTH
    const left = Math.min(
      Math.max(MARGIN, ideal),
      Math.max(MARGIN, window.innerWidth - PANEL_WIDTH - MARGIN),
    )

    setPos({ top, left })
  }, [])

  const show = useCallback(() => {
    window.clearTimeout(closeTimer.current)
    setOpen(true)
  }, [])

  const hide = useCallback(() => {
    window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => setOpen(false), 120)
  }, [])

  // Measure once the panel exists, then keep it pinned to the icon while the
  // page moves underneath it.
  useEffect(() => {
    if (!open) return

    place()

    const onMove = () => place()
    // `true` so scrolling inside any container, not just the window, re-places.
    window.addEventListener('scroll', onMove, true)
    window.addEventListener('resize', onMove)

    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)

    // Touch has no hover and no Escape key, so a tap anywhere else is the only
    // way out. Harmless on desktop, where the pointer leaving already closed it.
    const onOutside = (e: PointerEvent) => {
      const target = e.target as Node
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return
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

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  return (
    <span className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        aria-label={`What is ${label}?`}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        className="inline-flex h-5 w-5 items-center justify-center rounded text-muted transition-colors hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        // Tapping is the only way in on a touch screen, where there is no
        // hover. Deliberately NOT a toggle: on desktop the hover has already
        // opened it by the time the click lands, so toggling would close the
        // panel the moment someone clicked the icon to read it.
        onClick={(e) => { e.preventDefault(); show() }}
      >
        <Info size={14} />
      </button>

      {open && createPortal(
        <div
          ref={panelRef}
          id={id}
          role="tooltip"
          onMouseEnter={show}
          onMouseLeave={hide}
          style={{
            position: 'fixed',
            top: pos?.top ?? -9999,
            left: pos?.left ?? -9999,
            width: PANEL_WIDTH,
            // Hidden until measured, so it never flashes in the wrong place.
            visibility: pos ? 'visible' : 'hidden',
          }}
          className="z-[100] rounded-lg border border-line bg-surface p-3 text-left shadow-lg"
        >
          <p className="text-xs font-semibold text-ink">{label}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-muted">{help.what}</p>

          <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
            How it's calculated
          </p>
          <p className="text-xs leading-relaxed text-muted">{help.how}</p>

          {help.differs && (
            <>
              <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                Not to be confused with
              </p>
              <p className="text-xs leading-relaxed text-muted">{help.differs}</p>
            </>
          )}

          {help.basis && (
            <p className="mt-2 border-t border-line pt-2 text-xs leading-relaxed text-ink">
              {help.basis}
            </p>
          )}
        </div>,
        document.body,
      )}
    </span>
  )
}
