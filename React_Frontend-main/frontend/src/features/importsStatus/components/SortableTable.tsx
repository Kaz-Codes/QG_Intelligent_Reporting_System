import { useState, type ReactNode, Fragment } from 'react'

/**
 * A sortable table for the Imports Status sheet.
 *
 * The shared DataTable has no sorting and colours the whole row from a status
 * column — right for the dashboard, not for a sheet where people sort by
 * slippage and value and want only the status *badge* coloured. Rather than
 * change the shared component (and risk the other developer's screens), this
 * lives in the feature and reuses the same Tailwind tokens so it still looks
 * like one product.
 */

export interface SortableColumn<T> {
  key: string
  label: string
  align?: 'left' | 'right'
  /** Cell contents. Falls back to String(row[key]) if omitted. */
  render?: (row: T) => ReactNode
  /** Comparable value for sorting. Omit to make the column unsortable. */
  sortValue?: (row: T) => number | string
  width?: number
}

interface Props<T> {
  columns: SortableColumn<T>[]
  rows: T[]
  /** Rows flagged here get a left accent bar — used for "information pending". */
  flagged?: (row: T) => boolean
  /** Extra classes per row. Used to strike through soft-deleted records, which
   *  share the list with live ones so their undo button stays reachable. */
  rowClassName?: (row: T) => string | undefined
  onRowClick?: (row: T) => void
  initialSort?: { key: string; dir: 'asc' | 'desc' }
  empty?: ReactNode
  maxHeight?: number
  /** Rows per page. Omit or 0 to disable pagination (show all). */
  pageSize?: number
  /**
   * Make rows single-click expandable. When provided, a click toggles an
   * expansion panel (spanning all columns) rendered by this function, instead
   * of firing onRowClick. Use rowKey to give each row a stable identity so the
   * open/closed state survives re-sorts and re-renders.
   */
  renderExpanded?: (row: T) => ReactNode
  rowKey?: (row: T) => string
  /**
   * Hand pagination to the caller — for a list whose rows come from the server
   * one page at a time. `rows` is then just the current page, and the footer
   * below drives the caller instead of slicing locally. Without this the table
   * pages whatever it was given, which would be a SECOND pager on top of the
   * server's.
   */
  serverPagination?: {
    page: number
    pageCount: number
    totalRows: number
    pageSize: number
    onPageChange: (page: number) => void
    loading?: boolean
  }
}

export function SortableTable<T>({
  columns, rows, flagged, rowClassName, onRowClick, initialSort, empty, maxHeight = 560, pageSize = 10,
  serverPagination, renderExpanded, rowKey,
}: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(initialSort ?? null)
  const [page, setPage] = useState(1)
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  const sorted = (() => {
    if (!sort) return rows
    const col = columns.find((c) => c.key === sort.key)
    if (!col?.sortValue) return rows
    const dir = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = col.sortValue!(a)
      const bv = col.sortValue!(b)
      return av < bv ? -dir : av > bv ? dir : 0
    })
  })()

  // Server-paged: show exactly what we were handed (sorted within the page)
  // and let the footer call back. Otherwise page locally; pageSize = 0
  // disables. The local page clamps when the row set shrinks.
  const serverPaged = !!serverPagination
  const paginate = serverPaged || pageSize > 0
  const pageCount = serverPaged
    ? Math.max(1, serverPagination.pageCount)
    : Math.max(1, Math.ceil(sorted.length / pageSize))
  const safePage = serverPaged ? serverPagination.page : (paginate ? Math.min(page, pageCount) : 1)
  if (!serverPaged && paginate && safePage !== page) setPage(safePage)
  const visible = serverPaged
    ? sorted
    : (paginate ? sorted.slice((safePage - 1) * pageSize, safePage * pageSize) : sorted)

  const totalRows = serverPaged ? serverPagination.totalRows : sorted.length
  const rowsPerPage = serverPaged ? serverPagination.pageSize : pageSize
  const goToPage = serverPaged ? serverPagination.onPageChange : setPage
  const pagerDisabled = serverPaged ? !!serverPagination.loading : false
  const showPager = serverPaged ? pageCount > 1 : (paginate && sorted.length > pageSize)
  const firstOnPage = totalRows === 0 ? 0 : (safePage - 1) * rowsPerPage + 1
  const lastOnPage = serverPaged
    ? Math.min((safePage - 1) * rowsPerPage + visible.length, totalRows)
    : Math.min(safePage * rowsPerPage, totalRows)

  const toggle = (key: string) => {
    const col = columns.find((c) => c.key === key)
    if (!col?.sortValue) return
    setSort((s) =>
      s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' },
    )
  }

  return (
    <div className="overflow-x-auto overflow-y-auto rounded-xl border border-line [scrollbar-width:auto]" style={{ maxHeight }}>
      <table className="w-full min-w-[960px] text-sm">
        <thead className="sticky top-0 z-10 bg-canvas-alt">
          <tr>
            {columns.map((col) => {
              const active = sort?.key === col.key
              const sortable = !!col.sortValue
              return (
                <th
                  key={col.key}
                  onClick={() => toggle(col.key)}
                  style={col.width ? { minWidth: col.width } : undefined}
                  className={[
                    'px-3 py-2 text-xs font-semibold text-muted whitespace-nowrap',
                    col.align === 'right' ? 'text-right' : 'text-left',
                    sortable ? 'cursor-pointer select-none hover:text-ink' : '',
                  ].join(' ')}
                >
                  {col.label}
                  {sortable && (
                    <span className={`ml-1 ${active ? 'text-accent' : 'opacity-30'}`}>
                      {active ? (sort!.dir === 'asc' ? '▲' : '▼') : '▲'}
                    </span>
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {visible.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-10 text-center text-muted">
                {empty ?? 'No rows match the current filter.'}
              </td>
            </tr>
          )}
          {visible.map((row, i) => {
            const key = rowKey ? rowKey(row) : String(i)
            const isOpen = expandedKey === key
            const clickable = renderExpanded || onRowClick
            const handleClick = renderExpanded
              ? () => setExpandedKey(isOpen ? null : key)
              : onRowClick
                ? () => onRowClick(row)
                : undefined
            return (
              <Fragment key={key}>
                <tr
                  onClick={handleClick}
                  aria-expanded={renderExpanded ? isOpen : undefined}
                  className={[
                    'border-t border-line align-top',
                    clickable ? 'cursor-pointer hover:bg-canvas-alt' : '',
                    flagged?.(row) ? 'shadow-[inset_3px_0_0_var(--color-warning)]' : '',
                    isOpen ? 'bg-canvas-alt' : '',
                    rowClassName?.(row) ?? '',
                  ].join(' ')}
                >
                  {columns.map((col, ci) => (
                    <td
                      key={col.key}
                      className={`px-3 py-2.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                    >
                      {ci === 0 && renderExpanded && (
                        <span className={`mr-1.5 inline-block text-[10px] text-muted transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                      )}
                      {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? '')}
                    </td>
                  ))}
                </tr>
                {renderExpanded && isOpen && (
                  <tr className="border-t border-line bg-canvas-alt/60">
                    <td colSpan={columns.length} className="px-3 py-3">
                      {renderExpanded(row)}
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
      {showPager && (
        <div className="flex items-center justify-between gap-3 border-t border-line px-3 py-2 text-sm text-muted">
          <span className="tabular-nums">
            {firstOnPage}–{lastOnPage} of {totalRows}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => goToPage(safePage - 1)} disabled={safePage <= 1 || pagerDisabled}
              className="rounded border border-line px-2.5 py-1 text-xs hover:border-muted disabled:opacity-40">Prev</button>
            <span className="px-2 text-xs tabular-nums">Page {safePage} of {pageCount}</span>
            <button onClick={() => goToPage(safePage + 1)} disabled={safePage >= pageCount || pagerDisabled}
              className="rounded border border-line px-2.5 py-1 text-xs hover:border-muted disabled:opacity-40">Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
