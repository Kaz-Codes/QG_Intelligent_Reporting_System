import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/components/ui/button'

/**
 * Generic confirm-before-acting modal — same shape as
 * changeHistory/RevertConfirmDialog (no shared dialog primitive exists in
 * components/ui/ yet), lifted out so any "are you sure?" prompt can use a
 * real dialog instead of the browser's window.confirm.
 *
 *
 * PORTALLED TO document.body, AND THAT IS LOAD-BEARING.
 *
 * `position: fixed` and `z-50` are NOT enough on their own. z-index is only
 * ever compared within a stacking context, so a dialog rendered inside one
 * competes only with that context's own children — however large its number.
 *
 * It broke exactly that way: the chatbot's delete prompt is rendered from
 * inside the conversation sidebar, whose <aside> is `position: sticky`, and
 * sticky ALWAYS creates a stacking context (no z-index needed). The dialog's
 * z-50 was therefore sealed inside the aside, the aside is z-index:auto, and
 * the Assistant's empty state — `relative`, also auto, but LATER in the DOM —
 * painted over the whole subtree. The 210px Qadri logo landed on top of the
 * dialog text and its Cancel button.
 *
 * Raising the number would have fixed that one case and nothing else: it was
 * never a contest the dialog could win from in there. A portal moves the node
 * to document.body, so it is laid out against the root stacking context and
 * escapes every ancestor's stacking context AND every ancestor's
 * `overflow: hidden` at the same time — the sidebar has that too.
 *
 * Same reasoning, and the same `createPortal(..., document.body)` idiom, as
 * MetricInfo and the two filter popovers.
 */
export function ConfirmDialog({
  open, title, description, confirmLabel, confirmingLabel, confirming, danger, onConfirm, onCancel,
  secondaryLabel, onSecondary,
}: {
  open: boolean
  title: string
  description: React.ReactNode
  confirmLabel: string
  confirmingLabel?: string
  confirming?: boolean
  /** Red confirm button for destructive/hard-to-reverse actions (default) vs.
   *  the normal accent button for a routine confirmation. */
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
  /** Optional middle action (e.g. "Move without saving"). Backward-compatible:
   *  when omitted, the dialog renders exactly as before. */
  secondaryLabel?: string
  onSecondary?: () => void
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

  return createPortal(
    // The backdrop is also the click-away target: anywhere outside the panel
    // cancels, which the panel's own stopPropagation below keeps from firing
    // on a click inside it. It dims the page as well, so a busy background —
    // the Assistant's watermark, a dense table — is suppressed rather than
    // competing with the dialog's text.
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-desc"
        tabIndex={-1}
        className="w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-lg focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="font-display text-base font-bold text-navy">
          {title}
        </h2>
        <p id="confirm-dialog-desc" className="mt-1.5 text-sm text-muted">
          {description}
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <Button
            onClick={onConfirm}
            disabled={confirming}
            className={danger === false ? undefined : 'border-[var(--color-risk)] bg-[var(--color-risk)] text-white hover:bg-[var(--color-risk)]/90'}
          >
            {confirming ? (confirmingLabel ?? 'Working…') : confirmLabel}
          </Button>
          {secondaryLabel && onSecondary && (
            <Button variant="outline" onClick={onSecondary} disabled={confirming}>{secondaryLabel}</Button>
          )}
          <Button variant="ghost" onClick={onCancel} disabled={confirming}>Cancel</Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
