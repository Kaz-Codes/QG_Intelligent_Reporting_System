import { useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/features/auth/AuthContext'
import { getTruckingReadthrough } from '@/lib/truckingStatusData'
import {
  statusesFor, marketingDelay, buildRemarksFeed, canEditRemark,
  type LogisticsDraft, type LogisticsItem, type LogisticsPackage, type RemarkEntry,
} from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

function DerivedField({ label, value, derivation }: { label: string; value: string; derivation: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      <div className="flex h-10 w-full items-center rounded-lg border border-line bg-canvas-alt px-3 text-sm tabular-nums text-muted">
        {value}
      </div>
      <p className="text-xs text-muted">{derivation}</p>
    </div>
  )
}

/**
 * Step 5 — Status.
 *
 * Adds, on top of the plain status select:
 *   - a derived, read-only Marketing Delay (packing date − gate out date,
 *     falling back to − today);
 *   - a chronological remarks FEED (buildRemarksFeed) merging user-entered
 *     entries with system-generated ones from every item's RFD change log —
 *     system entries are tagged and locked to everyone except an admin, who
 *     may only edit the entry's own text/remark, never who/when/the
 *     underlying date values;
 *   - a one-way "Send to Trucking" handoff — unchecking an already-saved
 *     true value requires a distinct confirmation, since that pulls the
 *     request back out of Trucking Status;
 *   - once sent, a read-only Trucking progress panel read live from
 *     lib/truckingStatusData.ts's getTruckingReadthrough().
 */
export function Step5Status() {
  const { id } = useParams<{ id: string }>()
  const { user } = useAuth()
  const { register, control, setValue, formState: { errors } } = useFormContext<LogisticsDraft>()
  const orderType = useWatch({ control, name: 'orderType' })
  const options = statusesFor(orderType)

  const items = (useWatch({ control, name: 'items' }) ?? []) as LogisticsItem[]
  const packages = (useWatch({ control, name: 'packages' }) ?? []) as LogisticsPackage[]
  const gateOutDate = useWatch({ control, name: 'gateOutDate' })
  const remarksLog = (useWatch({ control, name: 'remarksLog' }) ?? []) as RemarkEntry[]
  const sentToTrucking = useWatch({ control, name: 'sentToTrucking' })

  const { append: appendRemark } = useFieldArray({ control, name: 'remarksLog' })

  const delay = marketingDelay(packages, gateOutDate)
  const feed = buildRemarksFeed(items, remarksLog)
  const isAdmin = canEditRemark(user?.isAdmin ? 'admin' : 'user')

  // Whether sentToTrucking was already true when the wizard loaded this
  // order — only a true→false flip on an ALREADY-SAVED handoff needs the
  // extra confirmation; toggling it on (or off before ever being saved) is a
  // normal form edit.
  const wasSentRef = useRef(sentToTrucking)

  const [newRemark, setNewRemark] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  const readthrough = id && sentToTrucking ? getTruckingReadthrough(id) : null

  function handleSentToTruckingChange(checked: boolean) {
    if (!checked && wasSentRef.current) {
      const ok = window.confirm(
        'This order was already sent to Trucking. Unchecking pulls the open request back out of Trucking Status — continue?',
      )
      if (!ok) return
      wasSentRef.current = false
    }
    if (checked) wasSentRef.current = true
    setValue('sentToTrucking', checked, { shouldDirty: true })
  }

  function addRemark() {
    if (!newRemark.trim() || !user) return
    appendRemark({
      id: `remark-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      text: newRemark.trim(),
      authoredBy: user.name,
      authoredAt: new Date().toISOString(),
      system: false,
    })
    setNewRemark('')
  }

  function startEdit(entry: RemarkEntry) {
    setEditingId(entry.id)
    setEditText(entry.text)
  }

  function saveEdit(entry: RemarkEntry) {
    if (entry.system) {
      // System entries: only the attached remark note is editable, on the
      // underlying RfdChangeEvent — never the generated summary text itself.
      for (let itemIdx = 0; itemIdx < items.length; itemIdx++) {
        const eventIdx = items[itemIdx].rfdHistory.findIndex((ev) => ev.id === entry.id)
        if (eventIdx !== -1) {
          setValue(`items.${itemIdx}.rfdHistory.${eventIdx}.remark`, editText, { shouldDirty: true })
          break
        }
      }
    } else {
      const idx = remarksLog.findIndex((r) => r.id === entry.id)
      if (idx !== -1) setValue(`remarksLog.${idx}.text`, editText, { shouldDirty: true })
    }
    setEditingId(null)
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="status">Status</Label>
          <select id="status" className={selectClass} {...register('status')}>
            <option value="">Select a status…</option>
            {options.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <p className="text-xs text-muted">
            {orderType === 'Export' ? 'Export pipeline (8 stages).' : 'Local pipeline (4 stages).'}
          </p>
          {errors.status && <p className="text-xs text-risk">{errors.status.message}</p>}
        </div>

        <DerivedField
          label="Marketing Delay (days)"
          value={delay === null ? '—' : String(delay)}
          derivation="Packing date − gate out date, or − today if no gate out date yet"
        />

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="gateOutDate">Gate Out Date <span className="font-normal text-muted">(optional)</span></Label>
          <Input id="gateOutDate" type="date" {...register('gateOutDate')} />
        </div>
      </div>

      {/* Send to Trucking handoff */}
      <section className="rounded-xl border border-line bg-surface p-4">
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            checked={!!sentToTrucking}
            onChange={(e) => handleSentToTruckingChange(e.target.checked)}
          />
          Send to Trucking
        </label>
        <p className="mt-1 text-xs text-muted">
          One-way handoff — once sent, this order becomes an open request in Trucking Status.
        </p>

        {sentToTrucking && (
          <div className="mt-3 rounded-lg border border-line bg-canvas-alt px-3 py-2.5 text-sm">
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Trucking progress</div>
            {!readthrough || !readthrough.taken ? (
              <p className="text-muted">Awaiting trucking pickup — visible as an open request in Trucking Status.</p>
            ) : (
              <div className="grid gap-1 sm:grid-cols-3">
                <div><span className="text-muted">Job:</span> {readthrough.truckingJobId}</div>
                <div><span className="text-muted">Transporter:</span> {readthrough.transporterName || '—'}</div>
                <div><span className="text-muted">Vehicles:</span> {readthrough.vehicleCount}</div>
                <div className="sm:col-span-3"><span className="text-muted">Tracking:</span> {readthrough.trackingRollupLabel}</div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Remarks feed */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Remarks
        </h3>
        <div className="space-y-2 p-4">
          {feed.length === 0 && <p className="text-sm text-muted">No remarks yet.</p>}
          {feed.map((entry) => (
            <div key={entry.id} className="rounded-lg border border-line bg-canvas-alt/40 p-3 text-sm">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                {entry.system && (
                  <span className="rounded bg-[var(--color-info-bg)] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-info)]">
                    System
                  </span>
                )}
                <span>{entry.authoredBy}</span>
                <span>·</span>
                <span>{new Date(entry.authoredAt).toLocaleString()}</span>
                {isAdmin && editingId !== entry.id && (
                  <button type="button" className="ml-auto text-[11px] text-brand hover:underline" onClick={() => startEdit(entry)}>
                    Edit
                  </button>
                )}
              </div>

              {editingId === entry.id ? (
                <div className="flex items-center gap-2">
                  <input
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    className="h-8 w-full rounded border border-line bg-surface px-2 text-sm"
                  />
                  <button type="button" className="text-xs text-brand hover:underline" onClick={() => saveEdit(entry)}>Save</button>
                  <button type="button" className="text-xs text-muted hover:underline" onClick={() => setEditingId(null)}>Cancel</button>
                </div>
              ) : (
                <p className="text-ink">{entry.text}</p>
              )}
            </div>
          ))}

          <div className="flex items-center gap-2 pt-1">
            <input
              value={newRemark}
              onChange={(e) => setNewRemark(e.target.value)}
              placeholder="Add a remark…"
              className="h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm"
            />
            <button
              type="button"
              onClick={addRemark}
              className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-muted"
            >
              Add
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
