import * as XLSX from 'xlsx'
import { jsPDF } from 'jspdf'
import autoTableImport from 'jspdf-autotable'

// jspdf-autotable v3 ships a CJS default export. Under Vite/esbuild's CJS
// interop the default import can arrive as the module namespace object
// ({ default: fn }) rather than the function itself, so `autoTable(doc, …)`
// throws "autoTable is not a function". Normalise to the callable either way.
const autoTable = ((autoTableImport as unknown as { default?: typeof autoTableImport }).default
  ?? autoTableImport) as typeof autoTableImport

/**
 * Shared export for the status-module lists (Imports / Logistics / Trucking).
 *
 * The three lists previously each hand-rolled a CSV blob and a window.print()
 * call — inconsistent, and neither a real spreadsheet nor a real PDF. This
 * reuses SheetJS + jsPDF + autotable so a list gets a genuine .xlsx (typed
 * cells, auto-fit columns, a frozen header row) and a genuine landscape .pdf
 * with a title block.
 *
 * A column is defined once; both exporters read the same definition, so the
 * spreadsheet and the PDF never drift apart.
 */
export interface ListColumn<T> {
  header: string
  /** Cell value. Return a number for numeric columns so Excel treats them as
   *  numbers (right-aligned, summable) rather than text. */
  value: (row: T) => string | number | null | undefined
}

function matrix<T>(rows: T[], columns: ListColumn<T>[]) {
  const head = columns.map((c) => c.header)
  const body = rows.map((r) => columns.map((c) => {
    const v = c.value(r)
    return v === null || v === undefined ? '' : v
  }))
  return { head, body }
}

export function exportListExcel<T>(
  rows: T[],
  columns: ListColumn<T>[],
  filename: string,
  sheetName = 'Sheet1',
) {
  const { head, body } = matrix(rows, columns)
  const sheet = XLSX.utils.aoa_to_sheet([head, ...body])

  // Auto-fit column widths to the longest cell in each column (capped so one
  // long free-text cell doesn't blow the layout out).
  sheet['!cols'] = columns.map((c, i) => {
    const longest = Math.max(
      c.header.length,
      ...body.map((r) => String(r[i] ?? '').length),
    )
    return { wch: Math.min(Math.max(longest + 2, 8), 48) }
  })
  // Freeze the header row.
  sheet['!freeze'] = { xSplit: 0, ySplit: 1 }
  ;(sheet as { '!autofilter'?: { ref: string } })['!autofilter'] = {
    ref: XLSX.utils.encode_range({ s: { r: 0, c: 0 }, e: { r: body.length, c: columns.length - 1 } }),
  }

  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, sheet, sheetName.slice(0, 31))
  XLSX.writeFile(wb, filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`)
}

export function exportListPdf<T>(
  rows: T[],
  columns: ListColumn<T>[],
  filename: string,
  title: string,
) {
  const { head, body } = matrix(rows, columns)
  const doc = new jsPDF({ orientation: columns.length > 6 ? 'landscape' : 'portrait' })

  doc.setFontSize(14)
  doc.text(title, 14, 15)
  doc.setFontSize(9)
  doc.setTextColor(120)
  doc.text(
    `${rows.length} record${rows.length === 1 ? '' : 's'} · generated ${new Date().toLocaleString()}`,
    14, 21,
  )
  doc.setTextColor(0)

  autoTable(doc, {
    head: [head],
    body: body.map((r) => r.map((c) => String(c))),
    startY: 26,
    styles: { fontSize: 7.5, cellPadding: 2, overflow: 'linebreak' },
    headStyles: { fillColor: [15, 23, 42], textColor: 255, fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [246, 247, 249] },
    margin: { left: 12, right: 12 },
  })

  doc.save(filename.endsWith('.pdf') ? filename : `${filename}.pdf`)
}
