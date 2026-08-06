import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { StatusPill, Tag, PaymentDot } from './components/atoms'
import { pkr, fx, dateShort, days as daysFmt, num, etaChain } from './format'
import {
  getConsignment, pkrValue, slippageDays, daysAtPort, freeDaysLeft, requiredDelayDays,
} from '@/lib/importsStatusData'
import { WIZARD_STEPS } from './schema'

/**
 * Imports Status — detail view.
 *
 * All seven modules for one consignment, read-only, on a single page. This is
 * the screen a manager actually lives in — the wizard is for entry, this is
 * for looking things up. Each section links straight to its wizard step so a
 * correction never means walking through six Continue clicks.
 *
 * Missing data is shown, not hidden: "Not yet filed", "Pending", a tag on the
 * gap — a blank cell is ambiguous (zero? not entered? not applicable?), naming
 * it removes the guess.
 */
export function ImportsStatusDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { user } = useAuth()

  const row = useMemo(() => (id ? getConsignment(id) : undefined), [id])
  const editable = can(user, 'editAny') || can(user, 'editOwnDraft')

  if (!row) {
    return (
      <div className="space-y-4">
        <PageHeader title="Consignment not found" module="importsStatus" />
        <button onClick={() => navigate('/imports-status')} className="text-sm text-accent hover:underline">
          ← Back to consignments
        </button>
      </div>
    )
  }

  const editLink = (step: string) =>
    editable ? `/imports-status/${row.systemId}/edit/${step}` : undefined

  const EditLink = ({ step }: { step: string }) => {
    const href = editLink(step)
    if (!href) return null
    return (
      <button onClick={() => navigate(href)} className="ml-auto text-xs text-accent hover:underline">
        Edit
      </button>
    )
  }

  const days = daysAtPort(row)
  const left = freeDaysLeft(row)
  const slip = slippageDays(row)
  const reqDelay = requiredDelayDays(row)

  return (
    <div className="space-y-4 pb-16">
      <div className="text-xs text-muted">
        <button onClick={() => navigate('/imports-status')} className="hover:underline">Consignments</button>
        {' › '}{row.systemId}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title={row.systemId}
          subtitle={`${row.supplier} · ${row.branch} · ${row.requisitionSummary}`}
          module="importsStatus"
        />
        <div className="flex items-center gap-3">
          <StatusPill status={row.status} />
          <Button variant="outline" onClick={() => window.print()}>Export PDF</Button>
          {editable && (
            <Button asChild>
              <a href="#" onClick={(e) => { e.preventDefault(); navigate(`/imports-status/${row.systemId}/edit/consignment`) }}>
                Edit consignment
              </a>
            </Button>
          )}
        </div>
      </div>

      {/* key figures */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4 lg:grid-cols-7">
        <KeyFigure label="Value" value={fx(row.foreignValue, row.currency)} sub={pkr(pkrValue(row))} />
        <KeyFigure
          label="Required by" value={dateShort(row.requiredDate)}
          sub={reqDelay === null ? 'Needs a required date + ETA' : reqDelay <= 0 ? (reqDelay === 0 ? 'On time' : `${-reqDelay}d ahead`) : `${reqDelay}d late vs. ETA`}
          warn={reqDelay !== null && reqDelay > 0}
        />
        <KeyFigure label="ETD" value={dateShort(row.etd)} sub={row.items[0]?.itemName ?? ''} />
        <KeyFigure
          label="ETA" value={dateShort(row.eta)}
          sub={row.etaHistory.length ? `Revised ${row.etaHistory.length}× · ${daysFmt(slip)}` : 'Not revised'}
          warn={row.etaHistory.length > 0}
        />
        <KeyFigure label="Payment" value={row.paymentLabel} sub={row.outstanding > 0 ? `${fx(row.outstanding, row.currency)} outstanding` : 'Settled'} />
        <KeyFigure
          label="Free days"
          value={row.freeDays !== null ? `${row.freeDays} days` : '—'}
          sub={row.gateOut ? `Cleared ${dateShort(row.gateOut)}` : left !== null ? `${left} left` : 'Not yet arrived'}
          warn={left !== null && left <= 2 && !row.gateOut}
        />
        <KeyFigure label="Information" value={row.missing.length ? `${row.missing.length} pending` : 'Complete'} sub="See below" warn={row.missing.length > 0} />
      </div>

      {row.missing.length > 0 && (
        <div className="rounded-r border-l-4 border-[var(--color-watch)] bg-[var(--color-watch-bg)] px-3.5 py-2.5 text-sm text-[var(--color-watch)]">
          <b className="font-semibold">Pending information:</b> {row.missing.join(', ')}.{' '}
          Recorded as a draft — nothing here blocks the consignment progressing.
        </div>
      )}

      {/* section nav */}
      <nav className="sticky top-14 z-10 flex gap-1 overflow-x-auto rounded-lg border border-line bg-surface p-1">
        {WIZARD_STEPS.map((s) => (
          <a key={s.key} href={`#s-${s.key}`} className="flex-1 whitespace-nowrap rounded px-3 py-1.5 text-center text-xs text-muted hover:bg-canvas-alt hover:text-ink">
            {s.label}
          </a>
        ))}
      </nav>

      {/* 1 — consignment */}
      <Section id="s-consignment" title="Consignment details" editStep="consignment" edit={<EditLink step="consignment" />}>
        <FieldGrid>
          <Field label="Branch" value={row.branch} />
          <Field label="Supplier" value={row.supplier} span={2} />
          <Field label="Country of origin" value={row.origin} />
          <Field label="Currency" value={row.currency} mono />
          <Field label="Requisition date" value={dateShort(row.requisitionDate)} mono />
          <Field label="Required date" value={dateShort(row.requiredDate)} mono />
        </FieldGrid>

        <div className="mt-4 overflow-auto rounded-lg border border-line">
          <table className="w-full text-sm">
            <thead className="bg-canvas-alt text-xs text-muted">
              <tr>
                <th className="px-3 py-2 text-left">Item</th>
                <th className="px-3 py-2 text-left">Requisition</th>
                <th className="px-3 py-2 text-right">Quantity</th>
                <th className="px-3 py-2 text-left">H.S. code</th>
              </tr>
            </thead>
            <tbody>
              {row.items.map((it, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-3 py-2">
                    <div>{it.itemName}</div>
                    <div className="text-[11px] text-muted">{it.itemCode}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{it.requisitionType}</div>
                    <div className="text-[11px] text-muted">{it.referenceNo || '—'}</div>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(it.quantity)} <span className="text-muted">{it.uom}</span></td>
                  <td className="px-3 py-2">
                    {it.hsCode ? <span className="tabular-nums">{it.hsCode}</span> : <Tag tone="warning" title="Not yet entered">Missing</Tag>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* 2 — finance */}
      <Section id="s-finance" title="Finance" editStep="finance" edit={<EditLink step="finance" />}>
        <FieldGrid>
          <Field label="Instrument" value={row.paymentInstrument} />
          <Field label="Exchange rate" value={row.exchangeRate.toFixed(2)} mono />
          <Field label="Rate booked on" value={dateShort(row.rateDate)} mono />
          <Field label="Total (PKR)" value={pkr(pkrValue(row))} mono />
        </FieldGrid>
      </Section>

      {/* 3 — shipping */}
      <Section id="s-shipping" title="Shipping" editStep="shipping" edit={<EditLink step="shipping" />}>
        <FieldGrid>
          <Field label="ETD" value={dateShort(row.etd)} mono />
          <Field
            label="ETA"
            value={
              <>
                <span className="tabular-nums">{dateShort(row.eta)}</span>
                {row.etaHistory.length > 0 && (
                  <span className="ml-2"><Tag tone="warning" title={etaChain(row.etaHistory, row.eta)}>revised ×{row.etaHistory.length}</Tag></span>
                )}
              </>
            }
          />
          <Field label="Transit time" value={row.etd && row.eta ? `${Math.round((+new Date(row.eta) - +new Date(row.etd)) / 86_400_000)} days` : '—'} mono />
          <Field label="Slippage" value={slip === null ? '—' : daysFmt(slip)} mono />
        </FieldGrid>
      </Section>

      {/* 4 — payments */}
      <Section id="s-payments" title="Payments" editStep="payments" edit={<EditLink step="payments" />}>
        <FieldGrid>
          <Field label="Status" value={<><PaymentDot state={row.paymentState} />{row.paymentLabel}</>} />
          <Field label="Outstanding" value={fx(row.outstanding, row.currency)} mono />
        </FieldGrid>
      </Section>

      {/* 5 — status & remarks */}
      <Section id="s-status-remarks" title="Status &amp; remarks" editStep="status-remarks" edit={<EditLink step="status-remarks" />}>
        <FieldGrid>
          <Field label="Current status" value={<StatusPill status={row.status} />} />
          <Field label="Arrived at port" value={dateShort(row.arrivedAtPort)} mono />
        </FieldGrid>
        <div className="mt-3 rounded-lg border border-line bg-canvas-alt px-3 py-2.5 text-[13px] leading-relaxed text-ink/80">
          {row.etaHistory.length
            ? etaChain(row.etaHistory, row.eta) + '.'
            : 'ETA has not been revised.'}{' '}
          Currently {row.status}.
        </div>
      </Section>

      {/* 6 — clearance */}
      <Section id="s-clearance" title="Custom clearance" editStep="clearance" edit={<EditLink step="clearance" />}>
        <FieldGrid>
          <Field label="Clearing agent" value={row.clearingAgent ?? undefined} span={2} />
          <Field label="Free days allowed" value={row.freeDays !== null ? `${row.freeDays} days` : undefined} mono />
          <Field label="Gate out" value={dateShort(row.gateOut) !== '—' ? dateShort(row.gateOut) : undefined} mono />
          <Field label="Days at port" value={days !== null ? `${days} days` : undefined} mono />
          <Field
            label="Clearance status"
            value={
              row.gateOut ? undefined
              : left !== null ? <Tag tone={left <= 2 ? 'danger' : left <= 4 ? 'warning' : 'neutral'}>{left} free days left</Tag>
              : undefined
            }
          />
        </FieldGrid>
        {!row.arrivedAtPort && (
          <p className="mt-3 text-xs italic text-muted">
            Clearance is normally completed after the consignment lands. Nothing here is overdue.
          </p>
        )}
      </Section>

      {/* 7 — total expenditure (derived from earlier sections, read-only) */}
      <Section id="s-expenditure" title="Total expenditure">
        <div className="overflow-auto rounded-lg border border-line">
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-t border-line first:border-t-0">
                <td className="px-3 py-2 text-muted">Goods value <span className="text-[11px]">(Finance, at booked rate)</span></td>
                <td className="px-3 py-2 text-right tabular-nums">{pkr(pkrValue(row))}</td>
              </tr>
              <tr className="border-t border-line">
                <td className="px-3 py-2 text-muted">Bank charges <span className="text-[11px]">(Payments)</span></td>
                <td className="px-3 py-2 text-right tabular-nums">{pkr(row.bankChargesPkr)}</td>
              </tr>
              <tr className="border-t border-line">
                <td className="px-3 py-2 text-muted">Demurrage <span className="text-[11px]">(Clearance)</span></td>
                <td className="px-3 py-2 text-right tabular-nums">{row.demurragePkr ? pkr(row.demurragePkr) : '—'}</td>
              </tr>
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-line font-semibold">
                <td className="px-3 py-2">Total visible expenditure</td>
                <td className="px-3 py-2 text-right tabular-nums">{pkr(pkrValue(row) + row.bankChargesPkr + row.demurragePkr)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="mt-3 text-xs italic text-muted">
          Summed from figures already captured in Finance, Payments and Clearance — the system
          doesn't compute a definitive landed cost, since accounts carry duty, freight and agent
          fees it can't see. This is the shipment's visible expenditure, for reference.
        </p>
      </Section>
    </div>
  )
}

/* ---------- small local building blocks ---------- */

function KeyFigure({ label, value, sub, warn }: { label: string; value: string; sub?: string; warn?: boolean }) {
  return (
    <div className={`bg-surface px-3.5 py-2.5 ${warn ? 'bg-[var(--color-watch-bg)]' : ''}`}>
      <div className={`text-[10px] font-semibold uppercase tracking-wide ${warn ? 'text-[var(--color-watch)]' : 'text-muted'}`}>{label}</div>
      <div className="mt-0.5 truncate text-[15px] font-semibold tabular-nums">{value}</div>
      {sub && <div className="mt-0.5 truncate text-[10.5px] text-muted">{sub}</div>}
    </div>
  )
}

function Section({
  id, title, children, edit,
}: { id: string; title: string; editStep?: string; children: React.ReactNode; edit?: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-28 rounded-xl border border-line bg-surface">
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</h2>
        {edit}
      </div>
      <div className="p-4">{children}</div>
    </section>
  )
}

function FieldGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-x-5 gap-y-3 lg:grid-cols-4">{children}</div>
}

function Field({
  label, value, span, mono,
}: { label: string; value?: React.ReactNode; span?: 2; mono?: boolean }) {
  return (
    <div className={span === 2 ? 'col-span-2' : undefined}>
      <div className="text-[10.5px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 text-[13.5px] ${mono ? 'tabular-nums' : ''}`}>
        {value === undefined || value === null || value === '' ? <span className="italic text-muted">—</span> : value}
      </div>
    </div>
  )
}
