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
  getTruckingJob, getTruckingChangeHistory, revertTruckingUpdate,
  type ApiTruckingJob, type ApiTruckingHistoryEntry,
} from '@/lib/api/trucking'
import {
  apiToChangeHistoryEntry, EMPTY_LOOKUPS, type TruckingHistoryLookups,
} from '@/lib/api/truckingChangeHistoryMap'
import type { ChangeHistoryEntry } from '@/lib/changeHistory'

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: '2-digit' })
const PAGE_SIZE = 5

/**
 * Trucking Status — change history, wired to the live backend.
 *
 * GET /trucking/change-history/{id} for the list,
 * PUT /trucking/revert-update/{id}/{hid} to undo one change.
 *
 * Entries only exist for EDITS: creating a job writes no history row, and the
 * 399 jobs loaded from the workbooks have none until someone edits them, so an
 * empty history here is normal rather than a failure.
 *
 * Revertability and permission are both server-truthful, for the same reasons
 * as imports and logistics: the backend only allows reverting the newest
 * not-yet-reverted entry (asked for directly, since a paginated page can't
 * answer it), and the route checks ownership of the JOB, not of the history row.
 */
export function TruckingChangeHistory() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [job, setJob] = useState<ApiTruckingJob | null>(null)
  const [rawEntries, setRawEntries] = useState<ApiTruckingHistoryEntry[]>([])
  const [lookups, setLookups] = useState<TruckingHistoryLookups>(EMPTY_LOOKUPS)
  const [revertableId, setRevertableId] = useState<string | null>(null)

  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [pageCount, setPageCount] = useState(1)

  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revertingId, setRevertingId] = useState<string | null>(null)
  const [confirmEntry, setConfirmEntry] = useState<ChangeHistoryEntry | null>(null)

  // The job supplies the header provenance, the ownership check, and the
  // vehicle labels a diff can't carry (it only has row ids).
  useEffect(() => {
    if (!id) return
    let cancelled = false
    getTruckingJob(id)
      .then((j) => {
        if (cancelled) return
        setJob(j)
        setLookups({
          vehicleLabels: new Map(
            j.vehicles.map((v) => [v.id, v.vehicle_number || v.vehicle_type || `Vehicle #${v.id}`]),
          ),
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
        getTruckingChangeHistory(id, { page, pageSize: PAGE_SIZE, includeReverted: true }),
        getTruckingChangeHistory(id, { page: 1, pageSize: 1, includeReverted: false }),
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
      await revertTruckingUpdate(id, entryId)
      setConfirmEntry(null)
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
        <PageHeader title="Trucking job not found" module="truckingStatus" />
        <button onClick={() => navigate('/trucking-status')} className="text-sm text-accent hover:underline">
          ← Back to trucking
        </button>
      </div>
    )
  }

  // Mirrors verify_entry_ownership on the revert route.
  const mayRevert = !!user?.isAdmin
    || (job?.created_by_id != null && job.created_by_id === user?.id)

  const createdOn = job?.created_at ? DATE_FMT.format(new Date(job.created_at)) : null
  const label = job?.reference_no || `#${id}`
  const subtitle = job
    ? `Created by ${job.created_by ?? 'unknown'}${createdOn ? ` on ${createdOn}` : ''} · ${total} change${total === 1 ? '' : 's'} recorded`
    : `${total} change${total === 1 ? '' : 's'} recorded`

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted">
        <button onClick={() => navigate('/trucking-status')} className="hover:underline">Trucking Status</button>
        {' › '}
        <button onClick={() => navigate(`/trucking-status/${id}`)} className="hover:underline">{label}</button>
        {' › History'}
      </div>

      <PageHeader
        title={`Change history — ${label}`}
        subtitle={subtitle}
        module="truckingStatus"
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
          <p>No changes have been recorded for this job yet.</p>
          <p className="text-xs">History starts building the first time this job is edited.</p>
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
