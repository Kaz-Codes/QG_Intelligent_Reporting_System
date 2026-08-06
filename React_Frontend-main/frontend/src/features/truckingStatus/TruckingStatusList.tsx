import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Download, Printer } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { Button } from '@/components/ui/button'
import { StatusBadge } from '@/components/StatusBadge'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { MOVEMENT_TYPES, TRUCKING_SOURCES, vehicleCount } from './schema'
import { exportListExcel, exportListPdf, type ListColumn } from '@/lib/listExport'
import { usePagination, Pagination, useSort, SortHeader } from '@/components/Pagination'
import {
  getTruckingJobs,
  rollupLabel,
  rowGrossWeight,
  sourceLabel,
  takeAction,
  type TruckingRow,
} from '@/lib/truckingStatusData'

/**
 * Two clearly-separated tables:
 *   1. Open Requests — live, not-yet-taken work handed over from Logistics,
 *      Import-FOB and Export. These aren't owned trucking jobs yet; each has a
 *      Take Action button that converts it into an owned job.
 *   2. Trucking Jobs — the module's own manual + taken jobs, with Open/Edit.
 *
 * Splitting them (rather than one table with a "pending only" toggle) makes the
 * requests genuinely manageable: a dispatcher sees what's waiting to be picked
 * up at a glance, separate from what's already in motion. Both tables share the
 * same filter bar and scroll horizontally on narrow desktops.
 */
const sourceOptions = TRUCKING_SOURCES.map((s) => sourceLabel(s))
const sourceLabelToValue = new Map(TRUCKING_SOURCES.map((s) => [sourceLabel(s), s]))

export function TruckingStatusList() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canEdit = can(user, 'editAny')
  const [movementFilter, setMovementFilter] = useState<string[]>([])
  const [sourceFilter, setSourceFilter] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [takingId, setTakingId] = useState<string | null>(null)
  const [executionFrom, setExecutionFrom] = useState('')
  const [executionTo, setExecutionTo] = useState('')

  const all = useMemo(
    () =>
      getTruckingJobs({
        movementType: movementFilter.length ? movementFilter : undefined,
        source: sourceFilter.length ? sourceFilter.map((label) => sourceLabelToValue.get(label)!) : undefined,
        search,
      }),
    [movementFilter, sourceFilter, search],
  )

  const inDateRange = (r: TruckingRow) => {
    if (executionFrom && (!r.executionDate || r.executionDate < executionFrom)) return false
    if (executionTo && (!r.executionDate || r.executionDate > executionTo)) return false
    return true
  }

  // A request = a live, not-yet-taken derived row (from another module). Once
  // taken it becomes an owned job and drops out of this list.
  const requests = useMemo(
    () =>
      all
        .filter((r) => r.open && r.source !== 'manual' && inDateRange(r))
        .sort((a, b) => a.systemId.localeCompare(b.systemId)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, executionFrom, executionTo],
  )

  const jobsRaw = useMemo(
    () =>
      all.filter((r) => !(r.open && r.source !== 'manual') && inDateRange(r)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [all, executionFrom, executionTo],
  )
  const { sorted: jobs, sort, toggle } = useSort(jobsRaw, {
    systemId: (r) => r.systemId,
    source: (r) => sourceLabel(r.source),
    movement: (r) => r.movementType,
    transporter: (r) => r.transporterName ?? '',
    vehicles: (r) => vehicleCount(r.vehicles),
    payment: (r) => r.paymentStatus ?? '',
    execution: (r) => r.executionDate ?? '',
  })
  const { page, pageCount, pageRows: jobPage, setPage, total, pageSize } = usePagination(jobs, 10)

  // Export requests are always-live with no accept step (takeAction only
  // converts Logistics / Import-FOB sources), so this both narrows the type
  // for takeAction and matches that behaviour — the button is hidden for
  // export rows below rather than no-oping here.
  function canTakeAction(r: TruckingRow): r is TruckingRow & { source: 'from-logistics' | 'from-import-fob' } {
    return (r.source === 'from-logistics' || r.source === 'from-import-fob') && !!r.sourceRef
  }

  function handleTakeAction(r: TruckingRow) {
    if (!canTakeAction(r) || !r.sourceRef) return
    setTakingId(r.systemId)
    const newId = takeAction(r.source, r.sourceRef)
    navigate(`/trucking-status/${newId}/edit/1`)
  }

  const exportColumns: ListColumn<TruckingRow>[] = [
    { header: 'ID', value: (r) => r.systemId },
    { header: 'Source', value: (r) => sourceLabel(r.source) },
    { header: 'Movement', value: (r) => r.movementType },
    { header: 'Transporter', value: (r) => r.transporterName ?? '' },
    { header: 'Pickup', value: (r) => r.pickup ?? '' },
    { header: 'Destination', value: (r) => r.destination ?? '' },
    { header: 'Reference', value: (r) => r.referenceNo ?? '' },
    { header: 'Vehicles', value: (r) => vehicleCount(r.vehicles) },
    { header: 'Gross (kg)', value: (r) => Number(rowGrossWeight(r).toFixed(2)) },
    { header: 'Tracking', value: (r) => rollupLabel(r) },
    { header: 'Quoted', value: (r) => r.quotedFreight ?? '' },
    { header: 'Actual', value: (r) => r.actualFreight ?? '' },
    { header: 'Payment', value: (r) => r.paymentStatus ?? '' },
    { header: 'Execution date', value: (r) => r.executionDate ?? '' },
  ]
  const exportRows = () => [...requests, ...jobs]
  const stamp = () => new Date().toISOString().slice(0, 10)
  const doExcel = () => exportListExcel(exportRows(), exportColumns, `trucking-status-${stamp()}.xlsx`, 'Trucking')
  const doPdf = () => exportListPdf(exportRows(), exportColumns, `trucking-status-${stamp()}.pdf`, 'Trucking Status')

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Trucking Status" subtitle="Vehicle movements & open requests" module="truckingStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={doExcel}>
            <Download size={16} /> Excel
          </Button>
          <Button variant="outline" onClick={doPdf}>
            <Printer size={16} /> PDF
          </Button>
          {can(user, 'enter') && (
            <Button asChild>
              <Link to="/trucking-status/new">New Trucking Job</Link>
            </Button>
          )}
        </div>
      </div>

      <FilterBar
        search={{
          value: search,
          onChange: setSearch,
          placeholder: 'ID, transporter, item…',
        }}
      >
        <MultiSelectFilter label="Movement" options={[...MOVEMENT_TYPES]} value={movementFilter} onChange={setMovementFilter} />
        <MultiSelectFilter label="Source" options={sourceOptions} value={sourceFilter} onChange={setSourceFilter} />
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Execution from</label>
          <input type="date" value={executionFrom} onChange={(e) => setExecutionFrom(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink" />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Execution to</label>
          <input type="date" value={executionTo} onChange={(e) => setExecutionTo(e.target.value)}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink" />
        </div>
      </FilterBar>

      {/* ---- Open Requests (handed over from other modules) ---- */}
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">Open Requests</h3>
          <span className="rounded-full bg-[var(--color-watch-bg)] px-2 py-0.5 text-[11px] text-[var(--color-watch)]">{requests.length}</span>
          <span className="text-xs text-muted">Handed over from Logistics, Import-FOB and Export — take one to start an owned job</span>
        </div>
        {requests.length === 0 ? (
          <div className="rounded-xl border border-dashed border-line px-3 py-6 text-center text-sm text-muted">
            No open requests right now. New ones appear here automatically when Logistics sends an order to trucking or a FOB/export shipment is ready.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line [scrollbar-width:auto]">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-canvas-alt text-xs uppercase text-muted">
                <tr>
                  <th className="px-3 py-2">Request ID</th>
                  <th className="px-3 py-2">Source</th>
                  <th className="px-3 py-2">Movement</th>
                  <th className="px-3 py-2">Transporter</th>
                  <th className="px-3 py-2">Route</th>
                  <th className="px-3 py-2">Reference</th>
                  <th className="px-3 py-2">Execution</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {requests.map((r) => (
                  <tr
                    key={r.systemId}
                    className="cursor-pointer border-t border-line hover:bg-canvas-alt"
                    onClick={() => navigate(`/trucking-status/${r.systemId}`)}
                  >
                    <td className="px-3 py-2 font-medium text-ink">{r.systemId}</td>
                    <td className="px-3 py-2"><SourceTag row={r} /></td>
                    <td className="px-3 py-2">{r.movementType}</td>
                    <td className="px-3 py-2">{r.transporterName ?? '—'}</td>
                    <td className="px-3 py-2 text-muted">{(r.pickup ?? '—')} → {(r.destination ?? '—')}</td>
                    <td className="px-3 py-2 tabular-nums">{r.referenceNo ?? '—'}</td>
                    <td className="px-3 py-2 tabular-nums">{r.executionDate ?? '—'}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/trucking-status/${r.systemId}`)}
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          Open
                        </button>
                        {canTakeAction(r) && (
                          <button
                            onClick={() => handleTakeAction(r)}
                            disabled={takingId === r.systemId}
                            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-brand hover:text-brand disabled:opacity-50"
                          >
                            Take Action
                          </button>
                        )}
                      </div>
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
          <span className="rounded-full bg-canvas-alt px-2 py-0.5 text-[11px] text-muted">{jobs.length}</span>
        </div>
        <div className="overflow-x-auto rounded-xl border border-line [scrollbar-width:auto]">
          <table className="w-full min-w-[1000px] text-left text-sm">
            <thead className="bg-canvas-alt text-xs uppercase text-muted">
              <tr>
                <SortHeader label="ID" sortKey="systemId" sort={sort} onToggle={toggle} />
                <SortHeader label="Source" sortKey="source" sort={sort} onToggle={toggle} />
                <SortHeader label="Movement" sortKey="movement" sort={sort} onToggle={toggle} />
                <SortHeader label="Transporter" sortKey="transporter" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2">Route</th>
                <SortHeader label="Vehicles" sortKey="vehicles" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2">Tracking</th>
                <SortHeader label="Payment" sortKey="payment" sort={sort} onToggle={toggle} />
                <SortHeader label="Execution" sortKey="execution" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-right">Delay</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {jobPage.map((r) => (
                <tr
                  key={r.systemId}
                  className="cursor-pointer border-t border-line hover:bg-canvas-alt"
                  onClick={() => navigate(`/trucking-status/${r.systemId}`)}
                >
                  <td className="px-3 py-2 font-medium text-ink">{r.systemId}</td>
                  <td className="px-3 py-2"><SourceTag row={r} /></td>
                  <td className="px-3 py-2">{r.movementType}</td>
                  <td className="px-3 py-2">{r.transporterName ?? '—'}</td>
                  <td className="px-3 py-2 text-muted">{(r.pickup ?? '—')} → {(r.destination ?? '—')}</td>
                  <td className="px-3 py-2 tabular-nums">{vehicleCount(r.vehicles) || '—'}</td>
                  <td className="px-3 py-2">
                    {vehicleCount(r.vehicles) ? <StatusBadge label={rollupLabel(r)} /> : <span className="text-muted">awaiting vehicles</span>}
                  </td>
                  <td className="px-3 py-2">{r.paymentStatus ?? '—'}</td>
                  <td className="px-3 py-2 tabular-nums">{r.executionDate ?? '—'}</td>
                  <td className="px-3 py-2 text-right"><DelayCell days={truckingDelayDays(r)} /></td>
                  <td className="px-3 py-2">
                    <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => navigate(`/trucking-status/${r.systemId}`)}
                        className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                      >
                        Open
                      </button>
                      {canEdit && (
                        <button
                          onClick={() => navigate(`/trucking-status/${r.systemId}/edit/1`)}
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          Edit
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {jobs.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-3 py-8 text-center text-muted">
                    No trucking jobs match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <Pagination page={page} pageCount={pageCount} total={total} pageSize={pageSize} onPage={setPage} />
      </section>
    </div>
  )
}


/** Delay against ETA-to-works: dispatch → etaWorks vs today/actual. Positive =
 *  overdue. Null when we can't compute it. */
function truckingDelayDays(r: TruckingRow): number | null {
  if (!r.etaWorks) return null
  const today = new Date().toISOString().slice(0, 10)
  const a = new Date(r.etaWorks).getTime()
  const b = new Date(today).getTime()
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  // Only meaningful once the job is moving (has a dispatch note).
  if (!r.dispatchNoteDate) return null
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

function SourceTag({ row }: { row: TruckingRow }) {
  const label = sourceLabel(row.source)
  const style =
    row.source === 'from-logistics'
      ? { backgroundColor: 'var(--color-info-bg)', color: 'var(--color-info)' }
      : row.source === 'from-import-fob'
        ? { backgroundColor: 'var(--color-watch-bg)', color: 'var(--color-watch)' }
      : row.source === 'from-export'
        ? { backgroundColor: 'var(--color-healthy-bg)', color: 'var(--color-healthy)' }
        : undefined
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs ${style ? '' : 'bg-canvas-alt text-muted'}`}
      style={style}
    >
      {label}
    </span>
  )
}
