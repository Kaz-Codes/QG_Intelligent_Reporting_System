import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'
import type { ReportColumn } from './reportBuilder'
import type { ReportRow } from './api/reports'

/**
 * PDF is generated client-side because the backend has no PDF export endpoint
 * (only /reports/export, which streams .xlsx) — Excel downloads go straight
 * to that endpoint instead (see downloadReportExcel in lib/api/reports.ts).
 */
export function exportPdf(rows: ReportRow[], columns: ReportColumn[], filename: string, title: string, note?: string) {
  const doc = new jsPDF({ orientation: columns.length > 6 ? 'landscape' : 'portrait' })
  doc.setFontSize(13)
  doc.text(title, 14, 15)
  if (note) {
    doc.setFontSize(9)
    doc.setTextColor(140)
    doc.text(note, 14, 21)
    doc.setTextColor(0)
  }
  autoTable(doc, {
    head: [columns.map((c) => c.label)],
    body: rows.map((row) => columns.map((col) => col.text(row[col.key], row))),
    startY: note ? 26 : 20,
    styles: { fontSize: 7, cellPadding: 2 },
    headStyles: { fillColor: [15, 23, 42] },
  })
  doc.save(filename)
}
