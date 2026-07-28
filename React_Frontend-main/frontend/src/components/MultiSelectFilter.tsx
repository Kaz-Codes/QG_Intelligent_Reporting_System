import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronDown, X } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface Props {
  label: string
  options: string[]
  value: string[]
  onChange: (value: string[]) => void
}

interface MenuPosition {
  top: number
  left: number
  width: number
  maxHeight: number
  openUp: boolean
}

const MARGIN = 8
const PREFERRED_MAX_HEIGHT = 320

/**
 * Multi-value filter dropdown. An empty selection means "no filter" (same
 * as the old Streamlit ui.multiselect_filter()) — shown as the "All"
 * placeholder rather than requiring an explicit "All" option to pick.
 *
 * The menu is portaled to <body> and positioned with `fixed` coordinates
 * measured from the trigger button, instead of `absolute` inside the filter
 * bar. That sidesteps a whole class of bugs an in-flow menu runs into on a
 * scrolling page: clipping by an ancestor's overflow, losing a z-index
 * stacking fight against a sibling card, and drifting out of sync with its
 * button. It repositions on scroll/resize instead of just closing, and
 * flips to open upward when there isn't room below.
 */
export function MultiSelectFilter({ label, options, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<MenuPosition | null>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, value.length])

  useEffect(() => {
    if (!open) return
    function onReposition() {
      updatePosition()
    }
    window.addEventListener('scroll', onReposition, true)
    window.addEventListener('resize', onReposition)
    return () => {
      window.removeEventListener('scroll', onReposition, true)
      window.removeEventListener('resize', onReposition)
    }
  }, [open])

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      const target = e.target as Node
      if (wrapRef.current?.contains(target)) return
      if (menuRef.current?.contains(target)) return
      setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open])

  function toggle(option: string) {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option])
  }

  return (
    <div className="flex w-full min-w-[160px] flex-col gap-1.5 sm:w-48" ref={wrapRef}>
      <Label>{label}</Label>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'flex h-10 w-full items-center justify-between gap-2 rounded-lg border bg-surface px-3 text-left text-sm text-ink',
          'transition-colors duration-150',
          open ? 'border-brand ring-2 ring-brand/20' : 'border-line hover:border-brand-light',
        )}
      >
        <span className="flex flex-1 flex-wrap items-center gap-1 overflow-hidden">
          {value.length === 0 ? (
            <span className="text-muted">All</span>
          ) : (
            value.map((v) => (
              <span
                key={v}
                className="animate-scale-in flex items-center gap-1 rounded-md bg-brand-soft px-1.5 py-0.5 text-xs font-medium text-brand"
              >
                {v}
                <X
                  size={12}
                  className="cursor-pointer transition-colors hover:text-risk"
                  onClick={(e) => {
                    e.stopPropagation()
                    toggle(v)
                  }}
                />
              </span>
            ))
          )}
        </span>
        <ChevronDown
          size={16}
          className={cn('shrink-0 text-muted transition-transform duration-200', open && 'rotate-180')}
        />
      </button>

      {open && pos && createPortal(
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: pos.top, left: pos.left, minWidth: pos.width, maxHeight: pos.maxHeight }}
          className={cn(
            'animate-scale-in z-50 w-max max-w-xs overflow-y-auto overscroll-contain rounded-lg border border-line bg-surface py-1 shadow-lg',
            pos.openUp ? 'origin-bottom' : 'origin-top',
          )}
        >
          {options.map((option) => (
            <label
              key={option}
              className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm text-ink transition-colors duration-100 hover:bg-canvas-alt"
            >
              <input
                type="checkbox"
                checked={value.includes(option)}
                onChange={() => toggle(option)}
                className="accent-brand"
              />
              {option}
            </label>
          ))}
        </div>,
        document.body,
      )}
    </div>
  )
}
