import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Input } from './input'
import { cn } from '@/lib/utils'

/**
 * Typeahead select — the combobox primitive this project did not have.
 *
 * Every "pick a master record" field in the app is a plain text input with a
 * `<datalist>` today, which cannot show a secondary line, cannot be driven
 * from a search endpoint, and gives no keyboard affordance beyond the
 * browser's own. This is the shared replacement.
 *
 * It deliberately builds on `Input` rather than restyling a bare `<input>`, so
 * the field cannot drift from the rest of the form as input.tsx changes.
 *
 * TWO SOURCES, ONE COMPONENT. Pass `options` for a small in-memory master
 * (branches, ports), or `loadOptions` for a search endpoint (the item
 * catalogue, which is far too big to ship to the client). `loadOptions` is
 * debounced, and its identity must be STABLE — define it at module scope or
 * wrap it in useCallback, or every render restarts the search.
 *
 * FREE TEXT IS OPT-IN. With `allowFreeText` a value that matches nothing is
 * still accepted and reported on every keystroke, which is what a field
 * backed by an incomplete master needs (an imports line may carry a
 * generated `IMP-<hash>` code that was never in the catalogue). Without it
 * the input reverts to the last committed value on blur, so the field can
 * only ever hold something real.
 *
 * CONTROLLED, and shaped for react-hook-form: `value` + `onChange(string)` is
 * exactly what `<Controller render={({ field }) => ...} />` hands over, so it
 * drops in as `{...field}` without an adapter.
 */

/**
 * The marker shown beside a master-backed field holding a value the master
 * does not have. Its companion, so it lives here.
 *
 * DATA QUALITY IS MADE VISIBLE, NOT ENFORCED. These fields carry years of
 * free text — 1,424 loaded logistics orders hold a customer name with no
 * master row behind it — so an unmatched value is normal, must still save,
 * and must never quietly mint a master record from a typo.
 *
 * `stored` is the honest part, and it differs per field because the three
 * modules made different storage choices:
 *   'text' — there is a name column, so what was typed is kept as typed and
 *            simply is not linked to a master row.
 *   'none' — the column is a foreign key with nowhere to put a name, so an
 *            unmatched value cannot survive the save at all. Saying so is the
 *            whole point: the alternative is a field that looks accepted and
 *            comes back empty.
 */
export function NotInMasterNote({ master, stored }: { master: string; stored: 'text' | 'none' }) {
  return (
    <p className="text-xs text-[var(--color-watch)]">
      {stored === 'text'
        ? `Not in the ${master} — saved as typed, but not linked to a master record.`
        : `Not in the ${master} — this will NOT be saved. Pick an existing one, or add it under Masters first.`}
    </p>
  )
}

export interface SearchableOption<T = unknown> {
  /** What goes into the form field when this option is chosen. */
  value: string
  /** Primary display text. */
  label: string
  /** Secondary muted text — a name beside a code, a country beside a port. */
  hint?: string
  /** The full source record, handed back by `onSelectOption` so the caller
   *  can populate other fields from the same fetch. */
  data?: T
}

const DEBOUNCE_MS = 250

export function SearchableSelect<T = unknown>({
  value,
  onChange,
  options,
  loadOptions,
  onSelectOption,
  allowFreeText = false,
  placeholder,
  disabled,
  id,
  className,
  emptyMessage = 'No matches',
}: {
  value: string
  onChange: (value: string) => void
  options?: SearchableOption<T>[]
  loadOptions?: (query: string) => Promise<SearchableOption<T>[]>
  onSelectOption?: (option: SearchableOption<T>) => void
  allowFreeText?: boolean
  placeholder?: string
  disabled?: boolean
  id?: string
  className?: string
  emptyMessage?: string
}) {
  const reactId = useId()
  const listId = `${id ?? reactId}-listbox`

  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState(value ?? '')
  const [highlight, setHighlight] = useState(0)
  const [loaded, setLoaded] = useState<SearchableOption<T>[]>([])
  const [loading, setLoading] = useState(false)

  const wrapRef = useRef<HTMLDivElement>(null)
  const focusedRef = useRef(false)

  // Track the committed value while the user is not editing. Without this an
  // external reset (loading a saved record into the wizard) would leave the
  // box showing whatever was typed before.
  useEffect(() => {
    if (!focusedRef.current) setQuery(value ?? '')
  }, [value])

  // Async source. Only runs while the menu is open, so a form of twenty rows
  // does not fire twenty searches on mount.
  useEffect(() => {
    if (!loadOptions || !open) return

    let cancelled = false
    setLoading(true)

    const timer = setTimeout(() => {
      loadOptions(query)
        .then((res) => { if (!cancelled) setLoaded(res) })
        .catch(() => { if (!cancelled) setLoaded([]) })
        .finally(() => { if (!cancelled) setLoading(false) })
    }, DEBOUNCE_MS)

    return () => { cancelled = true; clearTimeout(timer) }
  }, [query, open, loadOptions])

  // A static list filters here; a loaded one was already filtered server-side.
  const visible = useMemo(() => {
    if (loadOptions) return loaded

    const needle = query.trim().toLowerCase()
    const all = options ?? []
    if (!needle) return all

    return all.filter((o) =>
      o.label.toLowerCase().includes(needle)
      || o.value.toLowerCase().includes(needle)
      || (o.hint ?? '').toLowerCase().includes(needle))
  }, [options, loadOptions, loaded, query])

  // Keep the highlight inside the list as it changes under the user.
  useEffect(() => { setHighlight(0) }, [query, open])

  const commit = useCallback((option: SearchableOption<T>) => {
    focusedRef.current = false
    setQuery(option.label)
    setOpen(false)
    onChange(option.value)
    onSelectOption?.(option)
  }, [onChange, onSelectOption])

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) { setOpen(true); return }
      if (visible.length === 0) return
      setHighlight((h) => {
        const next = e.key === 'ArrowDown' ? h + 1 : h - 1
        return (next + visible.length) % visible.length
      })
      return
    }

    if (e.key === 'Enter') {
      // Only swallow Enter when it is actually choosing something — otherwise
      // let it reach the form, which is what a user expects in a text field.
      if (open && visible[highlight]) {
        e.preventDefault()
        commit(visible[highlight])
      }
      return
    }

    if (e.key === 'Escape') {
      if (!open) return
      e.preventDefault()
      setOpen(false)
      if (!allowFreeText) setQuery(value ?? '')
    }
  }

  function handleBlur() {
    focusedRef.current = false
    setOpen(false)
    // A restricted field cannot keep half-typed text: put back whatever was
    // last actually committed.
    if (!allowFreeText) setQuery(value ?? '')
  }

  return (
    <div ref={wrapRef} className={cn('relative', className)}>
      <div className="relative">
        <Input
          id={id}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && visible[highlight] ? `${listId}-${highlight}` : undefined}
          autoComplete="off"
          disabled={disabled}
          placeholder={placeholder}
          value={query}
          className="pr-8"
          onFocus={() => { focusedRef.current = true; setOpen(true) }}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          onChange={(e) => {
            focusedRef.current = true
            setQuery(e.target.value)
            setOpen(true)
            // Free text is the value as it is typed; a restricted field only
            // changes when an option is actually chosen.
            if (allowFreeText) onChange(e.target.value)
          }}
        />
        <ChevronDown
          size={16}
          aria-hidden
          className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted"
        />
      </div>

      {open && !disabled && (
        <ul
          id={listId}
          role="listbox"
          // Keeps focus in the input, so blur never fires before the click
          // lands and closes the list out from under it.
          onMouseDown={(e) => e.preventDefault()}
          className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
        >
          {loading && visible.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">Searching…</li>
          )}

          {!loading && visible.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">{emptyMessage}</li>
          )}

          {visible.map((o, i) => (
            <li
              key={`${o.value}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === highlight}
              onMouseEnter={() => setHighlight(i)}
              onClick={() => commit(o)}
              className={cn(
                'flex cursor-pointer items-center justify-between gap-3 px-3 py-1.5 text-sm',
                i === highlight ? 'bg-canvas-alt text-ink' : 'text-ink',
              )}
            >
              <span className="truncate">{o.label}</span>
              {o.hint && <span className="shrink-0 truncate text-xs text-muted">{o.hint}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
