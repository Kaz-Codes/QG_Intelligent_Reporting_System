import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, FileText, Save, Trash2, Pencil, Eye, EyeOff, X, Database, Inbox, ListChecks } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { SegmentedControl } from '@/components/SegmentedControl'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { ColumnPicker } from '@/components/ColumnPicker'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { DataTable, type Column } from '@/components/DataTable'
import { Pagination } from '@/components/Pagination'
import { LiveDataState } from '@/components/LiveDataState'
import { useAuth } from '@/features/auth/AuthContext'
import { ApiError } from '@/lib/api/auth'
import { useDebounced } from '@/lib/useDebounced'
import {
  REPORT_TYPES, type ReportType, type ReportRow, type ReportFilters, type SavedReport, type SavedReportInput,
  downloadReportExcel, fetchReportRowsForExport,
  createSavedReport, updateSavedReport, deleteSavedReport,
} from '@/lib/api/reports'
import { useReportOptions, useReportData, useSavedReports } from '@/lib/api/useReports'
import { type ReportColumn, unionColumns } from '@/lib/reportBuilder'
import { exportPdf } from '@/lib/reportExport'

const VIEWS = [
  { value: 'build', label: 'Build Report' },
  { value: 'saved', label: 'Saved Reports' },
] as const

const PAGE_SIZE = 25

function slugify(name: string): string {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'report'
}

function toTableColumns(cols: ReportColumn[]): Column[] {
  return cols.map((col) => ({
    key: col.key,
    label: col.label,
    align: col.align,
    render: (row) => col.render(row[col.key], row as ReportRow),
  }))
}

function savedReportFilters(r: SavedReport): ReportFilters {
  return { types: r.types, item: r.filters.item, shaft: r.filters.shaft, supplier: r.filters.supplier, branch: r.filters.branch, category: r.filters.category }
}

export function Reports() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [view, setView] = useState<(typeof VIEWS)[number]['value']>('build')

  const [types, setTypes] = useState<ReportType[]>(['purchases'])
  const [item, setItem] = useState<string[]>([])
  const [shaft, setShaft] = useState<string[]>([])
  const [supplier, setSupplier] = useState<string[]>([])
  const [branch, setBranch] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [saveName, setSaveName] = useState('')
  const [saveMessage, setSaveMessage] = useState('')
  const [exportingPdf, setExportingPdf] = useState(false)
  const [actionError, setActionError] = useState('')
  // Set while editing an existing saved report (loaded via SavedReportsView's
  // Edit button) instead of building a fresh one — swaps "Save as Report"
  // for "Update Report" and lets Save-as-New branch off it explicitly.
  const [editingId, setEditingId] = useState<number | null>(null)

  const debouncedSearch = useDebounced(search)
  const hasTypes = types.length > 0

  const { data: options } = useReportOptions(types, hasTypes)
  const availableColumns = useMemo(() => unionColumns(types), [types])

  // "Select data → see every header those types have → pick which ones to
  // keep": the column checklist normally starts fully checked against
  // whatever the current type selection makes available, and resets to
  // fully checked again whenever that type selection changes — except right
  // after loadReportIntoBuilder sets an explicit saved column set, which
  // this guard lets through untouched for exactly one effect run.
  const skipColumnResetRef = useRef(false)
  const [selectedColumns, setSelectedColumns] = useState<string[]>(() => availableColumns.map((c) => c.key))
  useEffect(() => {
    if (skipColumnResetRef.current) {
      skipColumnResetRef.current = false
      return
    }
    setSelectedColumns(availableColumns.map((c) => c.key))
  }, [availableColumns])

  // Item Name and Shaft are two lenses onto the same underlying `item`
  // field — the backend keeps its curated shaft list separate from the
  // general item list, so this just keeps the general list from also
  // offering the four shaft names a second time.
  const itemOptions = useMemo(
    () => (options?.items ?? []).filter((i) => !(options?.shafts ?? []).includes(i)),
    [options],
  )
  const shaftOptions = options?.shafts ?? []
  const supplierOptions = options?.suppliers ?? []
  const branchOptions = options?.branches ?? []
  const categoryOptions = options?.categories ?? []

  const filters: ReportFilters = useMemo(
    () => ({
      types, item, shaft, supplier, branch, category,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
      search: debouncedSearch.trim() || undefined,
    }),
    [types, item, shaft, supplier, branch, category, dateFrom, dateTo, debouncedSearch],
  )

  // Any filter change can shift the result set out from under the current
  // page (e.g. page 5 of 5 collapsing to 2 pages) — reset to page 1 rather
  // than risk landing on an empty page.
  useEffect(() => {
    setPage(1)
  }, [filters])

  const { data, isLoading, isError, error } = useReportData(filters, page, PAGE_SIZE, hasTypes)
  const pagination = data?.pagination

  const visibleColumns = useMemo(
    () => availableColumns.filter((c) => selectedColumns.includes(c.key)),
    [availableColumns, selectedColumns],
  )

  const tableColumns = useMemo(() => toTableColumns(visibleColumns), [visibleColumns])

  const typeLabels = types.map((t) => REPORT_TYPES.find((r) => r.value === t)!.label)
  const stamp = new Date().toISOString().slice(0, 10)
  const fileBase = `qg-irs-report-${types.join('-') || 'empty'}-${stamp}`

  function resetBuilder() {
    setEditingId(null)
    setSaveName('')
    setSaveMessage('')
  }

  function loadReportIntoBuilder(report: SavedReport) {
    skipColumnResetRef.current = true
    setTypes(report.types)
    setSelectedColumns(report.columns)
    setItem(report.filters.item ?? [])
    setShaft(report.filters.shaft ?? [])
    setSupplier(report.filters.supplier ?? [])
    setBranch(report.filters.branch ?? [])
    setCategory(report.filters.category ?? [])
    setEditingId(report.id)
    setSaveName(report.name)
    setSaveMessage('')
    setView('build')
  }

  async function saveReport(targetId: number | null) {
    if (!user || !saveName.trim() || types.length === 0 || selectedColumns.length === 0) return
    const input: SavedReportInput = {
      name: saveName.trim(), types, columns: selectedColumns,
      filters: { item, shaft, supplier, branch, category },
    }
    try {
      if (targetId) {
        await updateSavedReport(targetId, input)
        setSaveMessage(`Updated "${saveName.trim()}".`)
      } else {
        await createSavedReport(input)
        setEditingId(null)
        setSaveMessage(`Saved as "${saveName.trim()}" — see it under Saved Reports.`)
      }
      queryClient.invalidateQueries({ queryKey: ['saved-reports'] })
    } catch (e) {
      setSaveMessage(e instanceof ApiError ? e.message : 'Could not save — is the backend reachable?')
    }
  }

  function handleSave() {
    saveReport(editingId)
  }

  function handleSaveAsNew() {
    saveReport(null)
  }

  async function handleDeleteSaved(id: number) {
    setActionError('')
    try {
      await deleteSavedReport(id)
      queryClient.invalidateQueries({ queryKey: ['saved-reports'] })
      if (editingId === id) resetBuilder()
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Could not delete — is the backend reachable?')
    }
  }

  async function handleExportExcel() {
    setActionError('')
    try {
      await downloadReportExcel(filters, visibleColumns.map((c) => c.key), `${fileBase}.xlsx`)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Export failed — is the backend reachable?')
    }
  }

  async function handleExportPdf() {
    setActionError('')
    setExportingPdf(true)
    try {
      const { rows: exportRows, truncated, total } = await fetchReportRowsForExport(filters)
      const note = truncated
        ? `Showing the first ${exportRows.length.toLocaleString()} of ${total.toLocaleString()} records.`
        : undefined
      exportPdf(exportRows, visibleColumns, `${fileBase}.pdf`, 'QG-IRS Report', note)
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Export failed — is the backend reachable?')
    } finally {
      setExportingPdf(false)
    }
  }

  async function handleDownloadSaved(report: SavedReport, format: 'xlsx' | 'pdf') {
    setActionError('')
    const savedFilters = savedReportFilters(report)
    const today = new Date().toISOString().slice(0, 10)
    const base = `qg-irs-${slugify(report.name)}-${today}`
    try {
      if (format === 'xlsx') {
        await downloadReportExcel(savedFilters, report.columns, `${base}.xlsx`)
      } else {
        const cols = unionColumns(report.types).filter((c) => report.columns.includes(c.key))
        const { rows: exportRows, truncated, total } = await fetchReportRowsForExport(savedFilters)
        const note = truncated
          ? `Showing the first ${exportRows.length.toLocaleString()} of ${total.toLocaleString()} records.`
          : undefined
        exportPdf(exportRows, cols, `${base}.pdf`, report.name, note)
      }
    } catch (e) {
      setActionError(e instanceof ApiError ? e.message : 'Export failed — is the backend reachable?')
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title="Reports"
          subtitle={
            view === 'build'
              ? 'Build a custom report — pick your data, pick your columns, filter, then export'
              : 'Saved report templates — same columns and filters every time, always current data'
          }
          module="reports"
        />
        <SegmentedControl options={VIEWS} value={view} onChange={setView} />
      </div>

      {actionError && <p className="-mb-2 pl-1 text-xs font-medium text-risk">{actionError}</p>}

      {view === 'saved' ? (
        <SavedReportsView
          currentUser={user}
          onDelete={handleDeleteSaved}
          onDownload={handleDownloadSaved}
          onEdit={loadReportIntoBuilder}
        />
      ) : (
        <>
          {editingId && (
            <div className="flex items-center gap-2 rounded-lg border border-brand/25 bg-brand-soft px-3 py-2 text-xs font-medium text-brand">
              <Pencil size={13} />
              Editing "{saveName || 'saved report'}" — Update it below, or Save as New to keep the original untouched.
              <button type="button" onClick={resetBuilder} className="ml-auto flex items-center gap-1 text-brand hover:underline">
                <X size={12} />
                Cancel
              </button>
            </div>
          )}

          <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search reference, item, supplier…' }}>
            <MultiSelectFilter
              label="Data"
              options={REPORT_TYPES.map((t) => t.label)}
              value={typeLabels}
              onChange={(labels) => setTypes(labels.map((l) => REPORT_TYPES.find((r) => r.label === l)!.value))}
            />
            {itemOptions.length > 0 && <MultiSelectFilter label="Item Name" options={itemOptions} value={item} onChange={setItem} />}
            {shaftOptions.length > 0 && <MultiSelectFilter label="Shaft" options={shaftOptions} value={shaft} onChange={setShaft} />}
            {supplierOptions.length > 0 && <MultiSelectFilter label="Supplier" options={supplierOptions} value={supplier} onChange={setSupplier} />}
            {branchOptions.length > 0 && <MultiSelectFilter label="Branch" options={branchOptions} value={branch} onChange={setBranch} />}
            {categoryOptions.length > 0 && <MultiSelectFilter label="Category" options={categoryOptions} value={category} onChange={setCategory} />}
            <DateRangeFilter label="Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
          </FilterBar>

          {!hasTypes ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-soft text-brand">
                  <Database size={22} />
                </span>
                <p className="text-sm text-muted">Select at least one data type above to build a report.</p>
              </CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardContent className="p-4">
                  <ColumnPicker
                    label="Columns to show"
                    options={availableColumns.map((c) => ({ key: c.key, label: c.label }))}
                    value={selectedColumns}
                    onChange={setSelectedColumns}
                  />
                </CardContent>
              </Card>

              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
                  <span className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                    <ListChecks size={16} className="text-brand" />
                    {(pagination?.total ?? 0).toLocaleString()} records
                  </span>
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      value={saveName}
                      onChange={(e) => {
                        setSaveName(e.target.value)
                        setSaveMessage('')
                      }}
                      placeholder="Name this report to save it…"
                      className="h-10 w-56"
                    />
                    <Button variant="outline" onClick={handleSave} disabled={!saveName.trim()}>
                      <Save size={15} />
                      {editingId ? 'Update Report' : 'Save as Report'}
                    </Button>
                    {editingId && (
                      <Button variant="ghost" onClick={handleSaveAsNew} disabled={!saveName.trim()}>
                        Save as New
                      </Button>
                    )}
                    <div className="h-6 w-px bg-line" />
                    <Button onClick={handleExportExcel} disabled={(pagination?.total ?? 0) === 0 || visibleColumns.length === 0}>
                      <FileSpreadsheet size={15} />
                      Export Excel
                    </Button>
                    <Button
                      variant="outline"
                      onClick={handleExportPdf}
                      disabled={(pagination?.total ?? 0) === 0 || visibleColumns.length === 0 || exportingPdf}
                    >
                      <FileText size={15} />
                      {exportingPdf ? 'Preparing…' : 'Export PDF'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
              {saveMessage && <p className="-mt-3 pl-1 text-xs font-medium text-healthy">{saveMessage}</p>}

              <LiveDataState isLoading={isLoading} isError={isError} error={error} />

              {!isLoading && !isError && (
                <Card>
                  <CardContent className="flex flex-col gap-0 p-0">
                    <DataTable columns={tableColumns} rows={(data?.rows ?? []) as unknown as Record<string, unknown>[]} height={520} />
                    {pagination && (
                      <div className="px-3 pb-3">
                        <Pagination
                          page={pagination.page}
                          pageCount={Math.max(1, pagination.total_pages)}
                          total={pagination.total}
                          pageSize={pagination.page_size}
                          onPage={setPage}
                        />
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

function SavedReportsView({
  currentUser, onDelete, onDownload, onEdit,
}: {
  currentUser: { username: string; isAdmin: boolean } | null
  onDelete: (id: number) => void
  onDownload: (report: SavedReport, format: 'xlsx' | 'pdf') => void
  onEdit: (report: SavedReport) => void
}) {
  const { data: reports, isLoading, isError, error } = useSavedReports()
  const [expandedId, setExpandedId] = useState<number | null>(null)

  if (isLoading || isError) {
    return <LiveDataState isLoading={isLoading} isError={isError} error={error} />
  }

  if (!reports || reports.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 p-12 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-brand-soft text-brand">
            <Inbox size={22} />
          </span>
          <p className="text-sm text-muted">No saved reports yet — build one under "Build Report" and save it to see it here.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {reports.map((r) => {
        const canManage = currentUser && (currentUser.isAdmin || currentUser.username === r.created_by)
        const typeLabels = r.types.map((t) => REPORT_TYPES.find((rt) => rt.value === t)?.label ?? t).join(', ')
        const expanded = expandedId === r.id

        return (
          <Card key={r.id}>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="font-display text-base font-bold text-navy">{r.name}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    {typeLabels} · {r.columns.length} columns · saved by {r.created_by ?? 'unknown'} on {new Date(r.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button variant="outline" size="sm" onClick={() => setExpandedId(expanded ? null : r.id)}>
                    {expanded ? <EyeOff size={14} /> : <Eye size={14} />}
                    {expanded ? 'Hide' : 'View'}
                  </Button>
                  {canManage && (
                    <Button variant="outline" size="sm" onClick={() => onEdit(r)}>
                      <Pencil size={14} />
                      Edit
                    </Button>
                  )}
                  <Button size="sm" onClick={() => onDownload(r, 'xlsx')}>
                    <FileSpreadsheet size={14} />
                    Excel
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => onDownload(r, 'pdf')}>
                    <FileText size={14} />
                    PDF
                  </Button>
                  {canManage && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onDelete(r.id)}
                      title="Delete this saved report"
                      className="w-9 border-risk/30 px-0 text-risk hover:bg-risk-bg hover:text-risk"
                    >
                      <Trash2 size={14} />
                    </Button>
                  )}
                </div>
              </div>

              {expanded && <SavedReportPreview report={r} />}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

/** Recomputed on every expand, not cached — the whole point of View here is
 * "what does this look like right now." Just the first page: this is a
 * quick look at the shape of the report, not a substitute for downloading
 * it — Excel/PDF pull the full filtered set. */
function SavedReportPreview({ report }: { report: SavedReport }) {
  const filters = useMemo(() => savedReportFilters(report), [report])
  const { data, isLoading, isError, error } = useReportData(filters, 1, 50)
  const previewColumns = useMemo(
    () => toTableColumns(unionColumns(report.types).filter((c) => report.columns.includes(c.key))),
    [report.types, report.columns],
  )

  return (
    <div className="animate-fade-in-up rounded-xl border border-line">
      {isLoading || isError ? (
        <div className="p-3">
          <LiveDataState isLoading={isLoading} isError={isError} error={error} />
        </div>
      ) : (
        <>
          <p className="border-b border-line px-3 py-2 text-xs text-muted">
            {(data?.pagination.total ?? 0).toLocaleString()} records, live as of right now
            {(data?.pagination.total ?? 0) > 50 ? ' — showing the first 50' : ''}
          </p>
          <DataTable columns={previewColumns} rows={(data?.rows ?? []) as unknown as Record<string, unknown>[]} height={360} />
        </>
      )}
    </div>
  )
}
