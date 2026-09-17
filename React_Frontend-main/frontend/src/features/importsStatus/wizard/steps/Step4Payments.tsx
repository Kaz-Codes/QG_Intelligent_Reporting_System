import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, PAYMENT_STATUSES, INSTRUMENT_WORDING,
  emptyPayment, emptyAddendum, foreignTotal, paidTotal, unpaidTotal, bankChargesTotal,
} from '../../schema'
import { Field, Input, Select, Callout, CarriedContext } from './fields'
import { EnteredOnBatchOne } from './EnteredOnBatchOne'

const fx = (v: number, code: string | undefined) =>
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
  const addenda = useFieldArray({ control, name: 'addenda' })
  const payments = useWatch({ control, name: 'payments' }) ?? []
  const items = watch('items')
  const currency = watch('currency')
  const instrument = watch('paymentInstrument') as keyof typeof INSTRUMENT_WORDING | ''
  const wording = instrument ? INSTRUMENT_WORDING[instrument] : null

  // THE RATES, FETCHED FROM STEP 2, ON ADVANCE ONLY. Requirements: *"Advance —
  // fetch both the rates and the value. Any other mode — fetch the consignment
  // value only"*. "The rates" is the whole triple, not the exchange rate
  // alone.
  //
  // Read straight off the draft, which already holds all three: they are group
  // columns published on every batch's payload. DISPLAYED, NOT RE-ENTERED —
  // they are Tier 1 frozen (§3.9) and Step 2 owns them, so this step shows
  // what Step 2 holds and offers no input. Labels match Step 2's exactly
  // ("Exchange rate", "Rate date", "Rate source") rather than inventing a
  // second vocabulary for one set of fields, and `rateSource` is already
  // readable prose in `RateSource` so it is rendered as stored.
  const isAdvance = instrument === 'Adv'
  const exchangeRate = watch('exchangeRate')
  const rateDate = watch('rateDate')
  const rateSource = watch('rateSource')

  const total = foreignTotal({ items } as ConsignmentDraft)
  const paid = paidTotal({ payments } as ConsignmentDraft)
  const unpaid = unpaidTotal({ payments } as ConsignmentDraft)
  const charges = bankChargesTotal({ payments } as ConsignmentDraft)
  const outstanding = total - paid - unpaid

  return (
    <EnteredOnBatchOne what="Payments">
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Instrument', value: instrument || '—' },
        { label: 'Consignment total', value: fx(total, currency) },
        { label: 'Outstanding', value: fx(Math.max(outstanding, 0), currency) },
        ...(isAdvance ? [
          { label: 'Exchange rate', value: exchangeRate !== undefined ? String(exchangeRate) : undefined },
          { label: 'Rate date', value: rateDate || undefined },
          { label: 'Rate source', value: rateSource || undefined },
        ] : []),
      ]} />

      {/* LC-LEVEL, ABOVE THE PAYMENT ROWS. Insurance is taken out on the
          ORDER, not on each shipment, so it sits with the other order-level
          figure on this step rather than on any one payment. The freeze does
          NOT cover it (§3.9 exempts the payment process), so it stays editable
          on a closed order — which is the point: an LC is retired after the
          goods arrive. */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Insurance — taken out once, on the order
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label={`Insurance amount (${currency || 'foreign'})`} htmlFor="insuranceAmount"
                 hint="Blank means nobody has entered one; 0 means there is none">
            <Input id="insuranceAmount" type="number" min="0" step="any"
                   className="tabular-nums" placeholder="0.00"
                   {...register('insuranceAmount')} />
          </Field>
        </div>
      </section>

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

      {/* ADDENDA — AMENDMENTS TO THE LC.
          An "Add addendum" button rather than fixed "1st"/"2nd" sections, per
          the requirements: the count is open.

          NOTHING HERE ENTERS ANY FIGURE ABOVE. Not `value`, which is a signed
          DELTA to the LC amount rather than a revised total, and not
          `bankCharges` either — the payment bank charges in the summary above
          carry into landed cost and these do not. Wiring either into a total
          restates a number that is already on screen and in printed sheets
          (CLAUDE.md rule 4) and is a change of its own. */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Addenda — amendments to the LC
        </h3>

        <div className="space-y-3 p-4">
          {addenda.fields.map((f, i) => (
            <div key={f.id} className="rounded-lg border border-line bg-canvas-alt/40 p-3">
              <div className="mb-2 flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">
                  Addendum {i + 1}
                </span>
                <button
                  type="button" onClick={() => addenda.remove(i)}
                  className="ml-auto h-6 w-6 rounded border border-line text-muted hover:border-risk hover:text-risk"
                  title="Remove"
                >×</button>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Field label="Addendum date">
                  <Input type="date" {...register(`addenda.${i}.date`)} />
                </Field>
                <Field label="Reference">
                  <Input {...register(`addenda.${i}.reference`)} autoComplete="off" />
                </Field>
                {/* NO `min="0"`. The value is the CHANGE to the LC amount —
                    an increase positive, a reduction NEGATIVE — so a minimum
                    of zero would block half of what this field records. */}
                <Field label={`Change to LC value (${currency || 'foreign'})`}
                       hint="The change, not the new total — negative for a reduction">
                  <Input type="number" step="any" className="tabular-nums"
                         {...register(`addenda.${i}.value`)} placeholder="0.00" />
                </Field>
                <Field label="Bank charges (PKR)" hint="Not included in any total above">
                  <Input type="number" min="0" step="any" className="tabular-nums"
                         {...register(`addenda.${i}.bankCharges`)} placeholder="0" />
                </Field>
                <Field label="Description" span>
                  <Input {...register(`addenda.${i}.description`)} autoComplete="off" />
                </Field>
              </div>
            </div>
          ))}

          {addenda.fields.length === 0 && (
            <p className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-sm text-muted">
              No addenda recorded. Most LCs are never amended.
            </p>
          )}

          <button
            type="button"
            onClick={() => addenda.append(emptyAddendum(`add-${Date.now()}`))}
            className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-muted"
          >
            + Add addendum
          </button>
        </div>
      </section>

      <Callout>
        Bank charges are listed but deliberately left out of the outstanding balance — they are a cost of
        the transaction, not money owed to the supplier. They carry forward into the actual landed cost in
        step 7.
      </Callout>
    </div>
    </EnteredOnBatchOne>
  )
}
