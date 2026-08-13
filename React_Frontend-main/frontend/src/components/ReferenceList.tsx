import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { List, ChevronLeft, ChevronRight, Loader2, Search, X } from 'lucide-react'

/**
 * "Which records is this number about?"
 *
 * A headline count cannot be checked or acted on by itself — "19 delayed" gives
 * nobody anything to chase. This puts the actual references one click away, so
 * a figure on a dashboard leads to the payment reference, GD number and works
 * you need to go and look the consignment up.
 *
 * THE LIST IS COMPLETE. There is no cap: `total` is always the true number of
 * records behind the figure, and every one of them is reachable by paging. A
 * truncated list quietly changes the question from "which records is this
 * about" to "which did we feel like showing", and the reader cannot tell the
 * difference. What is NOT complete is the payload — the dashboard ships page
 * one, and `fetchPage` pulls the rest on demand, because local procurement
 * alone stands over 8,731 orders (1.3 MB) on a screen that reloads whenever a
 * filter moves.
 *
 * THE LIST NEVER HIDES LINES. Where a record has lines under it, the rows ARE
 * the lines: a consignment carrying three shaft rows shows as three rows, each
 * with its own arrival date and value. Folding them up looks tidy and destroys
 * the only view that explains the number — it was exactly this that let payment
 * ref 65704 show one row for seven lines arriving in two different months.
 *
 * So `total` (lines) and the KPI it opened from (consignments) legitimately
 * differ, and the header says so: "3 lines across 1 consignment". What is not
 * allowed is a list that quietly reports a different number with nothing saying
 * why — the Delayed tile reading 247 over a list reading 454.
 *
 * Portalled and positioned for the same reason MetricInfo is: KpiCard is
 * `overflow-hidden` for its rounded corners and coloured edge, which would clip
 * a panel rendered inside it.
 *
 * Click, not hover: this is a list you read and page through, so it stays open
 * until dismissed rather than vanishing when the pointer moves onto it.
 */

/**
 * One record behind a figure, in a shape general enough for any of them:
 * an import consignment keyed on its payment reference, a purchase LINE keyed
 * on its PO, a stock item keyed on its code. Deliberately not typed per source
 * — one component, one layout, so a reference list reads the same wherever it
 * is opened.
 */
export interface ReferenceItem {
  id: number | string
  /** The number somebody would look this up by: PO, payment ref, GD, item code. */
  reference: string
  /** What it is — the item on the line, usually. */
  detail?: string | null
  /** Secondary context: supplier, works, status. */
  meta?: string | null
  /** The figure that put this record in the list ("238 days late"). */
  badge?: string | null
}

/** One page of a complete list. `total` is never truncated.
 *
 *  A LIST NEVER HIDES LINES. Where a record has lines under it, the rows ARE
 *  the lines — a consignment with three shaft rows is three rows. So `total`
 *  (lines) and the KPI it opened from (consignments) legitimately differ, and
 *  `unit` / `groups` are what keep that honest: the header reads "3 lines
 *  across 1 consignment" rather than a bare number that contradicts the tile. */
export interface ReferenceSet {
  total: number
  /** What a row IS — "line", "consignment", "order", "item". */
  unit?: string
  /** How many parents those rows belong to; null when rows are the parent. */
  groups?: number | null
  group_unit?: string | null
  page: number
  page_size: number
  pages: number
  items: ReferenceItem[]
}

/** "3 lines" / "1 consignment" — pluralised once, in one place. */
function countOf(n: number, noun = 'record'): string {
  return `${n.toLocaleString()} ${noun}${n === 1 ? '' : 's'}`
}

/** The same "search the rendered text" rule as the backend's `matches_search`
 *  (app/dashboard/references.py) — used only as a fallback for a list with no
 *  `fetchPage`, where there is no server round trip to filter on instead. */
function matchesLocally(item: ReferenceItem, term: string): boolean {
  const haystack = [item.reference, item.detail, item.meta, item.badge]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(term)
}

const SEARCH_DEBOUNCE_MS = 300

/** Fetches another page of the same list, optionally narrowed to rows whose
 *  visible text contains `search`. Omit `search` (or pass '') for the
 *  unfiltered list. Pagers that can't page still take the search box's
 *  input, they just never see a `page` above 1. */
export type ReferencePager = (page: number, search?: string) => Promise<ReferenceSet>

const PANEL_WIDTH = 360
const GAP = 8
const MARGIN = 8

export function ReferenceList({
  label, refs, fetchPage,
}: {
  label: string
  refs?: ReferenceSet
  fetchPage?: ReferencePager
}) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const [current, setCurrent] = useState<ReferenceSet | undefined>(refs)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const id = useId()

  // Always the latest `fetchPage`, read from inside the debounce timer below —
  // a ref so the effect can key off `search` alone and not re-fire every time
  // a parent re-render hands this component a new pager closure for the same
  // list (Inventory's `pager(key)` builds one fresh on every render).
  const fetchPageRef = useRef(fetchPage)
  useEffect(() => { fetchPageRef.current = fetchPage })

  // A filter change replaces the figure, so it replaces the list under it too
  // — otherwise the panel would keep showing page 4, or a stale search term,
  // from a completely different query.
  useEffect(() => { setCurrent(refs); setSearch('') }, [refs])

  // Skips the debounce fetch that would otherwise fire once on mount (and once
  // after every filter-driven reset above) even though `search` is still ''.
  const searchMounted = useRef(false)
  useEffect(() => {
    const pager = fetchPageRef.current
    if (!pager) return
    if (!searchMounted.current) { searchMounted.current = true; return }

    const timer = setTimeout(async () => {
      setLoading(true)
      try {
        setCurrent(await pager(1, search))
        listRef.current?.scrollTo({ top: 0 })
      } finally {
        setLoading(false)
      }
    }, SEARCH_DEBOUNCE_MS)

    return () => clearTimeout(timer)
  }, [search])

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

  const goTo = useCallback(async (page: number) => {
    if (!fetchPage || !current || page < 1 || page > current.pages) return
    setLoading(true)
    try {
      setCurrent(await fetchPage(page, search))
      // Back to the top: page 5 opened halfway down reads as a broken scroll.
      listRef.current?.scrollTo({ top: 0 })
    } finally {
      setLoading(false)
    }
  }, [fetchPage, current, search])

  // Nothing behind the number means nothing to show.
  if (!current || current.total === 0) return null

  const { page, pages, total } = current
  const unit = current.unit ?? 'record'
  const groups = current.groups
  const groupUnit = current.group_unit
  // Without a pager we can only ever show what we were handed.
  const canPage = Boolean(fetchPage) && pages > 1
  const first = (page - 1) * current.page_size + 1
  const last = Math.min(page * current.page_size, total)

  // With a pager, every search term is already resolved server-side — `items`
  // IS the matching set. Without one, there is no round trip to filter with,
  // so the search box narrows what was already loaded instead; `total`/`page`
  // keep describing the loaded set, not the (unknowable from here) full one.
  const term = search.trim().toLowerCase()
  const localFilter = !fetchPage && term.length > 0
  const items = localFilter ? current.items.filter((it) => matchesLocally(it, term)) : current.items

  return (
    <span className="relative inline-flex">
      <button
        ref={triggerRef}
        type="button"
        aria-label={`Show the ${countOf(total, unit)} behind ${label}`}
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
              {/* The true total, always — and where in it you are. */}
              {pages > 1
                ? `${first.toLocaleString()}–${last.toLocaleString()} of ${countOf(total, unit)}`
                : countOf(total, unit)}
            </p>
          </div>

          {/* Says plainly that the rows are LINES and how many parents they
              belong to, so the tile's own count stays reconcilable with the
              list instead of merely differing from it. Skipped while
              local-filtering: `groups` still describes the loaded set, not
              the narrowed one, and restating it here would misquote it. */}
          {!localFilter && groups != null && groupUnit && (
            <p className="border-b border-line bg-brand-soft/40 px-3 py-1.5 text-[11px] text-muted">
              {countOf(total, unit)} across {countOf(groups, groupUnit)}
            </p>
          )}

          <div className="relative border-b border-line px-2 py-1.5">
            <Search size={12} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
            <input
              ref={searchInputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search ${unit}s…`}
              aria-label={`Search the ${label} list`}
              className="w-full rounded border border-line bg-canvas py-1 pl-6 pr-6 text-[11px] text-ink outline-none placeholder:text-muted focus:border-brand/60"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch('')}
                aria-label="Clear search"
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
              >
                <X size={12} />
              </button>
            )}
          </div>

          <div ref={listRef} className="relative max-h-72 overflow-y-auto">
            {loading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-surface/70">
                <Loader2 size={16} className="animate-spin text-muted" />
              </div>
            )}
            {items.length === 0 && (
              <p className="px-3 py-4 text-center text-[11px] text-muted">
                No {unit}s match "{search.trim()}".
              </p>
            )}
            {items.map((r) => (
              <div key={r.id} className="border-b border-line px-3 py-2 last:border-b-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-xs font-semibold text-ink">{r.reference}</span>
                  {r.badge && (
                    <span className="shrink-0 text-[11px] font-medium text-muted">{r.badge}</span>
                  )}
                </div>
                {r.detail && <p className="mt-0.5 truncate text-xs text-ink">{r.detail}</p>}
                <p className="mt-0.5 truncate text-[11px] text-muted">{r.meta || '—'}</p>
              </div>
            ))}
          </div>

          {localFilter && (
            <p className="border-t border-line px-3 py-1.5 text-[11px] text-muted">
              {items.length.toLocaleString()} match{items.length === 1 ? '' : 'es'} in the{' '}
              {total.toLocaleString()} loaded {unit}{total === 1 ? '' : 's'} — this list can't
              fetch further pages to search.
            </p>
          )}

          {canPage && (
            <div className="flex items-center justify-between border-t border-line px-2 py-1.5">
              <button
                type="button"
                disabled={page <= 1 || loading}
                onClick={() => goTo(page - 1)}
                className="inline-flex h-6 items-center gap-0.5 rounded px-1.5 text-[11px] text-muted transition-colors hover:text-ink disabled:pointer-events-none disabled:opacity-40"
              >
                <ChevronLeft size={12} /> Prev
              </button>
              <span className="text-[11px] text-muted">
                Page {page.toLocaleString()} of {pages.toLocaleString()}
              </span>
              <button
                type="button"
                disabled={page >= pages || loading}
                onClick={() => goTo(page + 1)}
                className="inline-flex h-6 items-center gap-0.5 rounded px-1.5 text-[11px] text-muted transition-colors hover:text-ink disabled:pointer-events-none disabled:opacity-40"
              >
                Next <ChevronRight size={12} />
              </button>
            </div>
          )}

          {/* A list we cannot page through says so, rather than looking complete.
              Suppressed while local-filtering — the paragraph above already
              covers it, and both at once would say the same thing twice. */}
          {!canPage && !localFilter && pages > 1 && (
            <p className="border-t border-line px-3 py-1.5 text-[11px] text-muted">
              Showing the first {items.length} of {total.toLocaleString()}.
            </p>
          )}
        </div>,
        document.body,
      )}
    </span>
  )
}
