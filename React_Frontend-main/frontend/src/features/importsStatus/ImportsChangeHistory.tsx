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
  getConsignment, getConsignmentChangeHistory, revertConsignmentUpdate,
  type ApiConsignment, type ApiChangeHistoryEntry,
} from '@/lib/api/imports'
import { fetchBranches, fetchSuppliers, fetchPorts, fetchClearingAgents } from '@/lib/api/masters'
import {
  apiToChangeHistoryEntry, EMPTY_LOOKUPS, type HistoryLookups,
} from '@/lib/api/importsChangeHistoryMap'
import type { ChangeHistoryEntry } from '@/lib/changeHistory'

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: '2-digit' })
const PAGE_SIZE = 5

/**
 * Imports Status — change history, wired to the live backend.
 *
 * GET /consignments/change-history/{id} for the list,
 * PUT /consignments/revert-update/{id}/{hid} to undo one change.
 *
 * Entries only exist for EDITS: creating a consignment writes no history row,
 * and rows loaded from the Excel sheets have none at all until someone edits
 * them, so an empty history here is normal rather than a failure.
 *
 * Two things are deliberately server-truthful rather than inferred:
 *
 *  - REVERTABILITY. The backend allows reverting only the newest not-yet-
 *    reverted entry (LIFO). With the list paginated, the page in hand can't
 *    answer that on its own — the newest active entry may be on another page
 *    if everything on this one is reverted. So it's asked for directly
 *    (include_reverted=false, one row), which is exactly what the revert route
 *    itself compares against.
 *  - WHO MAY REVERT. The route runs verify_entry_ownership on the CONSIGNMENT,
 *    not on the history row: an admin, or whoever created the record. Not
 *    "whoever made this particular change".
 */
export function ImportsChangeHistory() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [consignment, setConsignment] = useState<ApiConsignment | null>(null)
  // Raw rows are kept as they came back and mapped at RENDER time, so masters
  // arriving late re-label the cards without refetching the list.
  const [rawEntries, setRawEntries] = useState<ApiChangeHistoryEntry[]>([])
  const [lookups, setLookups] = useState<HistoryLookups>(EMPTY_LOOKUPS)
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

  // Masters resolve the FK columns (branch_id -> "QCL"); they never change
  // mid-page, so they're fetched once and reused for every entry. A failure
  // here is not fatal — the mapper falls back to "#id".
  useEffect(() => {
    let cancelled = false
    Promise.all([fetchBranches(), fetchSuppliers(), fetchPorts(), fetchClearingAgents()])
      .then(([branches, suppliers, ports, agents]) => {
        if (cancelled) return
        setLookups((prev) => ({ ...prev, branches, suppliers, ports, agents }))
      })
      .catch(() => { /* mapper degrades to raw ids */ })
    return () => { cancelled = true }
  }, [])

  // The consignment supplies the header provenance, the ownership check, and
  // the item/payment names a child diff can't carry on its own.
  useEffect(() => {
    if (!id) return
    let cancelled = false
    getConsignment(id)
      .then((c) => {
        if (cancelled) return
        setConsignment(c)
        setLookups((prev) => ({
          ...prev,
          itemLabels: new Map(
            c.items.map((it) => [it.id, it.item_name || it.item_code || `Item #${it.id}`]),
          ),
          paymentLabels: new Map(
            c.payments.map((p) => [p.id, p.bank_reference || `Payment #${p.id}`]),
          ),
        }))
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
        getConsignmentChangeHistory(id, { page, pageSize: PAGE_SIZE, includeReverted: true }),
        getConsignmentChangeHistory(id, { page: 1, pageSize: 1, includeReverted: false }),
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
      await revertConsignmentUpdate(id, entryId)
      setConfirmEntry(null)
      // Reverting writes is_reverted on the row and moves the revertable
      // entry one step back, so re-read rather than patching state locally.
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
        <PageHeader title="Consignment not found" module="importsStatus" />
        <button onClick={() => navigate('/imports-status')} className="text-sm text-accent hover:underline">
          ← Back to consignments
        </button>
      </div>
    )
  }

  // Mirrors verify_entry_ownership on the revert route.
  const mayRevert = !!user?.isAdmin
    || (consignment?.created_by_id != null && consignment.created_by_id === user?.id)

  const createdOn = consignment?.created_at
    ? DATE_FMT.format(new Date(consignment.created_at))
    : null
  const subtitle = consignment
    ? `Created by ${consignment.created_by ?? 'unknown'}${createdOn ? ` on ${createdOn}` : ''} · ${total} change${total === 1 ? '' : 's'} recorded`
    : `${total} change${total === 1 ? '' : 's'} recorded`

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted">
        <button onClick={() => navigate('/imports-status')} className="hover:underline">Consignments</button>
        {' › '}
        <button onClick={() => navigate(`/imports-status/${id}`)} className="hover:underline">{id}</button>
        {' › History'}
      </div>

      <PageHeader
        title={`Change history — Consignment #${id}`}
        subtitle={subtitle}
        module="importsStatus"
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
          <p>No changes have been recorded for this consignment yet.</p>
          <p className="text-xs">History starts building the first time this consignment is edited.</p>
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
