import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, Check } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface Props {
  label: string
  options: string[]
  value: string
  onChange: (value: string) => void
}

/**
 * Single-value dropdown — the sibling of MultiSelectFilter, for filters a
 * backend endpoint only accepts one value of at a time (a plain `?work=`
 * style query param, not an array). Empty string means "no filter", shown as
 * the "All" option.
 *
 * This was a native <select>, which cannot carry a search box. On real data
 * that made it unusable: the supplier list runs to hundreds of entries and
 * finding one meant scrolling a native menu with no way to type. It is now the
 * same portalled, searchable menu the multi-select uses, so both filters
 * behave identically wherever they appear.
 */

const MARGIN = 8
const PREFERRED_MAX_HEIGHT = 320
const SEARCH_THRESHOLD = 8

interface MenuPosition {
  top: number
  left: number
  width: number
  maxHeight: number
  openUp: boolean
}

export function SingleSelectFilter({ label, options, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<MenuPosition | null>(null)
  const [query, setQuery] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  const needle = query.trim().toLowerCase()
  // The current selection stays listed however the search is narrowed, so the
  // menu always shows what is actually filtered.
  const shown = needle
    ? options.filter((o) => o.toLowerCase().includes(needle) || o === value)
    : options

  function updatePosition() {
    const rect = buttonRef.current?.getBoundingClientRect()
    if (!rect) return
    const spaceBelow = window.innerHeight - rect.bottom - MARGIN
    const spaceAbove = rect.top - MARGIN
    const openUp = spaceBelow < 160 && spaceAbove > spaceBelow
    const maxHeight = Math.max(120, Math.min(PREFERRED_MAX_HEIGHT, openUp ? spaceAbove : spaceBelow))
    setPos({
      top: openUp ? rect.top - maxHeight - 4 : rect.bottom + 4,
      left: rect.left,
      width: rect.width,
      maxHeight,
      openUp,
    })
  }

  useLayoutEffect(() => {
    if (open) updatePosition()
  }, [open])

  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }

    const reposition = () => updatePosition()
    // `true` so scrolling any ancestor keeps the menu pinned to its button.
    window.addEventListener('scroll', reposition, true)
    window.addEventListener('resize', reposition)

    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', onKey)

    const onOutside = (e: PointerEvent) => {
      const t = e.target as Node
      if (wrapRef.current?.contains(t) || menuRef.current?.contains(t)) return
      setOpen(false)
    }
    document.addEventListener('pointerdown', onOutside)

    return () => {
      window.removeEventListener('scroll', reposition, true)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onOutside)
    }
  }, [open])

  function pick(next: string) {
    onChange(next)
    setOpen(false)
  }

  return (
    <div ref={wrapRef} className="flex w-full min-w-40 flex-col gap-1.5 sm:w-48">
      <Label>{label}</Label>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-10 w-full items-center justify-between gap-2 rounded-lg border border-line bg-surface px-2.5 text-left text-sm text-ink transition-colors duration-150 hover:border-brand-light focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
      >
        <span className={cn('truncate', !value && 'text-muted')}>{value || 'All'}</span>
        <ChevronDown
          size={16}
          className={cn('shrink-0 text-muted transition-transform duration-200', open && 'rotate-180')}
        />
      </button>

      {open && pos && createPortal(
        <div
          ref={menuRef}
          role="listbox"
          style={{ position: 'fixed', top: pos.top, left: pos.left, minWidth: pos.width, maxHeight: pos.maxHeight }}
          className={cn(
            'animate-scale-in z-50 w-max max-w-xs overflow-y-auto overscroll-contain rounded-lg border border-line bg-surface py-1 shadow-lg',
            pos.openUp ? 'origin-bottom' : 'origin-top',
          )}
        >
          {options.length > SEARCH_THRESHOLD && (
            <div className="sticky top-0 z-10 border-b border-line bg-surface px-2 pb-1.5 pt-1">
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Search ${options.length} options…`}
                className="h-7 w-full rounded border border-line bg-canvas px-2 text-xs text-ink placeholder:text-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
                onKeyDown={(e) => {
                  if (e.key === 'Escape' && query) {
                    e.stopPropagation()
                    setQuery('')
                  }
                }}
              />
            </div>
          )}

          {/* "All" is how the filter is cleared, so it is never searched away. */}
          <button
            type="button"
            role="option"
            aria-selected={!value}
            onClick={() => pick('')}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-muted transition-colors duration-100 hover:bg-canvas-alt"
          >
            <span className="w-3.5 shrink-0">{!value && <Check size={14} className="text-brand" />}</span>
            All
          </button>

          {options.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted">No values available</p>
          )}
          {options.length > 0 && shown.length === 0 && (
            <p className="px-3 py-2 text-sm text-muted">Nothing matches “{query}”</p>
          )}

          {shown.map((option) => (
            <button
              key={option}
              type="button"
              role="option"
              aria-selected={option === value}
              onClick={() => pick(option)}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-ink transition-colors duration-100 hover:bg-canvas-alt"
            >
              <span className="w-3.5 shrink-0">
                {option === value && <Check size={14} className="text-brand" />}
              </span>
              <span className="truncate">{option}</span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  )
}
