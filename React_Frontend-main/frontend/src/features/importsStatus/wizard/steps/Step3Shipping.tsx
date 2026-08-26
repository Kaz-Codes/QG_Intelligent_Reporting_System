import { useFormContext, useWatch, Controller } from 'react-hook-form'
import { type ConsignmentDraft, SHIPMENT_MODES, transitDays } from '../../schema'
import { Field, Input, Select, Callout, CarriedContext, PendingBanner } from './fields'
import { useMasters } from '../MastersContext'
import type { PortOption } from '@/lib/api/masters'
import { SearchableSelect } from '@/components/ui/SearchableSelect'
import { toOptions } from '@/lib/api/useMasterOptions'

/** Which master port_type a shipment mode's ports are filtered to. Land and
 *  courier moves aren't tracked by a dedicated port_type on the master (only
 *  Sea/Air/Dry/Land exist) — 'Land' is the closest fit. */
const PORT_TYPE_FOR_MODE: Record<string, PortOption['port_type']> = {
  'Sea freight FCL': 'Sea',
  'Sea freight LCL': 'Sea',
  'Air freight': 'Air',
  'Land/courier': 'Land',
}

/**
 * Step 3 — Shipping.
 *
 * Ports filter by the selected mode (a sea consignment shouldn't offer an
 * airport). The field is "Port of delivery", matching the sheet this replaces.
 * ETA revisions are recorded as history: the first ETA is preserved so slippage
 * is measured against the original promise, and a reason is required whenever
 * the current ETA is changed.
 */
export function Step3Shipping() {
  const { register, control, watch, formState: { errors } } = useFormContext<ConsignmentDraft>()
  const mode = useWatch({ control, name: 'modeOfShipment' })
  const etd = watch('etd')
  const eta = watch('eta')
  const revisions = watch('etaRevisions') ?? []
  const { ports: allPorts, loading: mastersLoading } = useMasters()

  const wantedType = mode ? PORT_TYPE_FOR_MODE[mode] : undefined
  const byType = wantedType ? allPorts.filter((p) => p.port_type === wantedType) : allPorts
  const loadingPorts = byType.filter((p) => p.used_as === 'Loading' || p.used_as === 'Both')
  const deliveryPorts = byType.filter((p) => p.used_as === 'Delivery' || p.used_as === 'Both')
  const transit = transitDays({ etd, eta })

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Consignment', value: watch('systemId') || 'New' },
        { label: 'Supplier', value: watch('supplier') },
        { label: 'Origin', value: watch('origin') },
      ]} />

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Route &amp; schedule
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Mode of shipment" htmlFor="modeOfShipment" error={errors.modeOfShipment?.message}>
            <Select id="modeOfShipment" {...register('modeOfShipment')}>
              <option value="">Select…</option>
              {SHIPMENT_MODES.map((m) => <option key={m}>{m}</option>)}
            </Select>
          </Field>

          {/* Searchable, but deliberately NOT free text — the one pair of
              master fields in this round that stays restricted.
              A consignment stores loading_port_id / delivery_port_id, foreign
              keys with no name column beside them, so an unmatched value has
              nowhere to live and would be dropped on save. These were already
              a closed <Select> for that reason; this only makes a long port
              list searchable instead of a scroll. The port-type and used_as
              filtering below is also a real constraint (a sea consignment
              must not offer an airport) that free text would defeat. */}
          <Field label="Port of loading" hint={mode ? undefined : 'Choose a mode to filter ports'}>
            <Controller
              control={control}
              name="portOfLoading"
              render={({ field }) => (
                <SearchableSelect
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  options={toOptions(loadingPorts, (p) => p.port_type)}
                  disabled={!mode || mastersLoading}
                  placeholder={mode ? 'Search ports…' : 'Select mode first'}
                  emptyMessage="No matching port for this mode"
                />
              )}
            />
          </Field>

          <Field label="Port of delivery">
            <Controller
              control={control}
              name="portOfDelivery"
              render={({ field }) => (
                <SearchableSelect
                  value={field.value ?? ''}
                  onChange={field.onChange}
                  options={toOptions(deliveryPorts, (p) => p.port_type)}
                  disabled={!mode || mastersLoading}
                  placeholder={mode ? 'Search ports…' : 'Select mode first'}
                  emptyMessage="No matching port for this mode"
                />
              )}
            />
          </Field>

          <Field label="Readiness date" hint="Goods ready to ship">
            <Input type="date" {...register('readinessDate')} />
          </Field>

          <Field label="ETD" error={errors.etd?.message}>
            <Input type="date" {...register('etd')} />
          </Field>

          <Field label="ETA (port)" error={errors.eta?.message}>
            <Input type="date" {...register('eta')} />
          </Field>

          <Field label="ETA (works)" hint="Optional">
            <Input type="date" {...register('etaWorks')} />
          </Field>

          <Field label="Transit time">
            <div className="flex h-10 items-center px-1 text-sm tabular-nums text-muted">
              {transit !== undefined ? `${transit} days` : 'ETD and ETA needed'}
            </div>
          </Field>
        </div>
      </section>

      {/* revision history — read-only here; a change is logged via the detail
          view's edit action, which captures the reason. In the wizard we show
          the chain and explain the rule. */}
      {revisions.length > 0 && (
        <section className="rounded-xl border border-line bg-surface">
          <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
            ETA history
          </h3>
          <ul className="divide-y divide-line">
            {revisions.map((r, i) => (
              <li key={r.id ?? i} className="flex items-baseline gap-3 px-4 py-2 text-sm">
                <span className="text-xs text-muted">{r.changedAt?.slice(0, 10)}</span>
                <span className="tabular-nums">{r.from} → {r.to}</span>
                <span className="text-muted">{r.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <PendingBanner
        items={[!etd && 'ETD', !eta && 'ETA'].filter(Boolean) as string[]}
        note="Shipping dates are usually confirmed after the LC or advance is arranged."
      />

      <Callout>
        The first ETA is kept even after it changes. Slippage is measured against that original date,
        not the most recent one, so a consignment revised three times still shows the full delay against
        what was first promised. Each change asks for a reason, which builds the "1st ETA… 2nd ETA…" line
        seen on reports.
      </Callout>
    </div>
  )
}
