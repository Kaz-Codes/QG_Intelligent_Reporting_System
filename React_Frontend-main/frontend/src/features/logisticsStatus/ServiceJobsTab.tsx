import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { SegmentedControl } from '@/components/SegmentedControl'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  getServiceJobs, getReworkOrders,
  type ServiceJob, type ServiceJobType, type LogisticsOrder,
} from '@/lib/logisticsStatusData'

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
 *                       single form. See lib/logisticsStatusData.ts's
 *                       getReworkOrders().
 *
 * A type filter switches between All / Import FOB / Customer Rework.
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
  | { kind: 'import-fob'; job: ServiceJob }
  | { kind: 'customer-rework'; order: LogisticsOrder }

export function ServiceJobsTab({ initialTypeFilter }: { initialTypeFilter?: TypeFilter } = {}) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const canEnter = can(user, 'enter')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(initialTypeFilter ?? 'all')

  const fobJobs = useMemo(() => getServiceJobs('import-fob'), [])
  const reworkOrders = useMemo(() => getReworkOrders(), [])

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
            {fobJobs.length} import FOB · {reworkOrders.length} customer rework
          </span>
        </div>
        {canEnter && (
          <Button onClick={() => navigate('/logistics-status/rework/new')}>
            New Rework Job
          </Button>
        )}
      </div>

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
                  No service jobs of this type yet.
                </td>
              </tr>
            )}
            {rows.map((row) =>
              row.kind === 'import-fob' ? (
                <ImportFobRow key={row.job.systemId} job={row.job} onOpenImports={(ref) => navigate(`/imports-status/${ref}`)} />
              ) : (
                <ReworkOrderRow key={row.order.systemId} order={row.order} onOpen={(id) => navigate(`/logistics-status/${id}`)} />
              ),
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ImportFobRow({ job, onOpenImports }: { job: ServiceJob; onOpenImports: (ref: string) => void }) {
  return (
    <tr className="border-t border-line hover:bg-canvas-alt">
      <td className="px-3 py-2 font-semibold tabular-nums">{job.systemId}</td>
      <td className="px-3 py-2"><TypeTag type="import-fob" /></td>
      <td className="px-3 py-2">{job.customerName}</td>
      <td className="px-3 py-2">{job.itemDetails}</td>
      <td className="px-3 py-2 text-muted">{job.origin}</td>
      <td className="px-3 py-2"><StatusBadge label={job.status} /></td>
      <td className="px-3 py-2 text-[13px]">
        {!job.clearingAgent
          ? <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">Needs agent</span>
          : job.clearingAgent}
      </td>
      <td className="px-3 py-2">
        <button
          onClick={() => job.sourceRef && onOpenImports(job.sourceRef)}
          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
        >
          Open in Imports
        </button>
      </td>
    </tr>
  )
}

function ReworkOrderRow({ order, onOpen }: { order: LogisticsOrder; onOpen: (id: string) => void }) {
  const itemsSummary = order.items.map((it) => `${it.itemDetail || 'Not named'}${it.quantity !== undefined ? ` ×${it.quantity}` : ''}`)
  const origin = order.orderType === 'Export' ? (order.originCountry || '—') : (order.originCity || '—')
  return (
    <tr className="border-t border-line hover:bg-canvas-alt">
      <td className="px-3 py-2 font-semibold tabular-nums">{order.systemId}</td>
      <td className="px-3 py-2"><TypeTag type="customer-rework" /></td>
      <td className="px-3 py-2">{order.customerName}</td>
      <td className="px-3 py-2 max-w-[260px] truncate" title={itemsSummary.join(', ') || undefined}>
        {itemsSummary.length === 0 ? '—' : itemsSummary.join(', ')}
      </td>
      <td className="px-3 py-2 text-muted">{origin}</td>
      <td className="px-3 py-2">
        {order.status ? <StatusBadge label={order.status} /> : <span className="text-muted">Draft</span>}
      </td>
      <td className="px-3 py-2 text-[13px]">{order.clearingAgent || '—'}</td>
      <td className="px-3 py-2">
        <button
          onClick={() => onOpen(order.systemId)}
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
