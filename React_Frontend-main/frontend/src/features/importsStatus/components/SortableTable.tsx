import { useState, type ReactNode } from 'react'

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
  onRowClick?: (row: T) => void
  initialSort?: { key: string; dir: 'asc' | 'desc' }
  empty?: ReactNode
  maxHeight?: number
}

export function SortableTable<T>({
  columns, rows, flagged, onRowClick, initialSort, empty, maxHeight = 560,
}: Props<T>) {
  const [sort, setSort] = useState<{ key: string; dir: 'asc' | 'desc' } | null>(initialSort ?? null)

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

  const toggle = (key: string) => {
    const col = columns.find((c) => c.key === key)
    if (!col?.sortValue) return
    setSort((s) =>
      s?.key === key ? { key, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' },
    )
  }

  return (
    <div className="overflow-auto rounded-xl border border-line" style={{ maxHeight }}>
      <table className="w-full text-sm">
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
          {sorted.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-10 text-center text-muted">
                {empty ?? 'No rows match the current filter.'}
              </td>
            </tr>
          )}
          {sorted.map((row, i) => (
            <tr
              key={i}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={[
                'border-t border-line align-top',
                onRowClick ? 'cursor-pointer hover:bg-canvas-alt' : '',
                flagged?.(row) ? 'shadow-[inset_3px_0_0_var(--color-warning)]' : '',
              ].join(' ')}
            >
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`px-3 py-2.5 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                >
                  {col.render ? col.render(row) : String((row as Record<string, unknown>)[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
