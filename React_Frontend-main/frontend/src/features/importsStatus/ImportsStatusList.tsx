import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { SegmentedControl } from '@/components/SegmentedControl'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { SortableTable, type SortableColumn } from './components/SortableTable'
import { StatusPill, Tag, PaymentDot } from './components/atoms'
import { pkr, fx, dateShort, days as daysFmt, num } from './format'
import { STAGE_GROUPS } from '@/lib/importsStages'
import { CANCELLED_STATUS } from './schema'
import {
  listConsignments, fetchFilterOptions, exportConsignmentsExcel, downloadBlob, reopenConsignmentApi,
  type ConsignmentQuery,
} from '@/lib/api/imports'
import {
  apiToRow, slippageDays, requiredDelayDays, freeDaysLeft,
  type ImportsListRow,
} from '@/lib/api/importsMap'

/**
 * Imports Status — list view, wired to the live backend.
 *
 * Every filter runs SERVER-side: the pipeline strip, the four multi-selects,
 * the two checkboxes, the ETD range and the search box are all query params on
 * GET /consignments/, and Export Excel re-runs the same query with no page cap
 * so the download is exactly the filtered set. Sorting is client-side over the
 * loaded page, which is what SortableTable already does.
 *
 * Rows come back newest-first (the backend orders by id desc).
 *
 * Filter dropdowns are fetched from /consignments/filter-options rather than
 * hard-coded, because the imported (Excel) rows carry values the enums don't
 * have — offering only the canonical eleven statuses would make those rows
 * unfilterable. See lib/api/importsMap.ts for the rest of that reconciliation.
 */

const PAGE_SIZE = 50

const STAGE_KEYS = ['all', ...STAGE_GROUPS.map((g) => g.key)] as const
type StageKey = (typeof STAGE_KEYS)[number]

export function ImportsStatusList() {
  const navigate = useNavigate()
  const { user } = useAuth()

  // --- filter state (drives the query) ---
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [stage, setStage] = useState<StageKey>('all')
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [branchFilter, setBranchFilter] = useState<string[]>([])
  const [supplierFilter, setSupplierFilter] = useState<string[]>([])
  const [requisitionFilter, setRequisitionFilter] = useState<string[]>([])
  const [includeClosed, setIncludeClosed] = useState(false)
  const [missingOnly, setMissingOnly] = useState(false)
  const [etdFrom, setEtdFrom] = useState('')
  const [etdTo, setEtdTo] = useState('')
  const [page, setPage] = useState(1)

  // --- data ---
  const [rows, setRows] = useState<ImportsListRow[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [reopeningId, setReopeningId] = useState<number | null>(null)

  // --- dropdown options, from the data itself ---
  const [statusOptions, setStatusOptions] = useState<{ value: string; canonical: boolean }[]>([])
  const [branchOptions, setBranchOptions] = useState<{ id: number; name: string }[]>([])
  const [supplierOptions, setSupplierOptions] = useState<{ id: number; name: string }[]>([])
  const [requisitionOptions, setRequisitionOptions] = useState<string[]>([])

  // Typing shouldn't fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const [optionsError, setOptionsError] = useState<string | null>(null)

  const loadOptions = useCallback(() => {
    setOptionsError(null)
    fetchFilterOptions()
      .then((options) => {
        setStatusOptions(options.statuses ?? [])
        setBranchOptions(options.branches ?? [])
        setSupplierOptions(options.suppliers ?? [])
        setRequisitionOptions(options.requisition_types ?? [])
      })
      .catch((err) => {
        // Never swallow this: a silent failure here shows four empty dropdowns
        // with no hint that anything went wrong.
        setOptionsError(err instanceof Error ? err.message : 'Could not load filter options')
      })
  }, [])

  useEffect(() => { loadOptions() }, [loadOptions])

  // The multi-selects show names; the API filters branch/supplier by id.
  const branchIds = useMemo(
    () => branchOptions.filter((b) => branchFilter.includes(b.name)).map((b) => b.id),
    [branchOptions, branchFilter],
  )
  const supplierIds = useMemo(
    () => supplierOptions.filter((s) => supplierFilter.includes(s.name)).map((s) => s.id),
    [supplierOptions, supplierFilter],
  )

  const query: ConsignmentQuery = useMemo(() => ({
    page,
    pageSize: PAGE_SIZE,
    stage,
    status: statusFilter,
    branchId: branchIds,
    supplierId: supplierIds,
    requisitionType: requisitionFilter,
    includeClosed,
    missingOnly,
    etdFrom: etdFrom || undefined,
    etdTo: etdTo || undefined,
    search: debouncedSearch,
  }), [page, stage, statusFilter, branchIds, supplierIds, requisitionFilter,
       includeClosed, missingOnly, etdFrom, etdTo, debouncedSearch])

  // Any filter change puts us back on page 1 — staying on page 7 of a result
  // set that now has 2 pages would show an empty table.
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return }
    setPage(1)
  }, [stage, statusFilter, branchIds, supplierIds, requisitionFilter,
      includeClosed, missingOnly, etdFrom, etdTo, debouncedSearch])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { rows: apiRows, pagination } = await listConsignments(query)
      setRows(apiRows.map(apiToRow))
      setTotal(pagination?.total ?? apiRows.length)
      setTotalPages(pagination?.total_pages ?? 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load consignments')
      setRows([])
      setTotal(0)
      setTotalPages(0)
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => { void load() }, [load])

  async function handleReopen(id: number) {
    if (!window.confirm('Reopen this consignment? It will become editable again until closed once more.')) return
    setReopeningId(id)
    try {
      await reopenConsignmentApi(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reopen this consignment')
    } finally {
      setReopeningId(null)
    }
  }

  async function doExcel() {
    setExporting(true)
    try {
      const blob = await exportConsignmentsExcel(query)
      downloadBlob(blob, `consignments_${new Date().toISOString().slice(0, 10)}.xlsx`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export')
    } finally {
      setExporting(false)
    }
  }

  const columns: SortableColumn<ImportsListRow>[] = [
    {
      key: 'systemId', label: 'ID / Reference', width: 150,
      sortValue: (r) => r.id,
      render: (r) => (
        <div>
          <div className="font-semibold tabular-nums">{r.systemId}</div>
          <div className="text-[11px] text-muted">{r.instrumentNo || r.items[0]?.referenceNo || '—'}</div>
        </div>
      ),
    },
    {
      key: 'payment', label: 'Payment', width: 150,
      sortValue: (r) => r.paymentState,
      render: (r) => (
        <span className="whitespace-nowrap text-[13px]">
          <PaymentDot state={r.paymentState} />
          {r.paymentLabel}
        </span>
      ),
    },
    {
      key: 'branch', label: 'Branch', width: 120,
      sortValue: (r) => r.branch,
      render: (r) => (
        <div>
          <div>{r.branch}</div>
          <div className="text-[11px] text-muted">{r.requisitionSummary}</div>
        </div>
      ),
    },
    {
      key: 'supplier', label: 'Supplier / Origin', width: 190,
      sortValue: (r) => r.supplier,
      render: (r) => (
        <div>
          <div>{r.supplier}</div>
          <div className="text-[11px] text-muted">{r.origin}</div>
        </div>
      ),
    },
    {
      key: 'items', label: 'Items', width: 170,
      sortValue: (r) => r.items[0]?.itemName ?? '',
      render: (r) => {
        const first = r.items[0]
        const more = r.items.length - 1
        if (!first) return <span className="text-muted">—</span>
        return (
          <div>
            <div>{first.itemName || '—'}</div>
            <div className="text-[11px] text-muted tabular-nums">
              {first.quantity !== null ? `${num(first.quantity)} ${first.uom}` : 'qty not recorded'}
              {more > 0 && ` · +${more} more`}
            </div>
          </div>
        )
      },
    },
    {
      key: 'status', label: 'Status', width: 180,
      sortValue: (r) => r.status,
      render: (r) => (
        <div className="space-y-1">
          <StatusPill status={r.status} canonical={r.statusCanonical} />
          {r.missing.length > 0 && (
            <div>
              <Tag tone="warning" title={`Missing: ${r.missing.join(', ')}`}>
                {r.missing.length} field{r.missing.length > 1 ? 's' : ''} missing
              </Tag>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'requisition', label: 'Requisition / Required', width: 150,
      sortValue: (r) => r.requiredDate ?? '9999',
      render: (r) => (
        <div className="tabular-nums text-[13px]">
          <div>{dateShort(r.requisitionDate)} <span className="text-muted">req'd</span></div>
          <div>{dateShort(r.requiredDate)} <span className="text-muted">needed</span></div>
        </div>
      ),
    },
    {
      key: 'requiredDelay', label: 'Delay (needed vs. ETA)', width: 130, align: 'right',
      sortValue: (r) => requiredDelayDays(r) ?? -9999,
      render: (r) => {
        const d = requiredDelayDays(r)
        if (d === null) return <span className="text-muted" title="Needs both a required date and an ETA">—</span>
        return d <= 0
          ? <span className="tabular-nums text-[var(--color-healthy)]">{d === 0 ? 'on time' : `${-d}d ahead`}</span>
          : <Tag tone="danger" title="ETA is later than the date this was required by">{d}d late</Tag>
      },
    },
    {
      key: 'etd', label: 'ETD', width: 90, align: 'right',
      sortValue: (r) => r.etd ?? '9999',
      render: (r) => <span className="tabular-nums">{dateShort(r.etd)}</span>,
    },
    {
      key: 'eta', label: 'ETA', width: 110, align: 'right',
      sortValue: (r) => r.eta ?? '9999',
      render: (r) => (
        <div className="tabular-nums">
          {dateShort(r.eta)}
          {r.etaHistory.length > 1 && (
            <div className="mt-0.5">
              <Tag tone="warning" title={`Revised ${r.etaHistory.length - 1} time(s)`}>
                ETA ×{r.etaHistory.length - 1}
              </Tag>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'slippage', label: 'Slippage', width: 90, align: 'right',
      sortValue: (r) => slippageDays(r) ?? -1,
      render: (r) => {
        const s = slippageDays(r)
        if (s === null) return <span className="text-muted">—</span>
        return s <= 0
          ? <span className="tabular-nums text-[var(--color-healthy)]">on time</span>
          : <Tag tone="danger">{daysFmt(s)}</Tag>
      },
    },
    {
      key: 'value', label: 'Value', width: 110, align: 'right',
      sortValue: (r) => r.foreignValue ?? -1,
      render: (r) => (
        r.foreignValue !== null
          ? <span className="tabular-nums whitespace-nowrap">{fx(r.foreignValue, r.currency)}</span>
          : <span className="text-muted" title="No priced item line">—</span>
      ),
    },
    {
      key: 'pkr', label: 'Value (PKR)', width: 130, align: 'right',
      sortValue: (r) => r.pkrValue ?? -1,
      render: (r) => {
        if (r.pkrValue === null) {
          return <span className="text-muted" title="Needs a value and a booked exchange rate">—</span>
        }
        return (
          <div className="tabular-nums">
            {pkr(r.pkrValue)}
            {r.exchangeRate !== null && (
              <div className="text-[11px] text-muted" title={r.rateDate ? `Rate booked ${dateShort(r.rateDate)}` : 'Rate date not recorded'}>
                @ {r.exchangeRate.toFixed(2)}{r.rateDate ? ` · ${dateShort(r.rateDate)}` : ''}
              </div>
            )}
          </div>
        )
      },
    },
    {
      key: 'reference', label: 'Reference', width: 130,
      sortValue: (r) => r.instrumentNo ?? '',
      render: (r) => (
        r.instrumentNo
          ? <span className="tabular-nums text-[13px] font-medium">{r.instrumentNo}</span>
          : <span className="text-muted text-[13px]" title="No instrument number entered yet">—</span>
      ),
    },
    {
      key: 'clearance', label: 'Clearance', width: 120,
      sortValue: (r) => freeDaysLeft(r) ?? 9999,
      render: (r) => {
        if (r.gateOut) return <span className="tabular-nums text-[13px]">Out {dateShort(r.gateOut)}</span>
        const left = freeDaysLeft(r)
        if (left === null) return <span className="text-muted">—</span>
        const tone = left <= 2 ? 'danger' : left <= 4 ? 'warning' : 'neutral'
        return <Tag tone={tone}>{left} free day{left === 1 ? '' : 's'} left</Tag>
      },
    },
    {
      key: 'submitted', label: 'Submitted', width: 90,
      sortValue: (r) => (r.recordState === 'submitted' ? 1 : 0),
      render: (r) => (
        r.recordState === 'submitted'
          ? <Tag tone="neutral">Submitted</Tag>
          : <Tag tone="warning">Draft</Tag>
      ),
    },
    {
      // Closed = truly locked (Arrived at Works + submitted) OR the other
      // terminal status, Order Cancelled — mirrors the backend's
      // is_truly_closed (helpers.py), so this matches whatever landed in the
      // Closed stage, including old data that predates the lock/submit flow.
      key: 'closed', label: 'Closed', width: 80,
      sortValue: (r) => (r.isLocked || r.status === CANCELLED_STATUS ? 1 : 0),
      render: (r) => (
        r.isLocked
          ? <Tag tone="neutral" title="Arrived at Works and submitted — an admin must reopen it before editing">Closed</Tag>
          : r.status === CANCELLED_STATUS
            ? <Tag tone="neutral" title="Order cancelled">Closed</Tag>
            : <span className="text-muted">—</span>
      ),
    },
    {
      key: 'actions', label: '', width: 180,
      render: (r) => (
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => navigate(`/imports-status/${r.id}`)}
            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
          >
            Open
          </button>
          {can(user, 'editAny', 'imports') && (
            <button
              onClick={() => navigate(`/imports-status/${r.id}/edit/consignment`)}
              disabled={r.isLocked}
              title={r.isLocked ? 'Closed — an admin must reopen it before editing' : undefined}
              className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted disabled:opacity-40"
            >
              Edit
            </button>
          )}
          {user?.isAdmin && r.isLocked && (
            <button
              onClick={() => void handleReopen(r.id)}
              disabled={reopeningId === r.id}
              className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted disabled:opacity-40"
            >
              {reopeningId === r.id ? 'Reopening…' : 'Reopen'}
            </button>
          )}
          <button
            onClick={() => navigate(`/imports-status/${r.id}/history`)}
            title="View change history"
            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
          >
            History
          </button>
        </div>
      ),
    },
  ]

  const shown = loading ? 'Loading…' : `${total} total${totalPages > 1 ? ` · page ${page} of ${totalPages}` : ''}`

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Consignments" subtitle={shown} module="importsStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void doExcel()} disabled={exporting || total === 0}>
            {exporting ? 'Exporting…' : 'Export Excel'}
          </Button>
          {can(user, 'enter', 'imports') && (
            <Button asChild>
              <Link to="/imports-status/new">New consignment</Link>
            </Button>
          )}
        </div>
      </div>

      {/* The stage strip filters server-side. Counts aren't shown per stage:
          they'd need a separate aggregate call, and a wrong count is worse
          than none. */}
      <SegmentedControl
        options={STAGE_KEYS.map((key) => ({
          value: key,
          label: key === 'all' ? (includeClosed ? 'All' : 'All open') : key,
        }))}
        value={stage}
        onChange={(v) => setStage(v as StageKey)}
      />

      <FilterBar
        search={{
          value: search,
          onChange: setSearch,
          placeholder: 'ID, LC/DP reference, supplier, branch, item…',
        }}
      >
        <MultiSelectFilter
          label="Branch"
          options={branchOptions.map((b) => b.name)}
          value={branchFilter}
          onChange={setBranchFilter}
        />
        <MultiSelectFilter
          label="Status"
          options={statusOptions.map((s) => s.value)}
          value={statusFilter}
          onChange={setStatusFilter}
        />
        <MultiSelectFilter
          label="Requisition"
          options={requisitionOptions}
          value={requisitionFilter}
          onChange={setRequisitionFilter}
        />
        <MultiSelectFilter
          label="Supplier"
          options={supplierOptions.map((s) => s.name)}
          value={supplierFilter}
          onChange={setSupplierFilter}
        />
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={missingOnly} onChange={(e) => setMissingOnly(e.target.checked)} />
          Missing information only
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} />
          Include completed
        </label>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">ETD from</label>
          <input
            type="date"
            value={etdFrom}
            onChange={(e) => setEtdFrom(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">ETD to</label>
          <input
            type="date"
            value={etdTo}
            onChange={(e) => setEtdTo(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink"
          />
        </div>
      </FilterBar>

      {optionsError && (
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>Filter options couldn’t be loaded — {optionsError}</span>
          <button type="button" onClick={loadOptions} className="underline">Retry</button>
        </div>
      )}

      {!optionsError && requisitionOptions.length === 0 && (
        <p className="rounded-lg bg-[var(--color-watch-bg)] px-3 py-2 text-sm text-[var(--color-watch)]">
          No consignment records a requisition type yet — the imported sheets have no such column, so the
          Requisition filter only matches records entered through the ERP.
        </p>
      )}

      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="underline">Retry</button>
        </div>
      )}

      {/* Rows are server-paged, so the table's own footer drives the fetch
          rather than slicing again — one pager, not two. */}
      <SortableTable
        columns={columns}
        rows={rows}
        flagged={(r) => r.missing.length > 0}
        onRowClick={(r) => navigate(`/imports-status/${r.id}`)}
        initialSort={{ key: 'systemId', dir: 'desc' }}
        serverPagination={{
          page,
          pageCount: totalPages,
          totalRows: total,
          pageSize: PAGE_SIZE,
          onPageChange: setPage,
          loading,
        }}
        empty={
          <div>
            <div className="mb-1 font-semibold text-ink">
              {loading ? 'Loading consignments…' : 'No consignments match these filters'}
            </div>
            {!loading && 'Clear a filter or widen the search to see results.'}
          </div>
        }
      />
    </div>
  )
}
