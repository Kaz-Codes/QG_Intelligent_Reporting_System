import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { SegmentedControl } from '@/components/SegmentedControl'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { ApiError } from '@/lib/api/client'
import { listLogisticsOrders, getImportFobJobs, type ApiImportFobJob } from '@/lib/api/logistics'
import { apiToRow, type LogisticsListRow } from '@/lib/api/logisticsMap'
import type { ServiceJobType } from '@/lib/logisticsStatusData'

/**
 * Service Jobs tab — the shipping/clearing work Logistics does that isn't one
 * of its own export/local orders. Two job types side by side:
 *
 *   - Import FOB      : handed over from Imports (item details entered there
 *                       first). Read-only here; opens the source consignment.
 *   - Customer Rework : a customer sends old rolls / used goods for rework.
 *                       Imports isn't involved, but the job needs the same
 *                       shape as a standard order (items, packing, shipping,
 *                       expenditures, status, Send to Trucking) — so
 *                       "New Rework Job" opens the SAME 5-step order wizard
 *                       (jobKind pre-set to 'rework'), not a lightweight
 *                       single form.
 *
 * A type filter switches between All / Import FOB / Customer Rework.
 *
 * Both halves are LIVE, but they are different KINDS of thing:
 *
 *   Customer Rework OWNS its records — a rework job is a real
 *   logistics_consignments row with job_kind='rework' (no separate table; it
 *   is structurally an order), so it has change history, submit and the closed
 *   lock. Read from GET /logistics/?job_kind=rework.
 *
 *   Import FOB is a READ-THROUGH. The consignment's home stays imports, where
 *   its item details were entered; logistics only sees the ones imports
 *   explicitly handed over (sent_to_logistics_at). Read from
 *   GET /logistics/import-fob-jobs, and the row opens the SOURCE consignment
 *   in imports rather than anything here. There is no "take" step, so unlike
 *   trucking's queue nothing is ever consumed off this list.
 */
type TypeFilter = 'all' | ServiceJobType

const TYPE_OPTIONS = [
  { value: 'all' as const, label: 'All' },
  { value: 'import-fob' as const, label: 'Import FOB' },
  { value: 'customer-rework' as const, label: 'Customer Rework' },
]

/** One table row, either a read-only import-fob ServiceJob or a real
 *  customer-rework LogisticsOrder — kept as a union rather than flattening
 *  rework into the ServiceJob shape, since the rework row needs the real
 *  items array (for a proper multi-item summary) and a real systemId to
 *  link into LogisticsStatusDetail. */
type Row =
  | { kind: 'import-fob'; job: ApiImportFobJob }
  | { kind: 'customer-rework'; order: LogisticsListRow }

/** Rework jobs are ordinary orders behind the scenes, so one page of 100 is
 *  plenty — this is a service queue, not the main order book. */
const REWORK_PAGE_SIZE = 100

export function ServiceJobsTab({ initialTypeFilter }: { initialTypeFilter?: TypeFilter } = {}) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const canEnter = can(user, 'enter')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(initialTypeFilter ?? 'all')

  const [reworkOrders, setReworkOrders] = useState<LogisticsListRow[]>([])
  const [fobJobs, setFobJobs] = useState<ApiImportFobJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadJobs = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Two independent sources — one owned, one read-through — fetched
      // together so the tab lands in one paint rather than two.
      const [rework, fob] = await Promise.all([
        listLogisticsOrders({ jobKind: 'rework', pageSize: REWORK_PAGE_SIZE }),
        getImportFobJobs(),
      ])
      setReworkOrders(rework.rows.map(apiToRow))
      setFobJobs(fob)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 403
        ? "Signed in, but this account doesn't have permission to view logistics."
        : err instanceof Error ? err.message : 'Could not load service jobs')
      setReworkOrders([])
      setFobJobs([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadJobs() }, [loadJobs])

  const rows: Row[] = useMemo(() => {
    const fobRows: Row[] = fobJobs.map((job) => ({ kind: 'import-fob', job }))
    const reworkRows: Row[] = reworkOrders.map((order) => ({ kind: 'customer-rework', order }))
    if (typeFilter === 'import-fob') return fobRows
    if (typeFilter === 'customer-rework') return reworkRows
    return [...fobRows, ...reworkRows]
  }, [typeFilter, fobJobs, reworkOrders])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <SegmentedControl options={TYPE_OPTIONS} value={typeFilter} onChange={setTypeFilter} />
          <span className="text-xs text-muted">
            {loading ? '…' : fobJobs.length} import FOB · {loading ? '…' : reworkOrders.length} customer rework
          </span>
        </div>
        {canEnter && (
          <Button onClick={() => navigate('/logistics-status/rework/new')}>
            New Rework Job
          </Button>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>{error}</span>
          <button type="button" onClick={() => void loadJobs()} className="underline">Retry</button>
        </div>
      )}

      <div className="max-h-[60vh] overflow-auto rounded-xl border border-line bg-surface [scrollbar-width:auto]">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="sticky top-0 z-10 bg-canvas-alt text-xs text-muted shadow-[0_1px_0_var(--color-line)]">
            <tr>
              <th className="px-3 py-2 text-left">Job ID</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Customer</th>
              <th className="px-3 py-2 text-left">Item details</th>
              <th className="px-3 py-2 text-left">Origin</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Clearing agent</th>
              <th className="px-3 py-2 text-left"></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted">
                  {loading ? 'Loading service jobs…' : 'No service jobs of this type yet.'}
                </td>
              </tr>
            )}
            {rows.map((row) =>
              row.kind === 'import-fob' ? (
                <ImportFobRow key={`fob-${row.job.consignment_id}`} job={row.job} onOpenImports={(id) => navigate(`/imports-status/${id}`)} />
              ) : (
                <ReworkOrderRow key={`rw-${row.order.id}`} order={row.order} onOpen={(id) => navigate(`/logistics-status/${id}`)} />
              ),
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ImportFobRow({ job, onOpenImports }: { job: ApiImportFobJob; onOpenImports: (id: number) => void }) {
  return (
    <tr className="border-t border-line hover:bg-canvas-alt">
      {/* The LC/DP instrument number is what people recognise a consignment
          by; the id is the fallback for one that hasn't got one yet. */}
      <td className="px-3 py-2 font-semibold tabular-nums">
        {job.instrument_number || `IMP-${job.consignment_id}`}
      </td>
      <td className="px-3 py-2"><TypeTag type="import-fob" /></td>
      {/* Supplier, not customer: on an inbound FOB import the counterparty is
          who QG bought from. */}
      <td className="px-3 py-2">{job.supplier || '—'}</td>
      <td className="px-3 py-2">{job.item_summary || '—'}</td>
      <td className="px-3 py-2 text-muted">{job.origin || '—'}</td>
      <td className="px-3 py-2">
        {job.status ? <StatusBadge label={job.status} /> : <span className="text-muted">—</span>}
      </td>
      <td className="px-3 py-2 text-[13px]">
        {!job.clearing_agent
          ? <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">Needs agent</span>
          : job.clearing_agent}
      </td>
      <td className="px-3 py-2">
        {/* The record's home is imports — there is nothing to open here. */}
        <button
          onClick={() => onOpenImports(job.consignment_id)}
          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
        >
          Open in Imports
        </button>
      </td>
    </tr>
  )
}

function ReworkOrderRow({ order, onOpen }: { order: LogisticsListRow; onOpen: (id: number) => void }) {
  const itemsSummary = order.items.map((it) => `${it.itemDetail || 'Not named'}${it.quantity !== undefined ? ` ×${it.quantity}` : ''}`)
  const origin = order.orderType === 'Export' ? (order.originCountry || '—') : (order.originCity || '—')
  return (
    <tr className="border-t border-line hover:bg-canvas-alt">
      <td className="px-3 py-2 font-semibold tabular-nums">{order.systemId}</td>
      <td className="px-3 py-2"><TypeTag type="customer-rework" /></td>
      <td className="px-3 py-2">{order.customerName || '—'}</td>
      <td className="px-3 py-2 max-w-[260px] truncate" title={itemsSummary.join(', ') || undefined}>
        {itemsSummary.length === 0 ? '—' : itemsSummary.join(', ')}
      </td>
      <td className="px-3 py-2 text-muted">{origin}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {order.status ? <StatusBadge label={order.status} /> : <span className="text-muted">—</span>}
          {order.recordState !== 'submitted' && (
            <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">
              Draft
            </span>
          )}
          {order.isLocked && (
            <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted"
              title="Delivered and submitted — an admin must reopen it before editing">
              Closed
            </span>
          )}
        </div>
      </td>
      <td className="px-3 py-2 text-[13px]">{order.clearingAgent || '—'}</td>
      <td className="px-3 py-2">
        <button
          onClick={() => onOpen(order.id)}
          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
        >
          Open
        </button>
      </td>
    </tr>
  )
}

function TypeTag({ type }: { type: ServiceJobType }) {
  const isFob = type === 'import-fob'
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[11px]"
      style={isFob
        ? { backgroundColor: 'var(--color-watch-bg)', color: 'var(--color-watch)' }
        : { backgroundColor: 'var(--color-info-bg)', color: 'var(--color-info)' }}
    >
      {isFob ? 'Import FOB' : 'Customer Rework'}
    </span>
  )
}
