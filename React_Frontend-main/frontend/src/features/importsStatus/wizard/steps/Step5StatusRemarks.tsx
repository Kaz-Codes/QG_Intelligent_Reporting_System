import { useFormContext, useWatch } from 'react-hook-form'
import { type ConsignmentDraft, CONSIGNMENT_STATUSES } from '../../schema'
import { etaChain } from '../../format'
import { Field, Input, Select, Callout, CarriedContext } from './fields'

/**
 * Step 5 — Status & Remarks.
 *
 * Two distinct remark fields: systemRemarks is generated from the ETA and
 * status history and is read-only (editing it would be overwritten on the next
 * change); userRemarks is free text the operator owns. The status list is fixed
 * and ordered — picking a new value appends to the status history rather than
 * overwriting, so time-at-stage stays answerable.
 */
export function Step5StatusRemarks() {
  const { register, control, watch, formState: { errors } } = useFormContext<ConsignmentDraft>()
  const status = watch('status')
  const eta = watch('eta')
  const revisions = useWatch({ control, name: 'etaRevisions' }) ?? []

  // generated preview of systemRemarks — the real value is written server-side
  const chain = revisions.length
    ? etaChain(revisions.map((r) => r.from), eta)
    : eta ? `ETA ${eta}` : ''
  const generated = [chain, status && `Currently ${status}.`].filter(Boolean).join('. ')

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Consignment', value: watch('systemId') || 'New' },
        { label: 'Supplier', value: watch('supplier') },
      ]} />

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Current status
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          <Field label="Status" htmlFor="status" required error={errors.status?.message} hint="Changing this adds to the status history">
            <Select id="status" {...register('status')}>
              <option value="">Select…</option>
              {CONSIGNMENT_STATUSES.map((s) => <option key={s}>{s}</option>)}
            </Select>
          </Field>
        </div>
      </section>

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Remarks
        </h3>
        <div className="space-y-4 p-4">
          <div>
            <div className="mb-1.5 text-[13px] font-medium">System remarks <span className="font-normal text-muted">— generated, read-only</span></div>
            <div className="min-h-[44px] rounded-lg border border-line bg-canvas-alt px-3 py-2 text-sm text-ink/70">
              {generated || <span className="italic text-muted">Filled automatically from the ETA and status history.</span>}
            </div>
          </div>

          <div>
            <div className="mb-1.5 text-[13px] font-medium">Your remarks</div>
            <textarea
              {...register('userRemarks')}
              rows={4}
              placeholder="Anything the generated summary doesn't capture — a call with the supplier, a hold at customs, a special instruction."
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
            />
          </div>
        </div>
      </section>

      <Callout>
        The two remark fields are kept apart on purpose. The system line is regenerated every time the
        status or ETA changes, so anything typed into it would be lost — your own notes live in the second
        field where nothing overwrites them.
      </Callout>
    </div>
  )
}
