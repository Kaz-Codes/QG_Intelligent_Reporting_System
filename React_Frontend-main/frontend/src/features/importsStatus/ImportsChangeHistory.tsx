import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { History } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { usePagination, Pagination } from '@/components/Pagination'
import { ChangeHistoryCard } from '@/components/changeHistory/ChangeHistoryCard'
import { RevertConfirmDialog } from '@/components/changeHistory/RevertConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import {
  getConsignmentChangeHistory, getRecordProvenance, revertChangeHistoryEntry,
} from '@/lib/importsChangeHistory'
import { isRevertable, type ChangeHistoryEntry } from '@/lib/changeHistory'

const DATE_FMT = new Intl.DateTimeFormat('en-US', { day: 'numeric', month: 'short', year: '2-digit' })

/**
 * Imports Status — change history.
 *
 * FRONTEND-ONLY for now: reads from lib/importsChangeHistory.ts's mock engine,
 * not the real GET /consignments/change-history/{id} endpoint (which already
 * exists and is shaped identically — see that file's header comment for the
 * field-by-field mapping this will need when it's wired up).
 *
 * One card per change, newest first, collapsed to a summary by default.
 * Revert is enabled on exactly one card at a time — the newest not-yet-
 * reverted entry — mirroring the backend's own LIFO undo rule; every other
 * card explains why its button is disabled rather than hiding it, so the rule
 * is visible, not just enforced silently.
 */
export function ImportsChangeHistory() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  // Local re-render trigger: the data layer mutates its own cache in place on
  // revert (see revertChangeHistoryEntry), so bump this to re-read it.
  const [, forceRefresh] = useState(0)
  const [revertingId, setRevertingId] = useState<string | null>(null)
  // The entry awaiting confirmation — null/undefined means the dialog is
  // closed. Only one entry is ever revertable at a time, so one dialog
  // instance at page level (rather than one per card) is enough.
  const [confirmEntry, setConfirmEntry] = useState<ChangeHistoryEntry | null>(null)

  if (!id) return null

  const entries = getConsignmentChangeHistory(id)
  const provenance = getRecordProvenance(id)
  const { page, pageCount, pageRows, setPage, total, pageSize } = usePagination(entries, 5)

  async function handleRevert(entryId: string) {
    setRevertingId(entryId)
    // No backend yet — the small delay is only so "Reverting…" is visible
    // rather than an instant flicker, matching how this will feel once wired.
    await new Promise((r) => setTimeout(r, 300))
    revertChangeHistoryEntry(id!, entryId, user?.username ?? 'you')
    setRevertingId(null)
    setConfirmEntry(null)
    forceRefresh((n) => n + 1)
  }

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
        subtitle={`Created by ${provenance.createdBy} on ${DATE_FMT.format(new Date(provenance.createdAt))} · ${total} change${total === 1 ? '' : 's'} recorded`}
        module="importsStatus"
      />

      <p className="rounded-lg border border-line bg-canvas-alt/50 px-3 py-2 text-xs text-muted">
        Only the most recent change can be reverted at a time — reverting steps back one edit, oldest available
        change last. Reverted entries stay listed, greyed out, for the record.
      </p>

      {entries.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line px-3 py-12 text-center text-muted">
          <History size={28} />
          <p>No changes have been recorded for this consignment yet.</p>
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
