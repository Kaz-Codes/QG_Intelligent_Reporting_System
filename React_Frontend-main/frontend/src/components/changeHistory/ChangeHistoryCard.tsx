import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import type { ChangeHistoryEntry, FieldDiff } from '@/lib/changeHistory'

/**
 * One change-history entry, collapsed to a summary row by default with a
 * chevron to expand the full field-by-field diff — same "click the row to
 * expand" language as Disclosure (components/Disclosure.tsx), just with a
 * richer header than that component's plain string title (who / when / a
 * revert-status pill / the Revert button all need to sit there).
 *
 * A reverted entry is greyed out and its Revert button disappears entirely —
 * reverting an already-reverted change isn't a real action, so there's
 * nothing to offer. The single revertable entry (the newest, not-yet-reverted
 * one — see lib/changeHistory.ts's isRevertable) gets a live button; every
 * other active entry shows a disabled one with a tooltip explaining why,
 * matching the disabled-button-with-tooltip pattern used elsewhere (e.g. the
 * locked-record Edit button on the Imports detail page).
 */

const DATE_FMT = new Intl.DateTimeFormat('en-US', {
  day: 'numeric', month: 'short', year: '2-digit', hour: 'numeric', minute: '2-digit',
})

function formatWhen(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(+d) ? '—' : DATE_FMT.format(d)
}

function RevertStatusPill({ reverted }: { reverted: boolean }) {
  if (reverted) {
    return (
      <span className="inline-flex items-center rounded-full border border-line bg-canvas-alt px-2 py-0.5 text-[11px] font-medium text-muted">
        Reverted
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium"
      style={{ backgroundColor: 'var(--color-healthy-bg)', color: 'var(--color-healthy)', borderColor: 'var(--color-healthy)' }}
    >
      Active
    </span>
  )
}

function FieldDiffTable({ fields }: { fields: FieldDiff[] }) {
  return (
    <table className="w-full text-[12.5px]">
      <thead className="text-left text-[10.5px] uppercase tracking-wide text-muted">
        <tr>
          <th className="w-1/3 py-1 pr-2 font-medium">Field</th>
          <th className="py-1 pr-2 font-medium">Old value</th>
          <th className="py-1 font-medium">New value</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f.field} className="border-t border-line/60">
            <td className="py-1.5 pr-2 text-ink">{f.label}</td>
            <td className="py-1.5 pr-2 text-muted line-through decoration-muted/50">{f.oldValue || '—'}</td>
            <td className="py-1.5 font-medium text-ink">{f.newValue || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ChangeHistoryCard({
  entry, revertable, canRevert, onRevert, reverting,
}: {
  entry: ChangeHistoryEntry
  /** This is the single newest not-yet-reverted entry — the only one the
   *  backend's LIFO rule would actually allow reverting. */
  revertable: boolean
  /** Admin, or the person who made this change. */
  canRevert: boolean
  onRevert: () => void
  reverting?: boolean
}) {
  const [open, setOpen] = useState(false)

  const touchedSections = entry.sections.filter((s) => s.fields.length > 0)
  const touchedCollections = entry.collections.filter(
    (c) => c.updated.length || c.added.length || c.removed.length,
  )
  const changeCount =
    touchedSections.reduce((n, s) => n + s.fields.length, 0) +
    touchedCollections.reduce((n, c) => n + c.updated.length + c.added.length + c.removed.length, 0)

  const disabledReason = entry.isReverted
    ? null // button isn't shown at all once reverted
    : !revertable
      ? 'Only the most recent change can be reverted — revert that one first.'
      : !canRevert
        ? 'Only an admin or the person who made this change can revert it.'
        : null

  return (
    <div
      className={`rounded-xl border border-line bg-surface transition-opacity ${entry.isReverted ? 'opacity-60' : ''}`}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <ChevronRight size={16} className={`shrink-0 text-muted transition-transform ${open ? 'rotate-90' : ''}`} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink">{entry.changedBy}</span>
            <span className="text-xs text-muted">{formatWhen(entry.changedAt)}</span>
            <RevertStatusPill reverted={entry.isReverted} />
          </div>
          <div className="mt-0.5 text-[11.5px] text-muted">
            {changeCount} field{changeCount === 1 ? '' : 's'} changed
            {entry.isReverted && entry.revertedBy && (
              <> · reverted by <span className="text-ink/70">{entry.revertedBy}</span> on {formatWhen(entry.revertedAt!)}</>
            )}
          </div>
        </div>

        {!entry.isReverted && (
          <span onClick={(e) => e.stopPropagation()} title={disabledReason ?? undefined}>
            <button
              type="button"
              onClick={onRevert}
              disabled={!!disabledReason || reverting}
              className={`shrink-0 rounded border px-2.5 py-1 text-[11px] font-medium ${
                disabledReason || reverting
                  ? 'cursor-not-allowed border-line text-muted opacity-60'
                  : 'border-[var(--color-risk)] text-[var(--color-risk)] hover:bg-[var(--color-risk-bg)]'
              }`}
            >
              {reverting ? 'Reverting…' : 'Revert'}
            </button>
          </span>
        )}
      </button>

      {open && (
        <div className="space-y-3 border-t border-line px-4 py-3">
          {changeCount === 0 && (
            <p className="text-xs italic text-muted">No field-level changes recorded for this entry.</p>
          )}

          {touchedSections.map((s) => (
            <div key={s.key}>
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted">{s.label}</div>
              <FieldDiffTable fields={s.fields} />
            </div>
          ))}

          {touchedCollections.map((c) => (
            <div key={c.key}>
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted">{c.label}</div>
              <div className="space-y-2">
                {c.updated.map((row) => (
                  <div key={row.id} className="rounded-lg border border-line/60 bg-canvas-alt/40 p-2">
                    <div className="mb-1 text-[11.5px] font-medium text-ink">{row.label} changed</div>
                    <FieldDiffTable fields={row.changes} />
                  </div>
                ))}
                {c.added.map((row) => (
                  <div key={row.id} className="rounded-lg border border-[var(--color-healthy)]/30 bg-[var(--color-healthy-bg)] px-2.5 py-1.5 text-[12px] text-[var(--color-healthy)]">
                    + {row.label} added — {row.summary}
                  </div>
                ))}
                {c.removed.map((row) => (
                  <div key={row.id} className="rounded-lg border border-[var(--color-risk)]/30 bg-[var(--color-risk-bg)] px-2.5 py-1.5 text-[12px] text-[var(--color-risk)]">
                    − {row.label} removed — {row.summary}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
