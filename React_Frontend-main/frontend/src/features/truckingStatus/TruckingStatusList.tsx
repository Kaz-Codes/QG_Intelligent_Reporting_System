import { useCallback, useEffect, useMemo, useRef, useState, Fragment } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Download } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { StatusBadge } from '@/components/StatusBadge'
import { useAuth } from '@/features/auth/AuthContext'
import { RowDeleteActions, DELETED_ROW_CLASS } from '@/components/RowDeleteActions'
import { can } from '@/lib/roleAccess'
import { trackingRollup, outstanding } from './schema'
import { Pagination, useSort, SortHeader } from '@/components/Pagination'
import { SegmentedControl } from '@/components/SegmentedControl'
import { ApiError } from '@/lib/api/client'
import {
  listTruckingJobs, getOpenRequests, fetchTruckingFilterOptions,
  exportTruckingExcel, downloadBlob, reopenTruckingJob,
  deleteTruckingJob, undoDeleteTruckingJob,
  type TruckingQuery, type ApiOpenRequest,
} from '@/lib/api/trucking'
import { apiToRow, sourceLabel, type TruckingListRow } from '@/lib/api/truckingMap'

const PAGE_SIZE = 50

/**
 * Trucking Status — wired to the live backend.
 *
 * Two clearly-separated tables, which map onto two DIFFERENT endpoints rather
 * than one list split by a flag:
 *
 *   1. Open Requests — GET /trucking/open-requests. Work handed over from the
 *      other two modules and not yet turned into a job. These are NOT trucking
 *      records: they are derived from the source order/consignment, so they
 *      have no id here and cannot be opened or edited. Taking one starts an
 *      owned job. A request drops off this list the moment a job takes it.
 *   2. Trucking Jobs — GET /trucking/. The module's own records, server
 *      filtered and server paged.
 *
 * NO JOB-LEVEL STATUS COLUMN. Trucking stores tracking per VEHICLE; the
 * job-level reading is a rollup (schema.trackingRollup) computed from the
 * vehicles, never stored. "Closed" is the related-but-separate lock: every
 * vehicle Delivered AND the job submitted.
 */
export function TruckingStatusList() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canEdit = can(user, 'editAny')

  // --- filters (drive the jobs query) ---
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [movementFilter, setMovementFilter] = useState<string[]>([])
  const [sourceFilter, setSourceFilter] = useState<string[]>([])
  const [deliveryFilter, setDeliveryFilter] = useState<string[]>([])
  const [paymentFilter, setPaymentFilter] = useState<string[]>([])
  const [page, setPage] = useState(1)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [requestTab, setRequestTab] = useState<'all' | 'from-logistics' | 'from-import-fob'>('all')

  // --- data ---
  const [jobsRaw, setJobsRaw] = useState<TruckingListRow[]>([])
  const [requests, setRequests] = useState<ApiOpenRequest[]>([])
  const [total, setTotal] = useState(0)
  const [pageCount, setPageCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [reopeningId, setReopeningId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmReopen, setConfirmReopen] = useState<TruckingListRow | null>(null)

  // --- dropdown options, from the data itself ---
  const [movementOptions, setMovementOptions] = useState<string[]>([])
  const [sourceOptions, setSourceOptions] = useState<string[]>([])
  const [optionsError, setOptionsError] = useState<string | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300)
    return () => clearTimeout(timer)
  }, [search])

  const loadOptions = useCallback(() => {
    setOptionsError(null)
    fetchTruckingFilterOptions()
      .then((options) => {
        setMovementOptions((options.movement_types ?? []).map((m) => m.value))
        setSourceOptions(options.sources ?? [])
      })
      .catch((err) => {
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
      if (restore) await undoDeleteTruckingJob(id)
      else await deleteTruckingJob(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message
        : `Could not ${restore ? 'restore' : 'delete'} this job`)
    } finally {
      setDeletingId(null)
    }
  }

  const query: TruckingQuery = useMemo(() => ({
    page,
    pageSize: PAGE_SIZE,
    movementType: movementFilter,
    source: sourceFilter,
    search: debouncedSearch,
    // Deleted jobs are FETCHED ONLY FOR AN ADMIN. Nobody else can undo a
    // delete, so for them the rows would be unactionable clutter — and the
    // list is where the undo button lives, so a deleted job has to be
    // reachable here rather than hidden on a screen of its own.
    includeDeleted: !!user?.isAdmin,
  }), [page, movementFilter, sourceFilter, debouncedSearch, user?.isAdmin])

  // Any filter change goes back to page 1 — staying on page 7 of a set that
  // now has 2 pages would show an empty table.
  const firstRender = useRef(true)
  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return }
    setPage(1)
  }, [movementFilter, sourceFilter, debouncedSearch])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // The two tables are independent sources, fetched together so the page
      // lands in one paint. Open requests are not filtered or paged: the
      // endpoint returns the whole (small) queue.
      const [listed, open] = await Promise.all([
        listTruckingJobs(query),
        getOpenRequests(),
      ])
      setJobsRaw(listed.rows.map(apiToRow))
      setTotal(listed.pagination?.total ?? listed.rows.length)
      setPageCount(listed.pagination?.total_pages ?? 1)
      setRequests(open)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403
        ? "Signed in, but this account doesn't have permission to view trucking."
        : err instanceof Error ? err.message : 'Could not load trucking jobs')
      setJobsRaw([])
      setRequests([])
      setTotal(0)
      setPageCount(0)
    } finally {
      setLoading(false)
    }
  }, [query])

  useEffect(() => { void load() }, [load])

  const { sorted: jobsSorted, sort, toggle } = useSort(jobsRaw, {
    systemId: (r) => r.systemId,
    source: (r) => sourceLabel(r.source),
    movement: (r) => r.movementType,
    transporter: (r) => r.transporterName ?? '',
    vehicles: (r) => r.vehicles.length,
    payment: (r) => r.paymentStatus ?? '',
    execution: (r) => r.executionDate ?? '',
    submitted: (r) => (r.recordState === 'submitted' ? 1 : 0),
    closed: (r) => (r.isLocked ? 1 : 0),
  })

  const jobs = useMemo(() => {
    return jobsSorted.filter((r) => {
      if (deliveryFilter.length > 0) {
        const rollup = trackingRollup(r.vehicles)
        const isDelivered = rollup.total > 0 && rollup.delivered === rollup.total
        const key = isDelivered ? 'Delivered' : 'Undelivered'
        if (!deliveryFilter.includes(key)) return false
      }
      if (paymentFilter.length > 0) {
        const out = outstanding(r.actualFreight, r.paidAmount)
        // Paid = nothing outstanding (<=0 and known); Unpaid = something outstanding.
        const key = out != null && out <= 0 ? 'Paid' : 'Unpaid'
        if (!paymentFilter.includes(key)) return false
      }
      return true
    })
  }, [jobsSorted, deliveryFilter, paymentFilter])

  const visibleRequests = requestTab === 'all'
    ? requests
    : requests.filter((r) => r.source === requestTab)

  async function handleReopen(job: TruckingListRow) {
    setReopeningId(job.id)
    setError(null)
    try {
      await reopenTruckingJob(job.id)
      setConfirmReopen(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reopen this job')
    } finally {
      setReopeningId(null)
    }
  }

  /**
   * Taking a request means CREATING an owned job from it, which needs the full
   * form — so this opens the new-job wizard carrying the source, rather than
   * minting a record behind the user's back. The request stays in the queue
   * until that job is actually saved.
   */
  function handleTakeAction(r: ApiOpenRequest) {
    const params = new URLSearchParams({ source: r.source, source_ref: r.source_ref })
    navigate(`/trucking-status/new?${params}`)
  }

  async function doExcel() {
    setExporting(true)
    try {
      const blob = await exportTruckingExcel(query)
      downloadBlob(blob, `trucking-status-${new Date().toISOString().slice(0, 10)}.xlsx`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not export')
    } finally {
      setExporting(false)
    }
  }

  const shown = loading ? 'Loading…' : `${total} job${total === 1 ? '' : 's'}${pageCount > 1 ? ` · page ${page} of ${pageCount}` : ''}`

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Trucking Status" subtitle={shown} module="truckingStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void doExcel()} disabled={exporting || total === 0}>
            <Download size={16} /> {exporting ? 'Exporting…' : 'Excel'}
          </Button>
          {can(user, 'enter') && (
            <Button asChild>
              <Link to="/trucking-status/new">New Trucking Job</Link>
            </Button>
          )}
        </div>
      </div>

      <FilterBar
        search={{ value: search, onChange: setSearch, placeholder: 'Reference, transporter, item…' }}
      >
        <MultiSelectFilter label="Movement" options={movementOptions} value={movementFilter} onChange={setMovementFilter} />
        <MultiSelectFilter label="Source" options={sourceOptions} value={sourceFilter} onChange={setSourceFilter} />
        <MultiSelectFilter label="Delivery" options={['Delivered', 'Undelivered']} value={deliveryFilter} onChange={setDeliveryFilter} />
        <MultiSelectFilter label="Payment" options={['Paid', 'Unpaid']} value={paymentFilter} onChange={setPaymentFilter} />
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

      {/* ---- Open Requests (handed over from the other two modules) ---- */}
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">Open Requests</h3>
          <span className="rounded-full bg-[var(--color-watch-bg)] px-2 py-0.5 text-[11px] text-[var(--color-watch)]">{requests.length}</span>
          <span className="text-xs text-muted">
            Explicitly handed over from Logistics and Imports — take one to start an owned job
          </span>
        </div>
        <SegmentedControl
          options={[
            { value: 'all' as const, label: `All (${requests.length})` },
            { value: 'from-logistics' as const, label: `Logistics (${requests.filter((r) => r.source === 'from-logistics').length})` },
            { value: 'from-import-fob' as const, label: `Import FOB (${requests.filter((r) => r.source === 'from-import-fob').length})` },
          ]}
          value={requestTab}
          onChange={setRequestTab}
        />
        {visibleRequests.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line px-3 py-6 text-center text-sm text-muted">
            {loading
              ? 'Loading open requests…'
              : 'No open requests right now. One appears here when Logistics sends an order to trucking, or Imports sends a FOB consignment.'}
          </div>
        ) : (
          <div className="max-h-[55vh] overflow-auto rounded-xl border border-line [scrollbar-width:auto]">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="sticky top-0 z-10 bg-canvas-alt text-xs uppercase text-muted shadow-[0_1px_0_var(--color-line)]">
                <tr>
                  <th className="px-3 py-2">Request</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2">Movement</th>
                  <th className="px-3 py-2">Counterparty</th>
                  <th className="px-3 py-2">Reference</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {visibleRequests.map((r) => (
                  <tr key={`${r.source}:${r.source_ref}`} className="border-t border-line hover:bg-canvas-alt">
                    <td className="px-3 py-2 font-medium text-ink">{r.label}</td>
                    <td className="px-3 py-2"><SourceTag source={r.source} /></td>
                    <td className="px-3 py-2">{r.movement_type ?? '—'}</td>
                    <td className="px-3 py-2 text-muted">{r.customer ?? r.supplier ?? '—'}</td>
                    <td className="px-3 py-2 tabular-nums">{r.mo_no ?? r.instrument_number ?? '—'}</td>
                    <td className="px-3 py-2">
                      {/* A request is derived from its source record — there is
                          nothing in trucking to open until it is taken. */}
                      {can(user, 'enter') && (
                        <button
                          onClick={() => handleTakeAction(r)}
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-brand hover:text-brand"
                        >
                          Take Action
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ---- Owned trucking jobs ---- */}
      <section className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">Trucking Jobs</h3>
          <span className="rounded-full bg-canvas-alt px-2 py-0.5 text-[11px] text-muted">{total}</span>
        </div>
        <div className="max-h-[60vh] overflow-auto rounded-xl border border-line [scrollbar-width:auto]">
          <table className="w-full min-w-[1200px] text-left text-sm">
            <thead className="sticky top-0 z-10 bg-canvas-alt text-xs uppercase text-muted shadow-[0_1px_0_var(--color-line)]">
              <tr>
                <SortHeader label="Reference" sortKey="systemId" sort={sort} onToggle={toggle} />
                <SortHeader label="Source" sortKey="source" sort={sort} onToggle={toggle} />
                <SortHeader label="Movement" sortKey="movement" sort={sort} onToggle={toggle} />
                <SortHeader label="Transporter" sortKey="transporter" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2">Route</th>
                <th className="px-3 py-2">Items</th>
                <SortHeader label="Vehicles" sortKey="vehicles" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2">Tracking</th>
                <SortHeader label="Payment" sortKey="payment" sort={sort} onToggle={toggle} />
                <SortHeader label="Execution" sortKey="execution" sort={sort} onToggle={toggle} />
                <SortHeader label="Submitted" sortKey="submitted" sort={sort} onToggle={toggle} />
                <SortHeader label="Closed" sortKey="closed" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-right">Delay</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((r) => {
                // Job-level tracking is DERIVED from the vehicles, never stored.
                const rollup = trackingRollup(r.vehicles)
                const isOpen = expandedId === r.id
                return (
                  <Fragment key={r.id}>
                  <tr
                    className={`cursor-pointer border-t border-line hover:bg-canvas-alt ${isOpen ? 'bg-canvas-alt' : ''} ${r.isDeleted ? DELETED_ROW_CLASS : ''}`}
                    onClick={() => setExpandedId(isOpen ? null : r.id)}
                    aria-expanded={isOpen}
                    style={r.missingFields.length > 0 ? { boxShadow: 'inset 3px 0 0 var(--color-watch)' } : undefined}
                  >
                    <td className="px-3 py-2 font-medium text-ink">
                      <span className={`mr-1.5 inline-block text-[10px] text-muted transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                      {r.systemId}
                      {r.missingFields.length > 0 && (
                        <span
                          className="ml-1.5 inline-block rounded bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-watch)]"
                          title={`Missing: ${r.missingFields.join(', ')}`}
                        >
                          {r.missingFields.length} missing
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2"><SourceTag source={r.source} /></td>
                    <td className="px-3 py-2">{r.movementType || '—'}</td>
                    <td className="px-3 py-2">{r.transporterName ?? '—'}</td>
                    <td className="px-3 py-2 text-muted">{(r.pickup ?? '—')} → {(r.destination ?? '—')}</td>
                    <td className="px-3 py-2">
                      {r.items && r.items.length > 0
                        ? <span title={r.items.map((it) => it.itemDetails).filter(Boolean).join(', ')}>
                            {r.items[0]?.itemDetails || '—'}{r.items.length > 1 ? ` +${r.items.length - 1}` : ''}
                          </span>
                        : (r.itemDetails || '—')}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{r.vehicles.length || '—'}</td>
                    <td className="px-3 py-2">
                      {r.vehicles.length
                        ? <StatusBadge label={rollup.label} />
                        : <span className="text-muted">awaiting vehicles</span>}
                    </td>
                    <td className="px-3 py-2">{r.paymentStatus ?? '—'}</td>
                    <td className="px-3 py-2 tabular-nums">{r.executionDate ?? '—'}</td>
                    <td className="px-3 py-2">
                      {r.recordState === 'submitted'
                        ? <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted">Submitted</span>
                        : <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">Draft</span>}
                    </td>
                    <td className="px-3 py-2">
                      {r.isLocked
                        ? <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted"
                            title="All vehicles delivered and submitted — an admin must reopen it before editing">Closed</span>
                        : <span className="text-muted">—</span>}
                    </td>
                    <td className="px-3 py-2 text-right"><DelayCell days={truckingDelayDays(r)} /></td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/trucking-status/${r.id}`)}
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          Open
                        </button>
                        {canEdit && (
                          <button
                            onClick={() => navigate(`/trucking-status/${r.id}/edit/1`)}
                            disabled={r.isLocked}
                            title={r.isLocked ? 'Closed — an admin must reopen it before editing' : undefined}
                            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted disabled:opacity-40"
                          >
                            Edit
                          </button>
                        )}
                        {user?.isAdmin && r.isLocked && (
                          <button
                            onClick={() => setConfirmReopen(r)}
                            disabled={reopeningId === r.id}
                            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted disabled:opacity-40"
                          >
                            {reopeningId === r.id ? 'Reopening…' : 'Reopen'}
                          </button>
                        )}
                        <button
                          onClick={() => navigate(`/trucking-status/${r.id}/history`)}
                          title="View change history"
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          History
                        </button>
                        {/* Admin only — and only the admin ever sees a deleted
                            job to restore, since the list fetches them for
                            nobody else. */}
                        {user?.isAdmin && (
                          <RowDeleteActions
                            isDeleted={r.isDeleted}
                            busy={deletingId === r.id}
                            label={`job ${r.systemId}`}
                            onDelete={() => void handleDelete(r.id, false)}
                            onUndo={() => void handleDelete(r.id, true)}
                          />
                        )}
                      </div>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="border-t border-line bg-canvas-alt/60">
                      <td colSpan={14} className="px-3 py-3">
                        <TruckingRowDetails row={r} />
                      </td>
                    </tr>
                  )}
                  </Fragment>
                )
              })}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={14} className="px-3 py-8 text-center text-muted">
                    {loading ? 'Loading trucking jobs…' : 'No trucking jobs match these filters.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {/* Server-paged: this drives the fetch, it does not slice a loaded array. */}
        <Pagination page={page} pageCount={pageCount} total={total} pageSize={PAGE_SIZE} onPage={setPage} />
      </section>

      <ConfirmDialog
        open={!!confirmReopen}
        title="Reopen this job?"
        description={
          <>
            <span className="font-medium text-ink">{confirmReopen?.systemId || `Job #${confirmReopen?.id}`}</span> is
            closed. Reopening makes it editable again until it is submitted with every vehicle delivered once more.
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


/** Delay against ETA-to-works: dispatch → etaWorks vs today. Positive =
 *  overdue. Null when we can't compute it. */
function truckingDelayDays(r: TruckingListRow): number | null {
  if (!r.etaWorks) return null
  // Only meaningful once the job is moving (has a dispatch note).
  if (!r.dispatchNoteDate) return null
  const today = new Date().toISOString().slice(0, 10)
  const a = new Date(r.etaWorks).getTime()
  const b = new Date(today).getTime()
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  return Math.round((b - a) / 86_400_000)
}

function DelayCell({ days }: { days: number | null }) {
  if (days === null) return <span className="text-muted">—</span>
  if (days <= 0) return <span className="tabular-nums text-[var(--color-healthy)]">{days === 0 ? 'due today' : `${-days}d left`}</span>
  return (
    <span className="inline-block rounded border border-[var(--color-risk)] bg-[var(--color-risk-bg)] px-1.5 py-0.5 text-[11px] tabular-nums text-[var(--color-risk)]" title="Past ETA to works">
      {days}d overdue
    </span>
  )
}

function SourceTag({ source }: { source: string }) {
  const isManual = source === 'manual'
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[11px]"
      style={isManual
        ? { backgroundColor: 'var(--color-canvas-alt)', color: 'var(--color-muted)' }
        : { backgroundColor: 'var(--color-info-bg)', color: 'var(--color-info)' }}
    >
      {sourceLabel(source)}
    </span>
  )
}


/** Single-click expansion for a trucking job row: its item details and each
 *  assigned vehicle. */
function TruckingRowDetails({ row }: { row: TruckingListRow }) {
  return (
    <div className="flex flex-col gap-3">
      {row.items.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-xs">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 text-left">#</th>
                <th className="py-1 pr-3 text-left">Item details</th>
                <th className="py-1 pr-3 text-right">Qty</th>
                <th className="py-1 pr-3 text-left">Unit</th>
                <th className="py-1 pr-3 text-left">Pickup</th>
                <th className="py-1 pr-3 text-left">Destination</th>
                <th className="py-1 pr-3 text-left">IDM/Ref</th>
              </tr>
            </thead>
            <tbody className="text-ink">
              {row.items.map((it, i) => (
                <tr key={i} className="border-t border-line/60">
                  <td className="py-1 pr-3 tabular-nums">{i + 1}</td>
                  <td className="py-1 pr-3 font-medium">{it.itemDetails || '—'}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{it.quantity ?? '—'}</td>
                  <td className="py-1 pr-3">{it.uom || '—'}</td>
                  <td className="py-1 pr-3">{it.pickup || '—'}</td>
                  <td className="py-1 pr-3">{it.destination || '—'}</td>
                  <td className="py-1 pr-3">{it.referenceNo || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="text-xs">
          <span className="font-semibold text-muted">Item details: </span>
          <span>{row.itemDetails || <span className="text-muted">none entered</span>}</span>
        </div>
      )}
      {row.vehicles.length === 0 ? (
        <div className="text-xs text-muted">No vehicles assigned yet.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-xs">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3 text-left">#</th>
                <th className="py-1 pr-3 text-left">Vehicle</th>
                <th className="py-1 pr-3 text-left">Type</th>
                <th className="py-1 pr-3 text-right">Packages</th>
                <th className="py-1 pr-3 text-right">Gross (kg)</th>
              </tr>
            </thead>
            <tbody className="text-ink">
              {row.vehicles.map((v, i) => (
                <tr key={i} className="border-t border-line/60">
                  <td className="py-1 pr-3 tabular-nums">{i + 1}</td>
                  <td className="py-1 pr-3 font-medium">{v.vehicleNumber || '—'}</td>
                  <td className="py-1 pr-3">{v.vehicleType || '—'}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{v.noOfPackages ?? '—'}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{v.grossWeight ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
