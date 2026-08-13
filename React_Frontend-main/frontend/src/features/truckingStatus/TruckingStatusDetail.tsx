import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  freightSavings,
  ratePerKg,
  totalGrossWeight,
  totalNetWeight,
  outstanding,
  trackingRollup,
} from './schema'
import { ApiError } from '@/lib/api/client'
import {
  getTruckingJob, submitTruckingJob, reopenTruckingJob, parseSubmitErrors,
} from '@/lib/api/trucking'
import { apiToRow, sourceLabel, type TruckingListRow } from '@/lib/api/truckingMap'

const rs = (v?: number | null) => (v === undefined || v === null ? '—' : `Rs. ${Math.round(v).toLocaleString('en-US')}`)

/** ETA-to-works delay: overdue if today is past etaWorks and the job is moving. */
function delayDays(r: TruckingListRow): number | null {
  if (!r.etaWorks || !r.dispatchNoteDate) return null
  const eta = new Date(r.etaWorks).getTime()
  const today = new Date(new Date().toISOString().slice(0, 10)).getTime()
  if (Number.isNaN(eta)) return null
  return Math.round((today - eta) / 86_400_000)
}

export function TruckingStatusDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [row, setRow] = useState<TruckingListRow | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [reopening, setReopening] = useState(false)
  const [confirmReopen, setConfirmReopen] = useState(false)
  const [submitErrors, setSubmitErrors] = useState<string[] | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    setNotFound(false)
    try {
      setRow(apiToRow(await getTruckingJob(id)))
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true)
      else setError(err instanceof Error ? err.message : 'Could not load this job')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])

  async function handleSubmit() {
    if (!row) return
    setSubmitting(true)
    setError(null)
    setSubmitErrors(null)
    try {
      await submitTruckingJob(row.id)
      await load()
    } catch (err) {
      if (err instanceof ApiError) {
        const parsed = parseSubmitErrors(err.detail)
        if (parsed) { setSubmitErrors(parsed.errors); return }
      }
      setError(err instanceof Error ? err.message : 'Could not submit this job')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleReopen() {
    if (!row) return
    setConfirmReopen(false)
    setReopening(true)
    setError(null)
    try {
      await reopenTruckingJob(row.id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reopen this job')
    } finally {
      setReopening(false)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Loading job…" module="truckingStatus" />
      </div>
    )
  }

  if (notFound || !row) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={`Trucking Job ${id}`} subtitle="Detail view" module="truckingStatus" />
        <Card>
          <CardContent className="flex h-40 flex-col items-center justify-center gap-2 text-muted">
            <span>No trucking job found for {id}.</span>
            {error && <span className="text-risk">{error}</span>}
            <button onClick={() => navigate('/trucking-status')} className="text-sm text-accent hover:underline">
              ← Back to trucking
            </button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // A closed job is locked for everyone; only an admin can reopen it.
  const canEdit = (can(user, 'editAny') || can(user, 'editOwnDraft')) && !row.isLocked
  const submittable = canEdit && row.recordState !== 'submitted'
  const submitBlocked = row.missingFields.length > 0

  const gross = totalGrossWeight(row.vehicles)
  const net = totalNetWeight(row.vehicles)
  const savings = freightSavings(row.quotedFreight, row.actualFreight)
  const rate = ratePerKg(row.actualFreight, gross)
  const out = outstanding(row.actualFreight, row.paidAmount)
  const rollup = trackingRollup(row.vehicles)
  const delay = delayDays(row)

  // Map the source back to its home record so the user can jump to it.
  const sourceHref =
    row.sourceRef && row.source === 'from-logistics'
      ? `/logistics-status/${row.sourceRef}`
      : row.sourceRef && row.source === 'from-import-fob'
        ? `/imports-status/${row.sourceRef}`
        : null

  return (
    <div className="flex flex-col gap-4 pb-16">
      <div className="text-xs text-muted">
        <button onClick={() => navigate('/trucking-status')} className="hover:underline">Trucking Status</button>
        {' › '}{row.systemId}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title={`Trucking Job ${row.systemId}`}
          subtitle={`${row.movementType || 'Movement not set'} · ${sourceLabel(row.source)}`}
          module="truckingStatus"
        />
        <div className="flex flex-wrap items-center gap-3">
          {/* Job-level tracking is a ROLLUP over the vehicles, never stored. */}
          {row.vehicles.length > 0 && <StatusBadge label={rollup.label} />}
          <span className={`rounded border px-1.5 py-0.5 text-[11px] ${row.recordState === 'submitted'
            ? 'border-line text-muted'
            : 'border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] text-[var(--color-watch)]'}`}>
            {row.recordState === 'submitted' ? 'Submitted' : 'Draft'}
          </span>
          {row.isLocked && (
            <span className="rounded border border-line px-1.5 py-0.5 text-[11px] text-muted"
              title="All vehicles delivered and submitted — an admin must reopen it before editing">
              Closed
            </span>
          )}
          {row.isLocked && user?.isAdmin && (
            <Button variant="outline" onClick={() => setConfirmReopen(true)} disabled={reopening}>
              {reopening ? 'Reopening…' : 'Reopen'}
            </Button>
          )}
          {submittable && (
            <Button
              variant="outline"
              onClick={() => void handleSubmit()}
              disabled={submitting || submitBlocked}
              title={submitBlocked ? `Missing: ${row.missingFields.join(', ')}` : undefined}
            >
              {submitting ? 'Submitting…' : 'Submit'}
            </Button>
          )}
          {canEdit && (
            <Button asChild variant="outline">
              <Link to={`/trucking-status/${row.id}/edit/1`}>Edit</Link>
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">
          <span>{error}</span>
          <button type="button" onClick={() => void load()} className="underline">Retry</button>
        </div>
      )}

      {submitErrors && submitErrors.length > 0 && (
        <div className="rounded-lg bg-risk-bg px-3 py-2.5 text-sm text-risk">
          <p className="font-medium">This job can’t be submitted yet:</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {submitErrors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      {row.isLocked && (
        <div className="rounded-lg border border-line bg-canvas-alt px-3.5 py-2.5 text-sm text-muted">
          This job is closed. An admin must reopen it before it can be edited.
        </div>
      )}

      {/* provenance banner */}
      {row.takenAt && (
        <div className="rounded-lg border border-line bg-canvas-alt px-4 py-3 text-sm text-muted">
          Taken from {sourceLabel(row.source)} order{' '}
          {sourceHref ? <Link to={sourceHref} className="text-brand hover:underline">{row.sourceRef}</Link> : row.sourceRef}
          {' '}on {new Date(row.takenAt).toLocaleString()}. This job is now independent — it no longer updates from its source.
        </div>
      )}

      {/* key figures */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-3 lg:grid-cols-6">
        <KeyFigure label="Vehicles" value={String(row.vehicles.length)} sub={rollup.label} />
        <KeyFigure label="Gross weight" value={`${gross.toFixed(0)} kg`} sub={`${net.toFixed(0)} kg net`} />
        <KeyFigure label="Actual freight" value={rs(row.actualFreight)} sub={rate != null ? `Rs. ${rate.toFixed(2)}/kg` : 'rate n/a'} />
        <KeyFigure label="Outstanding" value={rs(out)} sub={row.paymentStatus ?? '—'} warn={!!out && out > 0} />
        <KeyFigure
          label="ETA to works" value={row.etaWorks || '—'}
          sub={delay === null ? 'no ETA' : delay <= 0 ? (delay === 0 ? 'due today' : `${-delay}d left`) : `${delay}d overdue`}
          warn={delay !== null && delay > 0}
        />
        <KeyFigure label="Execution" value={row.executionDate || '—'} sub={row.transporterName ?? '—'} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Movement">
          <Row label="Execution date" value={row.executionDate} />
          <Row label="Transporter" value={row.transporterName} />
          <Row label="Shifting type" value={row.shiftingType} />
          <Row label="Dispatch note date" value={row.dispatchNoteDate} />
          <Row label="ETA to works" value={row.etaWorks} />
          <div className="pt-2">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Items</div>
            {(row.items?.length ?? 0) === 0 ? (
              <div className="text-sm text-muted">{row.itemDetails || 'No items entered.'}</div>
            ) : (
              <ul className="flex flex-col gap-1">
                {row.items!.map((it, i) => (
                  <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                    <span className="font-medium">{it.itemDetails || <span className="italic text-muted">Unnamed item</span>}</span>
                    {(it.quantity != null || it.uom) && (
                      <span className="text-xs text-muted tabular-nums">
                        {it.quantity ?? '—'}{it.uom ? ` ${it.uom}` : ''}
                      </span>
                    )}
                    {row.movementType !== 'Intrafactory' && it.referenceNo && (
                      <span className="text-xs text-muted">· IDM {it.referenceNo}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>

        <Section title="Freight & Payment">
          <Row label="Quoted freight" value={rs(row.quotedFreight)} />
          <Row label="Actual freight" value={rs(row.actualFreight)} />
          <Row label="Savings vs. quote" value={savings != null ? rs(savings) : undefined} />
          <Row label="Rate per kg" value={rate != null ? `Rs. ${rate.toFixed(2)}` : undefined} />
          <Row label="Payment status" value={row.paymentStatus} />
          <Row label="Paid" value={rs(row.paidAmount)} />
          <Row label="Outstanding" value={out != null ? rs(out) : undefined} />
          <Row label="Detention" value={row.detention != null && row.detention > 0 ? rs(row.detention) : undefined} />
        </Section>
      </div>

      <Section title={`Vehicles (${row.vehicles.length}) · ${rollup.label}`} rightNote={`Gross ${gross.toFixed(2)} kg · Net ${net.toFixed(2)} kg`}>
        {row.vehicles.length === 0 ? (
          <p className="text-sm text-muted">No vehicles assigned yet.</p>
        ) : (
          <div className="overflow-x-auto [scrollbar-width:auto]">
            <table className="w-full min-w-[720px] text-left text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 pr-3">#</th>
                  <th className="py-1 pr-3">Vehicle</th>
                  <th className="py-1 pr-3">Type</th>
                  <th className="py-1 pr-3">Packages</th>
                  <th className="py-1 pr-3">Gross</th>
                  <th className="py-1 pr-3">Driver</th>
                  {row.movementType === 'Inbound' && <th className="py-1 pr-3">Container</th>}
                  <th className="py-1 pr-3">Tracking</th>
                </tr>
              </thead>
              <tbody className="text-ink">
                {row.vehicles.map((v, i) => (
                  <tr key={i} className="border-t border-line">
                    <td className="py-1 pr-3">{i + 1}</td>
                    <td className="py-1 pr-3">{v.vehicleNumber || '—'}</td>
                    <td className="py-1 pr-3">{v.vehicleType || '—'}</td>
                    <td className="py-1 pr-3 tabular-nums">{v.noOfPackages ?? '—'}</td>
                    <td className="py-1 pr-3 tabular-nums">{v.grossWeight ?? '—'}</td>
                    <td className="py-1 pr-3">{v.driverPhone || '—'}</td>
                    {row.movementType === 'Inbound' && (
                      <td className="py-1 pr-3">{v.containerNo ? `${v.containerNo} (${v.containerType || '?'})` : '—'}</td>
                    )}
                    <td className="py-1 pr-3">
                      {v.trackingStatus ? <StatusBadge label={v.trackingStatus} /> : <span className="text-muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {row.remarks && (
        <Section title="Remarks">
          <p className="text-sm leading-relaxed text-ink/80">{row.remarks}</p>
        </Section>
      )}

      <ConfirmDialog
        open={confirmReopen}
        title="Reopen this job?"
        description={
          <>
            <span className="font-medium text-ink">{row.systemId}</span> is closed. Reopening makes it editable
            again until it is submitted with every vehicle delivered once more.
          </>
        }
        confirmLabel="Yes, reopen it"
        confirmingLabel="Reopening…"
        confirming={reopening}
        danger={false}
        onConfirm={() => void handleReopen()}
        onCancel={() => setConfirmReopen(false)}
      />
    </div>
  )
}

function KeyFigure({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className={`bg-surface px-3.5 py-2.5 ${warn ? 'bg-[var(--color-watch-bg)]' : ''}`}>
      <div className={`text-[10px] font-semibold uppercase tracking-wide ${warn ? 'text-[var(--color-watch)]' : 'text-muted'}`}>{label}</div>
      <div className="mt-0.5 truncate text-[15px] font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 truncate text-[10.5px] text-muted">{sub}</div>}
    </div>
  )
}

function Section({ title, children, rightNote }: { title: string; children: React.ReactNode; rightNote?: string }) {
  return (
    <section className="rounded-xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h3>
        {rightNote && <span className="text-xs text-muted">{rightNote}</span>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-1.5 text-sm last:border-b-0">
      <span className="text-muted">{label}</span>
      <span className="text-right text-ink">{value ?? '—'}</span>
    </div>
  )
}
