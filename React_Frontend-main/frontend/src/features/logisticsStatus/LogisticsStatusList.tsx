import { useCallback, useEffect, useMemo, useRef, useState, Fragment } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Truck } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { RowDeleteActions, DELETED_ROW_CLASS } from '@/components/RowDeleteActions'
import { can } from '@/lib/roleAccess'
import {
  totalNetWeight, totalPackageGrossWeight, orderTypeLabel, jobNumbers, batchDisplayLabel,
  arrivalDelayDays, latestPlannedRfd, latestActualRfd,
} from '@/features/logisticsStatus/schema'
import { Pagination, useSort, SortHeader } from '@/components/Pagination'
import { SegmentedControl } from '@/components/SegmentedControl'
import { ServiceJobsTab } from './ServiceJobsTab'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ApiError } from '@/lib/api/client'
import {
  listLogisticsOrders, fetchLogisticsFilterOptions, exportLogisticsExcel, downloadBlob,
  reopenLogisticsOrder, deleteLogisticsOrder, undoDeleteLogisticsOrder,
  type LogisticsQuery,
} from '@/lib/api/logistics'
import { apiToRow, type LogisticsListRow } from '@/lib/api/logisticsMap'

const num = (v: number) => v.toLocaleString('en-US')

const PAGE_SIZE = 50

/**
 * Consistent delay pill used across the status modules: red when late, green
 * when on time / early, muted dash when there's no data. `settled` means the
 * real arrival date is in — an unsettled positive delay is an in-flight
 * estimate ("slipping"), which reads differently from a locked-in late.
 */
function DelayCell({ days, settled }: { days: number | null; settled: boolean }) {
  if (days === null) return <span className="text-muted" title="No planned arrival date yet">—</span>
  if (days <= 0) {
    return <span className="tabular-nums text-[var(--color-healthy)]">{days === 0 ? 'on time' : `${-days}d early`}</span>
  }
  return (
    <span
      className="inline-block rounded border border-[var(--color-risk)] bg-[var(--color-risk-bg)] px-1.5 py-0.5 text-[11px] tabular-nums text-[var(--color-risk)]"
      title={settled ? 'Arrived later than planned' : 'Past planned arrival, still in transit'}
    >
      {days}d {settled ? 'late' : 'slipping'}
    </span>
  )
}

/**
 * Logistics Status — list view, ORDERS wired to the live backend.
 *
 * Every filter runs SERVER-side: the three multi-selects, the gate-out range
 * and the search box are all query params on GET /logistics/, and Export Excel
 * re-runs the same query with no page cap so the download is exactly the
 * filtered set. Sorting is client-side over the loaded page, as before.
 *
 * TWO DELIBERATE DIFFERENCES FROM THE IMPORTS LIST:
 *
 *  - There is no "closed" stage strip and no include_closed toggle. A
 *    delivered (closed) order STAYS in the list; it just reports "Closed" in
 *    its own column. The backend list has no such param either, so the two
 *    already agree — nothing to keep in lockstep.
 *  - The Mode column reads from a field the backend does not have yet
 *    (shipmentMode is front-end-only), so it renders "—" for every row rather
 *    than being dropped: the column is in the agreed spec, and showing the gap
 *    is more honest than hiding it.
 *
 * The Service Jobs tab is still entirely mock — it has no backend at all — so
 * it is untouched here and keeps reading lib/logisticsStatusData.
 */
export function LogisticsStatusList() {
  const navigate = useNavigate()
  const { user } = useAuth()

  // A brand-new rework job lands back here via /logistics-status?tab=
  // services&serviceType=customer-rework (see LogisticsStatusWizard's
  // onSubmit) — read once on mount so that redirect actually lands on the
  // Service Jobs tab with the right filter pre-selected, not the Orders tab.
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<'orders' | 'services'>(searchParams.get('tab') === 'services' ? 'services' : 'orders')
  const initialServiceType = searchParams.get('serviceType')

  // --- filter state (drives the query) ---
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [orderTypeFilter, setOrderTypeFilter] = useState<string[]>([])
  const [customerFilter, setCustomerFilter] = useState<string[]>([])
  const [gateOutFrom, setGateOutFrom] = useState('')
  const [gateOutTo, setGateOutTo] = useState('')
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  // --- data ---
  const [rowsRaw, setRowsRaw] = useState<LogisticsListRow[]>([])
  const [total, setTotal] = useState(0)
  const [pageCount, setPageCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [reopeningId, setReopeningId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  /** The closed order awaiting reopen confirmation; null means no dialog. */
  const [confirmReopen, setConfirmReopen] = useState<LogisticsListRow | null>(null)

  // --- dropdown options, from the data itself ---
  const [statusOptions, setStatusOptions] = useState<string[]>([])
  const [orderTypeOptions, setOrderTypeOptions] = useState<string[]>([])
  const [customerOptions, setCustomerOptions] = useState<string[]>([])
  const [optionsError, setOptionsError] = useState<string | null>(null)

  // Typing shouldn't fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const loadOptions = useCallback(() => {
    setOptionsError(null)
    fetchLogisticsFilterOptions()
      .then((options) => {
        setStatusOptions((options.statuses ?? []).map((s) => s.value))
        setOrderTypeOptions((options.order_types ?? []).map((t) => t.value))
        setCustomerOptions(options.customers ?? [])
      })
      .catch((err) => {
        // Never swallow this: a silent failure here shows three empty
        // dropdowns with no hint that anything went wrong.
        setOptionsError(err instanceof Error ? err.message : 'Could not load filter options')
      })
  }, [])

  useEffect(() => { loadOptions() }, [loadOptions])

  /** Soft delete, and its undo.
   *
   *  Re-reads the list rather than patching state: deleting can change which
   *  page a row belongs on, and the backend decides that.
   */
  async function handleDelete(id: number, restore: boolean) {
    setDeletingId(id)
    setError(null)
    try {
      if (restore) await undoDeleteLogisticsOrder(id)
      else await deleteLogisticsOrder(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message
        : `Could not ${restore ? 'restore' : 'delete'} this order`)
    } finally {
      setDeletingId(null)
    }
  }

  const query: LogisticsQuery = useMemo(() => ({
    page,
    pageSize: PAGE_SIZE,
    status: statusFilter,
    orderType: orderTypeFilter,
    customer: customerFilter,
    gateOutFrom: gateOutFrom || undefined,
    gateOutTo: gateOutTo || undefined,
    search: debouncedSearch,
    // Orders only. Customer-rework jobs share this table (job_kind is the
    // discriminator) but belong to the Service Jobs tab, not here. Sent
    // explicitly rather than relying on the server-side default, so the
    // intent is readable at the call site.
    jobKind: 'standard',
    // Deleted orders are FETCHED ONLY FOR AN ADMIN. Nobody else can undo a
    // delete, so for them the rows would be unactionable clutter — and the
    // list is where the undo button lives, so a deleted order has to be
    // reachable here rather than hidden on a screen of its own.
    includeDeleted: !!user?.isAdmin,
  }), [page, statusFilter, orderTypeFilter, customerFilter, gateOutFrom, gateOutTo,
       debouncedSearch, user?.isAdmin])

  // Any filter change puts us back on page 1 — staying on page 7 of a result
  // set that now has 2 pages would show an empty table.
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return }
    setPage(1)
  }, [statusFilter, orderTypeFilter, customerFilter, gateOutFrom, gateOutTo, debouncedSearch])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const { rows: apiRows, pagination } = await listLogisticsOrders(query)
      setRowsRaw(apiRows.map(apiToRow))
      setTotal(pagination?.total ?? apiRows.length)
      setPageCount(pagination?.total_pages ?? 1)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403
        ? "Signed in, but this account doesn't have permission to view logistics."
        : err instanceof Error ? err.message : 'Could not load logistics orders')
      setRowsRaw([])
      setTotal(0)
      setPageCount(0)
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => { void load() }, [load])

  const { sorted: rows, sort, toggle } = useSort(rowsRaw, {
    systemId: (o) => o.systemId,
    orderType: (o) => orderTypeLabel(o.department, o.orderType),
    mode: (o) => o.shipmentMode ?? '',
    customer: (o) => o.customerName,
    batch: (o) => o.batchNo,
    packages: (o) => o.packages.length,
    net: (o) => totalNetWeight(o.items),
    gross: (o) => totalPackageGrossWeight(o.packages),
    incoterm: (o) => o.incoterm ?? '',
    status: (o) => o.status,
    submitted: (o) => (o.recordState === 'submitted' ? 1 : 0),
    closed: (o) => (o.isLocked ? 1 : 0),
    delay: (o) => arrivalDelayDays(o) ?? -99999,
    actualRfd: (o) => latestActualRfd(o.items) ?? '',
  })

  const canEdit = can(user, 'editAny')

  // MO-group sizes across the currently-visible rows — drives the "shares an
  // MO with other batches" accent on the Batch # column. Only ever reflects
  // the loaded page, which is why it is described as "visible rows".
  const moCounts = useMemo(() => {
    const m = new Map<string, number>()
    rows.forEach((o) => { if (o.moNo) m.set(o.moNo, (m.get(o.moNo) ?? 0) + 1) })
    return m
  }, [rows])

  /** Admin-only server-side too (require_admin on the route) — the button is
   *  hidden for everyone else, but that is UX, not the boundary. */
  async function handleReopen(order: LogisticsListRow) {
    setReopeningId(order.id)
    setError(null)
    try {
      await reopenLogisticsOrder(order.id)
      setConfirmReopen(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reopen this order')
    } finally {
      setReopeningId(null)
    }
  }

  async function doExcel() {
    setExporting(true)
    try {
      const blob = await exportLogisticsExcel(query)
      downloadBlob(blob, `logistics_orders_${new Date().toISOString().slice(0, 10)}.xlsx`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export')
    } finally {
      setExporting(false)
    }
  }

  const shown = loading ? 'Loading…' : `${total} total${pageCount > 1 ? ` · page ${page} of ${pageCount}` : ''}`

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Logistics Status" subtitle={shown} module="logisticsStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void doExcel()} disabled={exporting || total === 0}>
            {exporting ? 'Exporting…' : 'Export Excel'}
          </Button>
          {can(user, 'enter') && (
            <Button asChild>
              <Link to="/logistics-status/new">New Logistics Order</Link>
            </Button>
          )}
        </div>
      </div>

      <SegmentedControl
        options={[{ value: 'orders' as const, label: 'Orders' }, { value: 'services' as const, label: 'Service Jobs' }]}
        value={tab}
        onChange={setTab}
      />

      {tab === 'services' ? (
        <ServiceJobsTab initialTypeFilter={initialServiceType === 'customer-rework' || initialServiceType === 'import-fob' ? initialServiceType : undefined} />
      ) : (
      <>
      <FilterBar
        search={{
          value: search,
          onChange: setSearch,
          placeholder: 'ID, MO no., customer, item, job no…',
        }}
      >
        <MultiSelectFilter label="Order type" options={orderTypeOptions} value={orderTypeFilter} onChange={setOrderTypeFilter} />
        <MultiSelectFilter label="Status" options={statusOptions} value={statusFilter} onChange={setStatusFilter} />
        <MultiSelectFilter label="Customer" options={customerOptions} value={customerFilter} onChange={setCustomerFilter} />
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Gate out from</label>
          <input
            type="date"
            value={gateOutFrom}
            onChange={(e) => setGateOutFrom(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Gate out to</label>
          <input
            type="date"
            value={gateOutTo}
            onChange={(e) => setGateOutTo(e.target.value)}
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

      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="underline">Retry</button>
        </div>
      )}

      {rows.length === 0 ? (
        <Card>
          <CardContent className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted">
            <Truck size={28} />
            <p>{loading ? 'Loading logistics orders…' : 'No logistics orders match this search.'}</p>
          </CardContent>
        </Card>
      ) : (
        <div className="max-h-[65vh] overflow-auto rounded-xl border border-line bg-surface [scrollbar-width:auto]">
          <table className="w-full min-w-[1200px] text-sm">
            <thead className="sticky top-0 z-10 bg-canvas-alt text-xs text-muted shadow-[0_1px_0_var(--color-line)]">
              <tr>
                <SortHeader label="MO #" sortKey="systemId" sort={sort} onToggle={toggle} />
                <SortHeader label="Order Type" sortKey="orderType" sort={sort} onToggle={toggle} />
                <SortHeader label="Mode" sortKey="mode" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-left">Job #</th>
                <SortHeader label="Customer" sortKey="customer" sort={sort} onToggle={toggle} />
                <SortHeader label="Batch #" sortKey="batch" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-left">Items</th>
                <SortHeader label="Packages" sortKey="packages" sort={sort} onToggle={toggle} />
                <SortHeader label="Net Wt (kg)" sortKey="net" sort={sort} onToggle={toggle} align="right" />
                <SortHeader label="Gross Wt (kg)" sortKey="gross" sort={sort} onToggle={toggle} align="right" />
                <th className="px-3 py-2 text-left">Works</th>
                <SortHeader label="Incoterm" sortKey="incoterm" sort={sort} onToggle={toggle} />
                <SortHeader label="Status" sortKey="status" sort={sort} onToggle={toggle} />
                <SortHeader label="Submitted" sortKey="submitted" sort={sort} onToggle={toggle} />
                <SortHeader label="Closed" sortKey="closed" sort={sort} onToggle={toggle} />
                <SortHeader label="Arrival delay" sortKey="delay" sort={sort} onToggle={toggle} align="right" />
                <SortHeader label="Actual RFD" sortKey="actualRfd" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-left">Sent to Trucking</th>
                <th className="px-3 py-2 text-left"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => {
                const jobNos = jobNumbers(o.items)
                const itemsSummary = o.items.map((it) => `${it.itemDetail}${it.quantity !== undefined ? ` ×${it.quantity}` : ''}`)
                const inMoGroup = !!o.moNo && (moCounts.get(o.moNo) ?? 0) > 1
                const works = o.packages.find((p) => p.packingWorks)?.packingWorks
                const colours = [...new Set(o.packages.map((p) => p.colourCode).filter(Boolean))]
                const isOpen = expandedId === o.id
                return (
                  <Fragment key={o.id}>
                  <tr
                    className={`cursor-pointer border-t border-line hover:bg-canvas-alt ${inMoGroup ? 'border-l-2 border-l-brand' : ''} ${isOpen ? 'bg-canvas-alt' : ''} ${o.isDeleted ? DELETED_ROW_CLASS : ''}`}
                    onClick={() => setExpandedId(isOpen ? null : o.id)}
                    aria-expanded={isOpen}
                    style={o.missingFields.length > 0 ? { boxShadow: 'inset 3px 0 0 var(--color-watch)' } : undefined}
                  >
                    <td className="px-3 py-2">
                      <div className="tabular-nums font-semibold">
                        <span className={`mr-1.5 inline-block text-[10px] text-muted transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                        {o.systemId}
                        {o.batchNo > 1 && (
                          <span className="ml-1 font-normal text-muted">({batchDisplayLabel(o.batchNo, o.batchLabel)})</span>
                        )}
                      </div>
                      {o.missingFields.length > 0 && (
                        <span
                          className="mt-0.5 inline-block rounded bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-watch)]"
                          title={`Missing: ${o.missingFields.join(', ')}`}
                        >
                          {o.missingFields.length} field{o.missingFields.length > 1 ? 's' : ''} missing
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">{orderTypeLabel(o.department, o.orderType)}</td>
                    <td className="px-3 py-2 text-[13px]">{o.shipmentMode ?? '—'}</td>
                    <td className="px-3 py-2 text-[13px] tabular-nums" title={jobNos.join(', ') || undefined}>
                      {jobNos.length === 0 ? '—' : jobNos.length <= 2 ? jobNos.join(', ') : `${jobNos.slice(0, 2).join(', ')} +${jobNos.length - 2}`}
                    </td>
                    <td className="px-3 py-2">{o.customerName || '—'}</td>
                    <td className="px-3 py-2">
                      <span className="text-[13px]">{batchDisplayLabel(o.batchNo, o.batchLabel)}</span>
                      {inMoGroup && (
                        <span className="ml-1.5 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] text-brand">MO group</span>
                      )}
                    </td>
                    <td className="px-3 py-2 max-w-[220px] truncate text-[13px]" title={itemsSummary.join(', ') || undefined}>
                      {itemsSummary.length === 0 ? '—' : itemsSummary.join(', ')}
                    </td>
                    <td className="px-3 py-2 text-[13px] text-muted">
                      {o.packages.length === 0 ? '—' : `${o.packages.length} pkg${o.packages.length === 1 ? '' : 's'}${colours.length ? ` (${colours.join(', ')})` : ''}`}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{num(totalNetWeight(o.items))}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{num(totalPackageGrossWeight(o.packages))}</td>
                    <td className="px-3 py-2 text-[13px] text-muted">{works || '—'}</td>
                    <td className="px-3 py-2 text-[13px]">{o.incoterm || '—'}</td>
                    <td className="px-3 py-2">
                      <StatusBadge label={o.status} />
                    </td>
                    <td className="px-3 py-2">
                      {o.recordState === 'submitted'
                        ? <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted">Submitted</span>
                        : <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">Draft</span>}
                    </td>
                    <td className="px-3 py-2">
                      {o.isLocked
                        ? <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted" title="Delivered — an admin must reopen it before editing">Closed</span>
                        : <span className="text-muted">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <DelayCell days={arrivalDelayDays(o)} settled={!!o.actualArrivalDate} />
                    </td>
                    <td className="px-3 py-2 text-[13px] tabular-nums">
                      {(() => {
                        const actual = latestActualRfd(o.items)
                        const planned = latestPlannedRfd(o.items)
                        if (actual) return <span>{actual}</span>
                        if (planned) return <span className="text-muted" title="Planned RFD — not yet actualised">{planned} <span className="text-[10px]">(planned)</span></span>
                        return <span className="text-muted">—</span>
                      })()}
                    </td>
                    <td className="px-3 py-2">
                      {o.sentToTrucking
                        ? <span className="rounded border border-[var(--color-healthy)]/30 bg-[var(--color-healthy-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-healthy)]">Sent</span>
                        : <span className="text-xs text-muted">Not sent</span>}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/logistics-status/${o.id}`)}
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          Open
                        </button>
                        {canEdit && (
                          <button
                            onClick={() => navigate(`/logistics-status/${o.id}/edit/order`)}
                            disabled={o.isLocked}
                            title={o.isLocked ? 'Closed — an admin must reopen it before editing' : undefined}
                            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted disabled:opacity-40"
                          >
                            Edit
                          </button>
                        )}
                        {user?.isAdmin && o.isLocked && (
                          <button
                            onClick={() => setConfirmReopen(o)}
                            disabled={reopeningId === o.id}
                            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted disabled:opacity-40"
                          >
                            {reopeningId === o.id ? 'Reopening…' : 'Reopen'}
                          </button>
                        )}
                        <button
                          onClick={() => navigate(`/logistics-status/${o.id}/history`)}
                          title="View change history"
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          History
                        </button>
                        {/* Admin only — and only the admin ever sees a deleted
                            order to restore, since the list fetches them for
                            nobody else. */}
                        {user?.isAdmin && (
                          <RowDeleteActions
                            isDeleted={o.isDeleted}
                            busy={deletingId === o.id}
                            label={`order ${o.moNo || o.id}`}
                            onDelete={() => void handleDelete(o.id, false)}
                            onUndo={() => void handleDelete(o.id, true)}
                          />
                        )}
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="border-t border-line bg-canvas-alt/60">
                      <td colSpan={20} className="px-3 py-3">
                        <LogisticsRowDetails order={o} />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Rows are SERVER-paged, so this drives the fetch rather than slicing
          an already-loaded array. */}
      <Pagination page={page} pageCount={pageCount} total={total} pageSize={PAGE_SIZE} onPage={setPage} />

      </>
      )}

      <ConfirmDialog
        open={!!confirmReopen}
        title="Reopen this order?"
        description={
          <>
            <span className="font-medium text-ink">{confirmReopen?.moNo || `Order #${confirmReopen?.id}`}</span> is
            closed. Reopening makes it editable again until it is submitted at "Delivered" once more.
          </>
        }
        confirmLabel="Yes, reopen it"
        confirmingLabel="Reopening…"
        confirming={!!confirmReopen && reopeningId === confirmReopen.id}
        danger={false}
        onConfirm={() => confirmReopen && void handleReopen(confirmReopen)}
        onCancel={() => setConfirmReopen(null)}
      />
    </div>
  )
}


/** Single-click expansion for a logistics order row: the job numbers on the
 *  order and every item line with its quantity. */
function LogisticsRowDetails({ order }: { order: LogisticsListRow }) {
  const jobNos = jobNumbers(order.items)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="font-semibold text-muted">Job numbers:</span>
        {jobNos.length === 0
          ? <span className="text-muted">none entered</span>
          : jobNos.map((j, i) => (
              <span key={i} className="rounded bg-surface px-1.5 py-0.5 tabular-nums">{j}</span>
            ))}
      </div>
      {order.items.length === 0 ? (
        <div className="text-xs text-muted">No item lines on this order.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-xs">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 text-left">#</th>
                <th className="py-1 pr-3 text-left">Job no.</th>
                <th className="py-1 pr-3 text-left">Item</th>
                <th className="py-1 pr-3 text-right">Qty</th>
              </tr>
            </thead>
            <tbody className="text-ink">
              {order.items.map((it, i) => (
                <tr key={i} className="border-t border-line/60">
                  <td className="py-1 pr-3 tabular-nums">{i + 1}</td>
                  <td className="py-1 pr-3 tabular-nums">{it.jobNo || '—'}</td>
                  <td className="py-1 pr-3 font-medium">{it.itemDetail || <span className="italic text-muted">Not named</span>}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{it.quantity ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
