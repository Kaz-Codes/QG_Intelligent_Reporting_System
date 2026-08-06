import { useFormContext, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, clearanceBasis, clearanceDays, arrivedAtPortDate,
} from '../../schema'
import { Field, Input, Callout, CarriedContext, PendingBanner } from './fields'

/**
 * Step 6 — Clearance.
 *
 * Clearance time is measured from ACTUAL arrival — the date the status became
 * "Arrived at Port" — falling back to ETA only when that status was never
 * logged. The operator never types the arrival date twice; it comes from the
 * status history. Free days count down from that real arrival, and demurrage
 * carries into landed cost. The whole module is optional and completed after
 * landing.
 */
export function Step6Clearance() {
  const { register, control, watch } = useFormContext<ConsignmentDraft>()
  const statusHistory = useWatch({ control, name: 'statusHistory' }) ?? []
  const eta = watch('eta')
  const freeDays = watch('freeDays')
  const gateOutDate = watch('gateOutDate')

  const draft = { statusHistory, eta, gateOutDate } as Pick<ConsignmentDraft, 'statusHistory' | 'eta' | 'gateOutDate'>
  const basis = clearanceBasis(draft)
  const arrived = arrivedAtPortDate(draft)
  const clearDays = clearanceDays(draft)
  const atPortDays = basis.date
    ? Math.round((+new Date(gateOutDate || new Date().toISOString().slice(0, 10)) - +new Date(basis.date)) / 86_400_000)
    : undefined
  const freeLeft = freeDays !== undefined && atPortDays !== undefined ? freeDays - atPortDays : undefined

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Consignment', value: watch('systemId') || 'New' },
        { label: 'Status', value: watch('status') || '—' },
        { label: 'Clearance measured from', value: basis.date ? `${basis.date} (${basis.kind === 'arrival' ? 'actual arrival' : 'ETA — no arrival logged yet'})` : 'Not yet arrived' },
      ]} />

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Clearance
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Clearing agent" span hint="From clearing-agent master">
            <Input {...register('clearingAgent')} list="dl-agents" autoComplete="off" placeholder="Search…" />
            <datalist id="dl-agents">
              <option>Prime Cargo Services</option>
              <option>Indus Clearing Co.</option>
              <option>Sea Link Logistics</option>
            </datalist>
          </Field>

          <Field label="GD number">
            <Input {...register('gdNumber')} autoComplete="off" />
          </Field>

          <Field label="GD date">
            <Input type="date" {...register('gdDate')} />
          </Field>

          <Field label="Free days allowed">
            <Input type="number" min="0" step="1" className="tabular-nums" {...register('freeDays')} />
          </Field>

          <Field label="Gate out date" hint="When it left the port">
            <Input type="date" {...register('gateOutDate')} />
          </Field>

          <Field label="Demurrage (PKR)" hint="Carries into landed cost">
            <Input type="number" min="0" step="any" className="tabular-nums" {...register('demurrageCost')} placeholder="0" />
          </Field>

          <Field label="Container Detention (PKR)">
            <Input type="number" min="0" step="any" className="tabular-nums" {...register('containerDetention')} placeholder="0" />
          </Field>
        </div>

        {/* live clearance readout */}
        <div className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-4">
          <Readout label="Arrived at port" value={arrived ?? '— not logged'} muted={!arrived} />
          <Readout label="Days at port" value={atPortDays !== undefined ? `${atPortDays} days` : '—'} />
          <Readout
            label="Free days left"
            value={freeLeft !== undefined ? `${freeLeft}` : '—'}
            warn={freeLeft !== undefined && freeLeft <= 2 && !gateOutDate}
          />
          <Readout label="Clearance time" value={clearDays !== undefined ? `${clearDays} days` : '—'} />
        </div>
      </section>

      {!arrived && (
        <PendingBanner
          items={['Actual arrival date']}
          note="It fills in automatically when the status reaches “Arrived at Port”. Until then, free days are estimated from the ETA."
        />
      )}

      <Callout>
        Clearance time and detention are measured from the day the consignment actually berthed — read from
        the status history — not from the ETA. That means the free-days countdown reflects the real clock the
        port is charging against, and nobody keys the arrival date twice.
      </Callout>
    </div>
  )
}

function Readout({ label, value, warn, muted }: { label: string; value: string; warn?: boolean; muted?: boolean }) {
  return (
    <div className={`bg-surface px-3.5 py-2.5 ${warn ? 'bg-[var(--color-watch-bg)]' : ''}`}>
      <div className="text-[10px] uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 text-[14px] font-semibold tabular-nums ${warn ? 'text-[var(--color-watch)]' : muted ? 'text-muted' : ''}`}>{value}</div>
    </div>
  )
}
