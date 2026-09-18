import { useCallback } from 'react'
import { useFormContext, useWatch, Controller } from 'react-hook-form'
import { type ConsignmentDraft, SHIPMENT_MODES, transitDays } from '../../schema'
import { Field, Input, Select, Callout, CarriedContext, PendingBanner } from './fields'
import { searchPorts, type PortSearchResult } from '@/lib/api/masters'
import { SearchableSelect } from '@/components/ui/SearchableSelect'
import { toOptions } from '@/lib/api/useMasterOptions'
import { AllocationPanel } from './AllocationPanel'
import { EarlierBatches, SHIPPING_COLUMNS } from './EarlierBatches'
import { useBatchContext } from '../BatchContext'

/** Which master port_type a shipment mode's ports are filtered to. Land and
 *  courier moves aren't tracked by a dedicated port_type on the master (only
 *  Sea/Air/Dry/Land exist) — 'Land' is the closest fit. */
const PORT_TYPE_FOR_MODE: Record<string, PortSearchResult['port_type']> = {
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
  const { register, control, watch, setValue, formState: { errors } } = useFormContext<ConsignmentDraft>()
  const mode = useWatch({ control, name: 'modeOfShipment' })
  const etd = watch('etd')
  const eta = watch('eta')
  const revisions = watch('etaRevisions') ?? []

  const wantedType = mode ? PORT_TYPE_FOR_MODE[mode] : undefined

  // Two loaders — loading needs used_as=Loading, delivery needs used_as=Delivery.
  // Both depend on wantedType, so they must stay useCallbacks (module scope
  // can't close over the currently-selected mode) — SearchableSelect requires
  // a stable loadOptions identity except when it's actually meant to change.
  const loadLoadingPorts = useCallback(
    (query: string) =>
      searchPorts(query, { portType: wantedType, usedAs: 'Loading' })
        .then((rows) => toOptions(rows, (p) => p.port_type)),
    [wantedType],
  )
  const loadDeliveryPorts = useCallback(
    (query: string) =>
      searchPorts(query, { portType: wantedType, usedAs: 'Delivery' })
        .then((rows) => toOptions(rows, (p) => p.port_type)),
    [wantedType],
  )

  const transit = transitDays({ etd, eta })
  const batchCtx = useBatchContext()

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        ...(batchCtx.isSplit && batchCtx.batchSequence
          ? [{ label: 'Batch', value: `${batchCtx.batchSequence} of ${batchCtx.batches.length}` }]
          : []),
        { label: 'Consignment', value: watch('consignmentNumber') || 'New' },
        { label: 'Supplier', value: watch('supplier') },
        { label: 'Origin', value: watch('origin') },
      ]} />

      {/* ALLOCATION FIRST. Step 3 is "where batches are created"
          (requirements), and the route below belongs to THIS batch — deciding
          what is in the batch comes before describing how it travels. */}
      <AllocationPanel />

      {/* EARLIER BATCHES, LOCKED. A later batch's own route is blank and
          editable below; what the earlier ones did is context, not a field.
          Shared with Step 6's clearance panel — same shape, different columns. */}
      <EarlierBatches title="Earlier batches — route & schedule" columns={SHIPPING_COLUMNS} />

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Route &amp; schedule{batchCtx.isSplit ? ` — batch ${watch('consignmentNumber')}` : ''}
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
                  onSelectOption={(o) => o.data && setValue('portOfLoadingId', o.data.id, { shouldDirty: true })}
                  loadOptions={loadLoadingPorts}
                  disabled={!mode}
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
                  onSelectOption={(o) => o.data && setValue('portOfDeliveryId', o.data.id, { shouldDirty: true })}
                  loadOptions={loadDeliveryPorts}
                  disabled={!mode}
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
