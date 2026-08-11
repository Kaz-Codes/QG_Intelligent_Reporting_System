import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { History } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { ChangeHistoryCard } from '@/components/changeHistory/ChangeHistoryCard'
import { RevertConfirmDialog } from '@/components/changeHistory/RevertConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { ApiError } from '@/lib/api/client'
import {
  getLogisticsOrder, getLogisticsChangeHistory, revertLogisticsUpdate,
  type ApiLogisticsOrder, type ApiLogisticsHistoryEntry,
} from '@/lib/api/logistics'
import {
  apiToChangeHistoryEntry, EMPTY_LOOKUPS, type LogisticsHistoryLookups,
} from '@/lib/api/logisticsChangeHistoryMap'
import type { ChangeHistoryEntry } from '@/lib/changeHistory'

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: '2-digit' })
const PAGE_SIZE = 5

/**
 * Logistics Status — change history, wired to the live backend.
 *
 * GET /logistics/change-history/{id} for the list,
 * PUT /logistics/revert-update/{id}/{hid} to undo one change.
 *
 * Entries only exist for EDITS: creating an order writes no history row, and
 * the 1,424 rows loaded from the workbooks have none until someone edits them,
 * so an empty history here is normal rather than a failure.
 *
 * Two things are server-truthful rather than inferred (same reasoning as the
 * imports history screen):
 *
 *  - REVERTABILITY. The backend allows reverting only the newest not-yet-
 *    reverted entry (LIFO). With the list paginated, the page in hand can't
 *    answer that — the newest active entry may sit on another page if
 *    everything on this one is reverted — so it is asked for directly.
 *  - WHO MAY REVERT. The route runs verify_entry_ownership on the ORDER, not
 *    on the history row: an admin, or whoever created the record.
 */
export function LogisticsChangeHistory() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [order, setOrder] = useState<ApiLogisticsOrder | null>(null)
  // Raw rows are kept as they came back and mapped at RENDER time, so the
  // order's labels arriving late re-label the cards without a refetch.
  const [rawEntries, setRawEntries] = useState<ApiLogisticsHistoryEntry[]>([])
  const [lookups, setLookups] = useState<LogisticsHistoryLookups>(EMPTY_LOOKUPS)
  /** The one entry the backend would currently accept a revert for, if any. */
  const [revertableId, setRevertableId] = useState<string | null>(null)

  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pageCount, setPageCount] = useState(1)

  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revertingId, setRevertingId] = useState<string | null>(null)
  const [confirmEntry, setConfirmEntry] = useState<ChangeHistoryEntry | null>(null)

  // The order supplies the header provenance, the ownership check, and the
  // child labels a diff can't carry on its own (it only has row ids).
  useEffect(() => {
    if (!id) return
    let cancelled = false
    getLogisticsOrder(id)
      .then((o) => {
        if (cancelled) return
        setOrder(o)
        setLookups({
          itemLabels: new Map(o.items.map((it) => [it.id, it.item_detail || `Item #${it.id}`])),
          packageLabels: new Map(o.packages.map((p) => [p.id, p.packing_works || p.colour_code || `Package #${p.id}`])),
          containerLabels: new Map(o.containers.map((c) => [c.id, c.container_no || c.container_type || `Container #${c.id}`])),
        })
      })
      .catch(() => { /* the history list below reports a real failure */ })
    return () => { cancelled = true }
  }, [id])

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      const [listed, newest] = await Promise.all([
        getLogisticsChangeHistory(id, { page, pageSize: PAGE_SIZE, includeReverted: true }),
        getLogisticsChangeHistory(id, { page: 1, pageSize: 1, includeReverted: false }),
      ])
      setRawEntries(listed.entries)
      setTotal(listed.pagination?.total ?? listed.entries.length)
      setPageCount(listed.pagination?.total_pages ?? 1)
      setRevertableId(newest.entries.length ? String(newest.entries[0].id) : null)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true)
      else setError(err instanceof Error ? err.message : 'Could not load the change history')
      setRawEntries([])
      setTotal(0)
      setPageCount(1)
    } finally {
      setLoading(false)
    }
  }, [id, page])

  useEffect(() => { void load() }, [load])

  const entries: ChangeHistoryEntry[] = useMemo(
    () => rawEntries.map((e) => apiToChangeHistoryEntry(e, lookups)),
    [rawEntries, lookups],
  )

  async function handleRevert(entryId: string) {
    if (!id) return
    setRevertingId(entryId)
    setError(null)
    try {
      await revertLogisticsUpdate(id, entryId)
      setConfirmEntry(null)
      // Reverting flags the row and moves the revertable entry one step back,
      // so re-read rather than patching state locally.
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not revert this change')
    } finally {
      setRevertingId(null)
    }
  }

  if (!id) return null

  if (notFound) {
    return (
      <div className="space-y-4">
        <PageHeader title="Order not found" module="logisticsStatus" />
        <button onClick={() => navigate('/logistics-status')} className="text-sm text-accent hover:underline">
          ← Back to logistics
        </button>
      </div>
    )
  }

  // Mirrors verify_entry_ownership on the revert route.
  const mayRevert = !!user?.isAdmin
    || (order?.created_by_id != null && order.created_by_id === user?.id)

  const createdOn = order?.created_at ? DATE_FMT.format(new Date(order.created_at)) : null
  const label = order?.mo_no || `#${id}`
  const subtitle = order
    ? `Created by ${order.created_by ?? 'unknown'}${createdOn ? ` on ${createdOn}` : ''} · ${total} change${total === 1 ? '' : 's'} recorded`
    : `${total} change${total === 1 ? '' : 's'} recorded`

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted">
        <button onClick={() => navigate('/logistics-status')} className="hover:underline">Logistics Status</button>
        {' › '}
        <button onClick={() => navigate(`/logistics-status/${id}`)} className="hover:underline">{label}</button>
        {' › History'}
      </div>

      <PageHeader
        title={`Change history — ${label}${order?.customer_name ? ` · ${order.customer_name}` : ''}`}
        subtitle={subtitle}
        module="logisticsStatus"
      />

      <p className="rounded-lg border border-line bg-canvas-alt/50 px-3 py-2 text-xs text-muted">
        Only the most recent change can be reverted at a time — reverting steps back one edit, oldest available
        change last. Reverted entries stay listed, greyed out, for the record.
      </p>

      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="underline">Retry</button>
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-dashed border-line px-3 py-12 text-center text-muted">
          Loading change history…
        </div>
      ) : entries.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line px-3 py-12 text-center text-muted">
          <History size={28} />
          <p>No changes have been recorded for this order yet.</p>
          <p className="text-xs">History starts building the first time this order is edited.</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {entries.map((entry) => (
            <ChangeHistoryCard
              key={entry.id}
              entry={entry}
              revertable={entry.id === revertableId}
              canRevert={mayRevert}
              reverting={revertingId === entry.id}
              onRevert={() => setConfirmEntry(entry)}
            />
          ))}
        </div>
      )}

      <Pagination page={page} pageCount={pageCount} total={total} pageSize={PAGE_SIZE} onPage={setPage} />

      <RevertConfirmDialog
        entry={confirmEntry}
        confirming={!!confirmEntry && revertingId === confirmEntry.id}
        onConfirm={() => confirmEntry && void handleRevert(confirmEntry.id)}
        onCancel={() => setConfirmEntry(null)}
      />
    </div>
  )
}
