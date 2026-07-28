import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, PAYMENT_STATUSES, INSTRUMENT_WORDING,
  emptyPayment, foreignTotal, paidTotal, unpaidTotal, bankChargesTotal,
} from '../../schema'
import { Field, Input, Select, Callout, CarriedContext } from './fields'

const fx = (v: number, code: string) =>
  `${code || ''} ${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim()

/**
 * Step 4 — Payments.
 *
 * A repeating table, because partial settlement is normal. Each payment carries
 * its own exchange rate (instalments months apart settle differently) and its
 * own bank charges. Bank charges are shown but excluded from the outstanding
 * balance — they are a transaction cost, carried into landed cost, not money
 * owed to the supplier. Nothing here blocks submission.
 */
export function Step4Payments() {
  const { register, control, watch } = useFormContext<ConsignmentDraft>()
  const { fields, append, remove } = useFieldArray({ control, name: 'payments' })
  const payments = useWatch({ control, name: 'payments' }) ?? []
  const items = watch('items')
  const currency = watch('currency')
  const instrument = watch('paymentInstrument') as keyof typeof INSTRUMENT_WORDING | ''
  const wording = instrument ? INSTRUMENT_WORDING[instrument] : null

  const total = foreignTotal({ items } as ConsignmentDraft)
  const paid = paidTotal({ payments } as ConsignmentDraft)
  const unpaid = unpaidTotal({ payments } as ConsignmentDraft)
  const charges = bankChargesTotal({ payments } as ConsignmentDraft)
  const outstanding = total - paid - unpaid

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Instrument', value: instrument || '—' },
        { label: 'Consignment total', value: fx(total, currency) },
        { label: 'Outstanding', value: fx(Math.max(outstanding, 0), currency) },
      ]} />

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          {wording ? `${wording.paymentNoun[0].toUpperCase()}${wording.paymentNoun.slice(1)}s` : 'Payments'} — record each one separately
        </h3>

        <div className="space-y-3 p-4">
          {fields.map((f, i) => (
            <div key={f.id} className="rounded-lg border border-line bg-canvas-alt/40 p-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {wording?.paymentNoun ?? 'Payment'} {i + 1}
                </span>
                <button
                  type="button" onClick={() => remove(i)}
                  className="ml-auto h-6 w-6 rounded border border-line text-muted hover:border-risk hover:text-risk"
                  title="Remove"
                >×</button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label={wording?.paymentDateLabel ?? 'Date'}>
                  <Input type="date" {...register(`payments.${i}.date`)} />
                </Field>
                <Field label={wording?.paymentValueLabel ?? 'Value'}>
                  <Input type="number" min="0" step="any" className="tabular-nums" {...register(`payments.${i}.value`)} placeholder="0.00" />
                </Field>
                <Field label="Status">
                  <Select {...register(`payments.${i}.status`)}>
                    {PAYMENT_STATUSES.map((s) => <option key={s}>{s}</option>)}
                  </Select>
                </Field>
                <Field label="Exchange rate" hint="Blank uses the consignment rate">
                  <Input type="number" min="0" step="any" className="tabular-nums" {...register(`payments.${i}.exchangeRate`)} placeholder="0.00" />
                </Field>
                <Field label="Bank charges (PKR)" hint="Swift, negotiation, commission">
                  <Input type="number" min="0" step="any" className="tabular-nums" {...register(`payments.${i}.bankCharges`)} placeholder="0" />
                </Field>
                <Field label="Reference">
                  <Input {...register(`payments.${i}.reference`)} autoComplete="off" />
                </Field>
              </div>
            </div>
          ))}

          {fields.length === 0 && (
            <p className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-sm text-muted">
              No payments recorded yet. A consignment can sit unpaid — this never blocks submission.
            </p>
          )}

          <button
            type="button"
            onClick={() => append(emptyPayment(`pay-${Date.now()}`))}
            className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-muted"
          >
            + Add {wording?.paymentNoun ?? 'payment'}
          </button>
        </div>

        {/* settlement summary */}
        <div className="grid grid-cols-2 gap-px border-t border-line bg-line sm:grid-cols-4">
          {[
            { l: 'Consignment total', v: fx(total, currency) },
            { l: 'Paid', v: fx(paid, currency) },
            { l: 'Outstanding', v: fx(Math.max(outstanding, 0), currency), warn: outstanding > 0.005 },
            { l: 'Bank charges', v: `PKR ${Math.round(charges).toLocaleString()}` },
          ].map((c) => (
            <div key={c.l} className="bg-surface px-3.5 py-2.5">
              <div className="text-[10px] uppercase tracking-wide text-muted">{c.l}</div>
              <div className={`mt-0.5 text-[14px] font-semibold tabular-nums ${c.warn ? 'text-risk' : ''}`}>{c.v}</div>
            </div>
          ))}
        </div>
      </section>

      <Callout>
        Bank charges are listed but deliberately left out of the outstanding balance — they are a cost of
        the transaction, not money owed to the supplier. They carry forward into the actual landed cost in
        step 7.
      </Callout>
    </div>
  )
}
