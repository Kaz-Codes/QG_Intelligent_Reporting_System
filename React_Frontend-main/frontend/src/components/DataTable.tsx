import type { ReactNode } from 'react'
import { useTheme } from '@/theme/ThemeContext'
import { statusColors } from '@/theme/tokens'

export interface Column {
  key: string
  label: string
  render?: (row: Record<string, unknown>) => ReactNode
  align?: 'left' | 'right'
}

interface Props {
  columns: Column[]
  /** Optional so a caller passing data that hasn't arrived (or that an
   * endpoint no longer returns) renders the empty state instead of throwing
   * on `.length` — a crash here unmounts the whole app, since a single
   * missing prop shouldn't be able to blank the page. */
  rows?: Record<string, unknown>[]
  /** Column whose value colors the whole row, same as the old
   * ui.styled_table(status_col=...). */
  statusColumn?: string
  height?: number
  /** Shown when there are no rows. Defaults to the "filtered everything out"
   * wording, which is wrong when the rows were never fetched at all. */
  emptyMessage?: string
}

export function DataTable({
  columns,
  rows = [],
  statusColumn,
  height = 380,
  emptyMessage = 'No rows match the current filter.',
}: Props) {
  const { colors } = useTheme()

  return (
    <div className="overflow-auto rounded-xl border border-line" style={{ maxHeight: height }}>
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-canvas-alt">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-3 py-2 text-xs font-semibold text-muted ${col.align === 'right' ? 'text-right' : 'text-left'}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                {emptyMessage}
              </td>
            </tr>
          )}
          {rows.map((row, i) => {
            const [fg, bg] = statusColumn
              ? statusColors(String(row[statusColumn] ?? ''), colors)
              : [colors.ink, undefined]
            return (
              <tr
                key={i}
                style={statusColumn ? { backgroundColor: bg, color: fg } : undefined}
                className={!statusColumn ? 'odd:bg-canvas' : undefined}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`whitespace-nowrap px-3 py-2 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                  >
                    {col.render ? col.render(row) : String(row[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}