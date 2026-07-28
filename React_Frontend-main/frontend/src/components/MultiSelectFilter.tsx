import { useEffect, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface Props {
  label: string
  options: string[]
  value: string[]
  onChange: (value: string[]) => void
}

/**
 * Multi-value filter dropdown. An empty selection means "no filter" (same
 * as the old Streamlit ui.multiselect_filter()) — shown as the "All"
 * placeholder rather than requiring an explicit "All" option to pick.
 */
export function MultiSelectFilter({ label, options, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  // Close on page scroll instead of letting the menu float along with it —
  // once its trigger button scrolls out of view the menu looks orphaned and
  // can pick up stray hover state from whatever's now under the cursor.
  // Scrolling *inside* the menu's own option list (long lists) is exempt.
  useEffect(() => {
    if (!open) return
    function onScroll(e: Event) {
      if (menuRef.current && e.target instanceof Node && menuRef.current.contains(e.target)) return
      setOpen(false)
    }
    document.addEventListener('scroll', onScroll, true)
    return () => document.removeEventListener('scroll', onScroll, true)
  }, [open])

  function toggle(option: string) {
    onChange(value.includes(option) ? value.filter((v) => v !== option) : [...value, option])
  }

  return (
    <div className="flex w-full min-w-[160px] flex-col gap-1.5 sm:w-48" ref={ref}>
      <Label>{label}</Label>
      <div className="relative">
        <button
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

        {open && (
          <div
            ref={menuRef}
            className="animate-scale-in absolute z-20 mt-1 max-h-[min(20rem,60vh)] w-max min-w-full max-w-xs origin-top overflow-y-auto overscroll-contain rounded-lg border border-line bg-surface py-1 shadow-lg"
          >
            {options.map((option) => (
              <label
                key={option}
                className={cn(
                  'flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm text-ink transition-colors duration-100 hover:bg-canvas-alt',
                )}
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
          </div>
        )}
      </div>
    </div>
  )
}
