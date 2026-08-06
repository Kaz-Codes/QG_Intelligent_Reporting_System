import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'

/**
 * No dialog/modal primitive exists in components/ui/ yet (just button, card,
 * input, label) — this is a minimal, dependency-free one, local to the
 * feature rather than promoted to components/ui/ since it's only used by the
 * two status wizards so far.
 */
export function UnsavedChangesDialog({
  open, onSaveAndMove, onDiscardAndMove, onCancel,
}: {
  open: boolean
  onSaveAndMove: () => void
  onDiscardAndMove: () => void
  onCancel: () => void
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    panelRef.current?.focus()
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCancel}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="unsaved-changes-title"
        aria-describedby="unsaved-changes-desc"
        tabIndex={-1}
        className="w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-lg focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="unsaved-changes-title" className="font-display text-base font-bold text-navy">
          Unsaved changes
        </h2>
        <p id="unsaved-changes-desc" className="mt-1.5 text-sm text-muted">
          You have unsaved changes on this step. What would you like to do?
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <Button onClick={onSaveAndMove}>Save and move</Button>
          <Button variant="outline" onClick={onDiscardAndMove}>Move without saving</Button>
          <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        </div>
      </div>
    </div>
  )
}
