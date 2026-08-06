import { Link, useParams, useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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
import { getTruckingJobs, sourceLabel, type TruckingRow } from '@/lib/truckingStatusData'

const rs = (v?: number | null) => (v === undefined || v === null ? '—' : `Rs. ${Math.round(v).toLocaleString('en-US')}`)

/** ETA-to-works delay: overdue if today is past etaWorks and the job is moving. */
function delayDays(r: TruckingRow): number | null {
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
  const row: TruckingRow | undefined = getTruckingJobs().find((r) => r.systemId === id)
  const canEdit = can(user, 'editAny') || can(user, 'editOwnDraft')

  if (!row) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={`Trucking Job ${id}`} subtitle="Detail view" module="truckingStatus" />
        <Card>
          <CardContent className="flex h-40 items-center justify-center text-muted">
            No trucking job found for {id}.
          </CardContent>
        </Card>
      </div>
    )
  }

  const gross = totalGrossWeight(row.vehicles)
  const net = totalNetWeight(row.vehicles)
  const savings = freightSavings(row.quotedFreight, row.actualFreight)
  const rate = ratePerKg(row.actualFreight, gross)
  const out = outstanding(row.actualFreight, row.paidAmount)
  const rollup = trackingRollup(row.vehicles)
  const delay = delayDays(row)
  // A still-open, live-derived request has no takenAt yet.
  const isDerived = row.source !== 'manual' && !row.takenAt

  // Map the derived source back to its home record so the user can jump to it.
  const sourceHref =
    row.sourceRef && (row.source === 'from-logistics' || row.source === 'from-export')
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
          subtitle={`${row.movementType} · ${sourceLabel(row.source)}`}
          module="truckingStatus"
        />
        <div className="flex items-center gap-3">
          {row.vehicles.length > 0 && <StatusBadge label={rollup.label} />}
          {canEdit && !isDerived && (
            <Button asChild variant="outline">
              <Link to={`/trucking-status/${row.systemId}/edit/1`}>Edit</Link>
            </Button>
          )}
        </div>
      </div>

      {/* provenance banners */}
      {isDerived && (
        <div className="rounded-lg border border-line bg-canvas-alt px-4 py-3 text-sm text-muted">
          This is a live request reflected from {sourceLabel(row.source)}. It updates automatically with
          its source — add vehicles and tracking here once the trucking team takes it on.
          {sourceHref && (
            <> <Link to={sourceHref} className="text-brand hover:underline">Open source {row.sourceRef}</Link>.</>
          )}
        </div>
      )}
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
        <Section title="Movement & Item">
          <Row label="Execution date" value={row.executionDate} />
          <Row label="Transporter" value={row.transporterName} />
          <Row label="Shifting type" value={row.shiftingType} />
          <Row label="Item details" value={row.itemDetails} />
          <Row label="Pickup" value={row.pickup} />
          <Row label="Destination" value={row.destination} />
          {row.movementType !== 'Intrafactory' && <Row label="Reference / IDM" value={row.referenceNo} />}
          <Row label="Dispatch note date" value={row.dispatchNoteDate} />
          <Row label="ETA to works" value={row.etaWorks} />
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
