import { useState } from 'react'
import { Trash2, Undo2, Loader2 } from 'lucide-react'

/**
 * Delete and undo-delete, as a pair of icon buttons on a list row.
 *
 * ONE COMPONENT FOR ALL THREE MODULES. Imports, logistics and trucking share
 * the same soft-delete model — `is_deleted` flips, the row keeps its id, its
 * children and its change history — so they should share the same control.
 * Three hand-written copies would drift, and the one that drifted would be the
 * one nobody noticed until it deleted something it should not have.
 *
 * WHY DELETE ASKS AND UNDO DOES NOT. Deleting is the destructive direction:
 * cheap to do, and on a long list very easy to do to the wrong row. So it
 * takes two clicks, the second one labelled with what is about to happen.
 * Undo only puts a record back — the worst case is that you see a row you did
 * not want to see, and clicking delete again costs nothing.
 *
 * ADMIN ONLY, and the caller decides that: this component is simply not
 * rendered for anyone else. Note that is a UI decision, NOT the security
 * boundary — the backend gates these endpoints on `can_delete_*` plus
 * entry-ownership, so a non-admin holding that permission can still call them
 * directly. See the note in CLAUDE.md.
 */

export function RowDeleteActions({
  isDeleted, busy, label, onDelete, onUndo,
}: {
  isDeleted: boolean
  /** Disables both buttons and shows a spinner while a call is in flight. */
  busy?: boolean
  /** What is being deleted, for the confirm prompt: "consignment 2739". */
  label: string
  onDelete: () => void
  onUndo: () => void
}) {
  const [confirming, setConfirming] = useState(false)

  if (busy) {
    return (
      <span className="inline-flex h-7 w-7 items-center justify-center text-muted">
        <Loader2 size={14} className="animate-spin" />
      </span>
    )
  }

  // A deleted row offers only the way back.
  if (isDeleted) {
    return (
      <button
        type="button"
        onClick={onUndo}
        title={`Restore ${label}`}
        aria-label={`Restore ${label}`}
        className="inline-flex h-7 w-7 items-center justify-center rounded border border-[var(--color-healthy)] text-[var(--color-healthy)] transition-colors hover:bg-[var(--color-healthy-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
      >
        <Undo2 size={14} />
      </button>
    )
  }

  // Second click confirms. The button says what it will do, rather than
  // relying on a dialog the eye skips past.
  if (confirming) {
    return (
      <span className="inline-flex items-center gap-1">
        <button
          type="button"
          onClick={() => { setConfirming(false); onDelete() }}
          className="rounded border border-[var(--color-risk)] bg-[var(--color-risk-bg)] px-2 py-1 text-[11px] font-semibold text-[var(--color-risk)]"
        >
          Delete?
        </button>
        <button
          type="button"
          onClick={() => setConfirming(false)}
          className="rounded border border-line px-2 py-1 text-[11px] text-muted hover:border-muted"
        >
          No
        </button>
      </span>
    )
  }

  return (
    <button
      type="button"
      onClick={() => setConfirming(true)}
      title={`Delete ${label}`}
      aria-label={`Delete ${label}`}
      className="inline-flex h-7 w-7 items-center justify-center rounded border border-line text-muted transition-colors hover:border-[var(--color-risk)] hover:text-[var(--color-risk)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
    >
      <Trash2 size={14} />
    </button>
  )
}

/**
 * The row treatment for a deleted record.
 *
 * Struck through and dimmed, so a deleted row is unmistakable in a list it
 * shares with live ones — without hiding it, which would put the undo button
 * out of reach.
 */
export const DELETED_ROW_CLASS = 'opacity-55 line-through decoration-[var(--color-risk)]/60'
