import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { History } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { usePagination, Pagination } from '@/components/Pagination'
import { ChangeHistoryCard } from '@/components/changeHistory/ChangeHistoryCard'
import { RevertConfirmDialog } from '@/components/changeHistory/RevertConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { getTruckingJobs } from '@/lib/truckingStatusData'
import {
  getJobChangeHistory, getRecordProvenance, revertChangeHistoryEntry,
} from '@/lib/truckingChangeHistory'
import { isRevertable, type ChangeHistoryEntry } from '@/lib/changeHistory'

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: '2-digit' })

/**
 * Trucking Status — change history. FRONTEND-ONLY for now — see
 * ImportsChangeHistory.tsx (the identical pattern) for the real-endpoint
 * mapping this will need once wired up; trucking's own change-history routes
 * already exist server-side in the same shape.
 */
export function TruckingChangeHistory() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [, forceRefresh] = useState(0)
  const [revertingId, setRevertingId] = useState<string | null>(null)
  const [confirmEntry, setConfirmEntry] = useState<ChangeHistoryEntry | null>(null)

  if (!id) return null

  const job = getTruckingJobs().find((r) => r.systemId === id)
  const entries = getJobChangeHistory(id)
  const provenance = getRecordProvenance(id)
  const { page, pageCount, pageRows, setPage, total, pageSize } = usePagination(entries, 5)

  async function handleRevert(entryId: string) {
    setRevertingId(entryId)
    await new Promise((r) => setTimeout(r, 300))
    revertChangeHistoryEntry(id!, entryId, user?.username ?? 'you')
    setRevertingId(null)
    setConfirmEntry(null)
    forceRefresh((n) => n + 1)
  }

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted">
        <button onClick={() => navigate('/trucking-status')} className="hover:underline">Trucking Status</button>
        {' › '}
        <button onClick={() => navigate(`/trucking-status/${id}`)} className="hover:underline">{id}</button>
        {' › History'}
      </div>

      <PageHeader
        title={`Change history — ${id}${job?.transporterName ? ` · ${job.transporterName}` : ''}`}
        subtitle={`Created by ${provenance.createdBy} on ${DATE_FMT.format(new Date(provenance.createdAt))} · ${total} change${total === 1 ? '' : 's'} recorded`}
        module="truckingStatus"
      />

      <p className="rounded-lg border border-line bg-canvas-alt/50 px-3 py-2 text-xs text-muted">
        Only the most recent change can be reverted at a time — reverting steps back one edit, oldest available
        change last. Reverted entries stay listed, greyed out, for the record.
      </p>

      {entries.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line px-3 py-12 text-center text-muted">
          <History size={28} />
          <p>No changes have been recorded for this job yet.</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {pageRows.map((entry) => (
            <ChangeHistoryCard
              key={entry.id}
              entry={entry}
              revertable={isRevertable(entries, entry)}
              canRevert={!!user?.isAdmin || user?.username === entry.changedById}
              reverting={revertingId === entry.id}
              onRevert={() => setConfirmEntry(entry)}
            />
          ))}
        </div>
      )}

      <Pagination page={page} pageCount={pageCount} total={total} pageSize={pageSize} onPage={setPage} />

      <RevertConfirmDialog
        entry={confirmEntry}
        confirming={!!confirmEntry && revertingId === confirmEntry.id}
        onConfirm={() => confirmEntry && void handleRevert(confirmEntry.id)}
        onCancel={() => setConfirmEntry(null)}
      />
    </div>
  )
}
