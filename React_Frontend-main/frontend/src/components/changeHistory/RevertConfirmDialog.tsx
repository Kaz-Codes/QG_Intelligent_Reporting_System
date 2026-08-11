import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import type { ChangeHistoryEntry } from '@/lib/changeHistory'

/**
 * Confirms a revert before it happens — reverting can't be undone (there's no
 * "revert the revert"; the next edit simply starts a new, separate history
 * entry), so this is a deliberate stop, not a rubber stamp. Same minimal,
 * dependency-free dialog shape as the wizards' UnsavedChangesDialog (no shared
 * dialog primitive exists in components/ui/ yet), placed alongside
 * ChangeHistoryCard since all three status modules share one instance of it.
 */
export function RevertConfirmDialog({
  entry, onConfirm, onCancel, confirming,
}: {
  /** null/undefined = closed. */
  entry: ChangeHistoryEntry | null | undefined
  onConfirm: () => void
  onCancel: () => void
  confirming?: boolean
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const open = !!entry

  useEffect(() => {
    if (!open) return
    panelRef.current?.focus()
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  if (!entry) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="revert-confirm-title"
        aria-describedby="revert-confirm-desc"
        tabIndex={-1}
        className="w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-lg focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="revert-confirm-title" className="font-display text-base font-bold text-navy">
          Revert this change?
        </h2>
        <p id="revert-confirm-desc" className="mt-1.5 text-sm text-muted">
          This puts back the values from before <span className="font-medium text-ink">{entry.changedBy}</span>'s
          change — every field, item and payment it touched. <span className="font-medium text-risk">This
          cannot be undone.</span> A later edit would start a new, separate history entry; it would not bring
          this one back.
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <Button
            onClick={onConfirm}
            disabled={confirming}
            className="border-[var(--color-risk)] bg-[var(--color-risk)] text-white hover:bg-[var(--color-risk)]/90"
          >
            {confirming ? 'Reverting…' : 'Yes, revert it'}
          </Button>
          <Button variant="ghost" onClick={onCancel} disabled={confirming}>Cancel</Button>
        </div>
      </div>
    </div>
  )
}
