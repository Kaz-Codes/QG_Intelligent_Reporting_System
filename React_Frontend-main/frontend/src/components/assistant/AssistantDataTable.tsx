import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Download, GripVertical, Sheet } from 'lucide-react'

// Renders the rows behind an assistant answer as a real, interactive table:
// click a header to sort, drag a header's grip to reorder columns, search
// globally or within one column, and page through the result. Export what's
// currently shown (after filtering/sorting/reordering) as CSV or a real .xlsx.
//
// PAGED, NOT SCROLLED. Every row the backend returns is still here — sorting,
// searching and export all see the complete result — but only one page of them
// is ever in the DOM. A 3,000-row answer used to mean 3,000 <tr> elements,
// which is what made the page lag; now it means 20, and the cost of rendering
// an answer no longer depends on how big the answer is.
//
// Deliberately separate from the app's own <DataTable> (components/DataTable.tsx),
// which renders a fixed, page-defined column set — an assistant answer's
// columns are only known at reply time and need sort/search/export the fixed
// dashboards don't. Same visual language (border-line, canvas-alt header,
// odd-row zebra) so it still reads as part of this app.

const INTERNAL_EXACT = new Set([
  'id',
  'is_deleted',
  'deleted_at',
  'deleted_by_id',
  'created_at',
  'updated_at',
  'created_by_id',
  'record_state',
  'is_locked',
])

const isInternalColumn = (c: string): boolean => {
  const k = c.toLowerCase()
  if (k.endsWith('_id') && k !== 'item_id_code') return true
  return INTERNAL_EXACT.has(k)
}

// Domain shorthand Title Case would mangle: "Etd" and "Uom" read as typos.
const ABBREV: Record<string, string> = {
  etd: 'ETD', eta: 'ETA', uom: 'UoM', po: 'PO', lc: 'LC', mo: 'MO', hs: 'HS',
  gd: 'GD', elc: 'ELC', alc: 'ALC', rfd: 'RFD', gin: 'GIN', qty: 'Qty',
  no: 'No.', ref: 'Ref', pkr: 'PKR', id: 'ID',
}

// snake_case -> a heading a person can read: "arrival_or_eta_date" ->
// "Arrival or ETA Date". Purely cosmetic; the underlying keys are untouched.
function prettyLabel(column: string): string {
  return column
    .split('_')
    .filter(Boolean)
    .map((word) => {
      const lower = word.toLowerCase()
      if (ABBREV[lower]) return ABBREV[lower]
      if (lower === 'or' || lower === 'of' || lower === 'and') return lower
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(' ')
    .replace(/^./, (c) => c.toUpperCase())
}

function looksNumeric(value: unknown): boolean {
  if (typeof value === 'number') return true
  if (typeof value === 'string') return value.trim() !== '' && !isNaN(Number(value))
  return false
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return value.toLocaleString(undefined, { maximumFractionDigits: 4 })
  if (Array.isArray(value)) {
    if (value.every((v) => v === null || typeof v !== 'object')) {
      return value.map((v) => (v === null ? '—' : String(v))).join(', ')
    }
    return JSON.stringify(value)
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function toExportValue(value: unknown): string | number {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return value
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

function toCsv(columns: string[], rows: Record<string, unknown>[]): string {
  const escape = (v: unknown) => {
    let s: string
    if (v === null || v === undefined) s = ''
    else if (typeof v === 'object') s = JSON.stringify(v)
    else s = String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const header = columns.map((c) => escape(prettyLabel(c))).join(',')
  const body = rows.map((r) => columns.map((c) => escape(r[c])).join(',')).join('\n')
  return `${header}\n${body}`
}

// One screenful. Small enough that a page renders instantly however large the
// underlying result is.
const PAGE_SIZE = 20

interface Props {
  columns?: string[]
  rows: Record<string, unknown>[]
}

export function AssistantDataTable({ columns, rows }: Props) {
  const [sort, setSort] = useState<{ column: string | null; dir: 1 | -1 }>({ column: null, dir: 1 })
  const [query, setQuery] = useState('')
  const [colFilters, setColFilters] = useState<Record<string, string>>({})
  const [exporting, setExporting] = useState(false)
  const dragColRef = useRef<string | null>(null)

  const cols = useMemo(() => {
    const all = columns && columns.length ? columns : rows.length ? Object.keys(rows[0]) : []
    const meaningful = all.filter((c) => !isInternalColumn(c))
    return meaningful.length ? meaningful : all
  }, [columns, rows])

  const [colOrder, setColOrder] = useState<string[]>(cols)
  const order = colOrder.length === cols.length ? colOrder : cols

  const filteredRows = useMemo(() => {
    const q = query.trim().toLowerCase()
    const activeColFilters = Object.entries(colFilters)
      .map(([c, v]) => [c, v.trim().toLowerCase()] as const)
      .filter(([, v]) => v)

    if (!q && activeColFilters.length === 0) return rows

    return rows.filter((r) => {
      if (q && !cols.some((c) => formatCell(r[c]).toLowerCase().includes(q))) return false
      return activeColFilters.every(([c, v]) => formatCell(r[c]).toLowerCase().includes(v))
    })
  }, [rows, cols, query, colFilters])

  const visibleRows = useMemo(() => {
    if (!sort.column) return filteredRows
    const column = sort.column
    const numeric = filteredRows.every((r) => r[column] == null || looksNumeric(r[column]))
    return [...filteredRows].sort((a, b) => {
      const av = a[column]
      const bv = b[column]
      if (av == null) return 1
      if (bv == null) return -1
      const cmp = numeric ? Number(av) - Number(bv) : String(av).localeCompare(String(bv))
      return cmp * sort.dir
    })
  }, [filteredRows, sort])

  const [page, setPage] = useState(1)
  const scrollRef = useRef<HTMLDivElement>(null)

  const pageCount = Math.max(1, Math.ceil(visibleRows.length / PAGE_SIZE))
  // Clamped rather than trusted: filtering can shrink the result under the
  // page the user is on, and page 7 of 2 would render as empty.
  const safePage = Math.min(page, pageCount)
  const firstRow = (safePage - 1) * PAGE_SIZE
  const pageRows = visibleRows.slice(firstRow, firstRow + PAGE_SIZE)

  // Any change to what's being shown starts again from the first page —
  // staying on page 12 of a search the user just narrowed reads as no results.
  useEffect(() => {
    setPage(1)
  }, [query, colFilters, sort, rows])

  const goToPage = (next: number) => {
    setPage(Math.min(Math.max(next, 1), pageCount))
    scrollRef.current?.scrollTo({ top: 0 })
  }

  if (!rows.length || !cols.length) return null

  const toggleSort = (column: string) =>
    setSort((prev) => (prev.column === column ? { column, dir: (-prev.dir as 1 | -1) } : { column, dir: 1 }))

  const handleDragStart = (col: string) => (e: React.DragEvent) => {
    dragColRef.current = col
    e.dataTransfer.effectAllowed = 'move'
  }
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }
  const handleDrop = (targetCol: string) => (e: React.DragEvent) => {
    e.preventDefault()
    const source = dragColRef.current
    dragColRef.current = null
    if (!source || source === targetCol) return
    setColOrder((prev) => {
      const next = prev.filter((c) => c !== source)
      next.splice(next.indexOf(targetCol), 0, source)
      return next
    })
  }

  const downloadCsv = () => {
    const blob = new Blob([toCsv(order, visibleRows)], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'assistant-data.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  const downloadExcel = async () => {
    setExporting(true)
    try {
      const XLSX = await import('xlsx')
      const sheetRows = visibleRows.map((r) => {
        const obj: Record<string, string | number> = {}
        order.forEach((c) => {
          obj[prettyLabel(c)] = toExportValue(r[c])
        })
        return obj
      })
      const sheet = XLSX.utils.json_to_sheet(sheetRows, { header: order.map(prettyLabel) })
      const workbook = XLSX.utils.book_new()
      XLSX.utils.book_append_sheet(workbook, sheet, 'Data')
      XLSX.writeFile(workbook, 'assistant-data.xlsx')
    } finally {
      setExporting(false)
    }
  }

  const filtering = query.trim() !== '' || Object.values(colFilters).some((v) => v.trim())

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3 py-2">
        {/* Which rows these are, not just how many — with a page showing 20 of
            3,000, "3,000 rows" alone leaves the user unsure what they're
            looking at. */}
        <span className="text-xs text-muted">
          {visibleRows.length > 0 && (
            <>
              {(firstRow + 1).toLocaleString()}–{Math.min(firstRow + PAGE_SIZE, visibleRows.length).toLocaleString()} of{' '}
            </>
          )}
          {visibleRows.length.toLocaleString()}
          {filtering ? ` of ${rows.length.toLocaleString()} rows` : ` row${visibleRows.length === 1 ? '' : 's'}`}
        </span>
        <div className="flex items-center gap-2">
          {rows.length > 5 && (
            <input
              type="text"
              placeholder="Search all…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-36 rounded-lg border border-line bg-canvas px-2 py-1 text-xs text-ink outline-none placeholder:text-muted focus:border-brand-light sm:w-48"
            />
          )}
          <button
            onClick={downloadCsv}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-canvas-alt hover:text-ink"
          >
            <Download size={12} /> CSV
          </button>
          <button
            onClick={downloadExcel}
            disabled={exporting}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-canvas-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Sheet size={12} /> {exporting ? '…' : 'Excel'}
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="max-h-[380px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-canvas-alt">
            <tr>
              {order.map((c) => (
                <th key={c} onDragOver={handleDragOver} onDrop={handleDrop(c)} className="whitespace-nowrap px-3 py-2 text-left">
                  <span className="flex items-center gap-1">
                    <span
                      draggable
                      onDragStart={handleDragStart(c)}
                      title="Drag to reorder column"
                      className="cursor-grab text-muted/60 active:cursor-grabbing"
                    >
                      <GripVertical size={12} />
                    </span>
                    <span
                      onClick={() => toggleSort(c)}
                      title={`Click to sort — ${c}`}
                      className="flex cursor-pointer items-center gap-1 text-xs font-semibold text-muted hover:text-ink"
                    >
                      {prettyLabel(c)}
                      {sort.column === c && (sort.dir === 1 ? <ArrowUp size={11} /> : <ArrowDown size={11} />)}
                    </span>
                  </span>
                </th>
              ))}
            </tr>
            <tr>
              {order.map((c) => (
                <th key={c} className="px-3 pb-2">
                  <input
                    type="text"
                    placeholder="Search…"
                    value={colFilters[c] || ''}
                    onChange={(e) => setColFilters((prev) => ({ ...prev, [c]: e.target.value }))}
                    className="w-full rounded-md border border-line bg-canvas px-1.5 py-0.5 text-[11px] font-normal text-ink outline-none placeholder:text-muted focus:border-brand-light"
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row, i) => (
              <tr key={firstRow + i} className="odd:bg-canvas">
                {order.map((c) => (
                  <td
                    key={c}
                    className={`whitespace-nowrap px-3 py-2 ${looksNumeric(row[c]) ? 'text-right tabular-nums' : 'text-left'}`}
                  >
                    {formatCell(row[c])}
                  </td>
                ))}
              </tr>
            ))}
            {visibleRows.length === 0 && (
              <tr>
                <td colSpan={order.length} className="px-3 py-6 text-center text-muted">
                  No rows match the current search.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-between gap-2 border-t border-line px-3 py-2">
          <button
            onClick={() => goToPage(safePage - 1)}
            disabled={safePage === 1}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-canvas-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            <ArrowLeft size={12} /> Prev
          </button>
          <span className="text-xs tabular-nums text-muted">
            Page {safePage.toLocaleString()} of {pageCount.toLocaleString()}
          </span>
          <button
            onClick={() => goToPage(safePage + 1)}
            disabled={safePage === pageCount}
            className="inline-flex items-center gap-1 rounded-lg border border-line px-2 py-1 text-xs font-medium text-muted transition-colors hover:bg-canvas-alt hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            Next <ArrowRight size={12} />
          </button>
        </div>
      )}
    </div>
  )
}
