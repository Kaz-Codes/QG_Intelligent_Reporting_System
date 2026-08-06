import { useMemo, useState } from 'react'

/**
 * Small pagination primitive shared by the status-module lists. The Imports
 * list uses SortableTable (which embeds this), while the Logistics and Trucking
 * lists — which have custom section layouts — use the hook + component directly
 * on their own tables. Ten rows per page by default, with Prev/Next and a page
 * readout; page resets to 1 whenever the underlying row set changes length
 * (e.g. a filter narrows the results), so you never land on an empty page.
 */
export function usePagination<T>(rows: T[], pageSize = 10) {
  const [page, setPage] = useState(1)
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize))

  // Clamp when the data shrinks under the current page (filter applied, etc.).
  const safePage = Math.min(page, pageCount)
  if (safePage !== page) setPage(safePage)

  const pageRows = useMemo(
    () => rows.slice((safePage - 1) * pageSize, safePage * pageSize),
    [rows, safePage, pageSize],
  )

  return {
    page: safePage,
    pageCount,
    pageRows,
    setPage,
    total: rows.length,
    pageSize,
  }
}

interface PaginationProps {
  page: number
  pageCount: number
  total: number
  pageSize: number
  onPage: (page: number) => void
}

export function Pagination({ page, pageCount, total, pageSize, onPage }: PaginationProps) {
  if (total === 0) return null
  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)

  return (
    <div className="flex items-center justify-between gap-3 px-1 pt-2 text-sm text-muted">
      <span className="tabular-nums">
        {first}–{last} of {total}
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPage(page - 1)}
          disabled={page <= 1}
          className="rounded border border-line px-2.5 py-1 text-xs hover:border-muted disabled:opacity-40"
        >
          Prev
        </button>
        <span className="px-2 text-xs tabular-nums">
          Page {page} of {pageCount}
        </span>
        <button
          onClick={() => onPage(page + 1)}
          disabled={page >= pageCount}
          className="rounded border border-line px-2.5 py-1 text-xs hover:border-muted disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}


/**
 * Lightweight column sort for the custom-layout lists (Logistics, Trucking)
 * that don't use SortableTable. Give each sortable header a key and a value
 * accessor; clicking toggles asc/desc/none. Kept tiny and dependency-free so
 * the two lists can share it without adopting the whole SortableTable.
 */
export type SortDir = 'asc' | 'desc'

export function useSort<T>(rows: T[], accessors: Record<string, (row: T) => number | string>) {
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(null)

  const sorted = useMemo(() => {
    if (!sort) return rows
    const get = accessors[sort.key]
    if (!get) return rows
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = get(a)
      const bv = get(b)
      return av < bv ? -dir : av > bv ? dir : 0
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, sort])

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }))

  return { sorted, sort, toggle }
}

export function SortHeader({
  label, sortKey, sort, onToggle, align = 'left', className = '',
}: {
  label: string
  sortKey: string
  sort: { key: string; dir: SortDir } | null
  onToggle: (key: string) => void
  align?: 'left' | 'right'
  className?: string
}) {
  const active = sort?.key === sortKey
  return (
    <th
      onClick={() => onToggle(sortKey)}
      className={`cursor-pointer select-none whitespace-nowrap px-3 py-2 hover:text-ink ${align === 'right' ? 'text-right' : 'text-left'} ${className}`}
    >
      {label}
      <span className={`ml-1 ${active ? 'text-accent' : 'opacity-30'}`}>
        {active ? (sort!.dir === 'asc' ? '▲' : '▼') : '▲'}
      </span>
    </th>
  )
}
