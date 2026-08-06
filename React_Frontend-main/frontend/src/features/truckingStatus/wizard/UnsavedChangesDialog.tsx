import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'

/**
 * Minimal local dialog — no modal primitive exists in components/ui/, and adding
 * a dependency (Radix etc.) needs coordinating with Imad, so this is a small
 * self-contained one: role="dialog", Escape-to-cancel, focus-on-open. Claude
 * Code should reconcile this with the equivalent already added to
 * importsStatus/logisticsStatus so all three share one component if practical.
 */
export function UnsavedChangesDialog({
  open,
  onSaveAndMove,
  onMoveWithout,
  onCancel,
}: {
  open: boolean
  onSaveAndMove: () => void
  onMoveWithout: () => void
  onCancel: () => void
}) {
  // `Button` (components/ui/button.tsx) is a plain function component, not
  // wrapped in React.forwardRef, so a ref can't attach to it directly (this
  // is the same fix applied in importsStatus/logisticsStatus's copy of this
  // dialog) — focus the panel itself instead of a specific button.
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    panelRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
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
        aria-labelledby="unsaved-title"
        tabIndex={-1}
        className="w-full max-w-md rounded-xl border border-line bg-surface p-6 shadow-lg focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="unsaved-title" className="text-base font-semibold text-ink">
          Unsaved changes
        </h2>
        <p className="mt-2 text-sm text-muted">
          You've edited this step. Save your changes before moving, or move without saving?
        </p>
        <div className="mt-6 flex flex-wrap justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="button" variant="outline" onClick={onMoveWithout}>
            Move without saving
          </Button>
          <Button type="button" onClick={onSaveAndMove}>
            Save and move
          </Button>
        </div>
      </div>
    </div>
  )
}
