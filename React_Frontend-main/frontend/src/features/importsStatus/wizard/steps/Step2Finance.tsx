import { useFormContext, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, PAYMENT_INSTRUMENTS, INSTRUMENT_WORDING,
  foreignTotal, localTotal, lineTotal,
} from '../../schema'
import { Field, Input, Select, Callout, CarriedContext } from './fields'

const fx = (v: number | undefined, code: string) =>
  v === undefined ? '—' : `${code || ''} ${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim()
const pkr = (v: number | undefined) => (v === undefined ? '—' : `PKR ${Math.round(v).toLocaleString('en-US')}`)

/**
 * Step 2 — Finance.
 *
 * Pricing is per item — the consignment total is the sum of the lines and is
 * never keyed. The payment instrument relabels the number/date fields via
 * INSTRUMENT_WORDING. The exchange rate is booked with its date and source so a
 * stored value never silently re-converts at a live rate.
 */
export function Step2Finance() {
  const { register, control, watch, formState: { errors } } = useFormContext<ConsignmentDraft>()
  const items = useWatch({ control, name: 'items' }) ?? []
  const currency = watch('currency')
  const rate = watch('exchangeRate')
  const instrument = watch('paymentInstrument') as keyof typeof INSTRUMENT_WORDING | ''

  const wording = instrument ? INSTRUMENT_WORDING[instrument] : null
  const draft = { items, exchangeRate: rate } as ConsignmentDraft
  const totalForeign = foreignTotal(draft)
  const totalLocal = localTotal(draft)

  return (
    <div className="space-y-5">
      <CarriedContext items={[
        { label: 'Supplier', value: watch('supplier') },
        { label: 'Branch', value: watch('branch') },
        { label: 'Currency', value: currency },
      ]} />

      {/* per-item pricing */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Pricing — one unit price per item
        </h3>
        <div className="overflow-auto p-4">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted">
              <tr>
                <th className="px-2 py-1.5 text-left font-medium">Item</th>
                <th className="px-2 py-1.5 text-right font-medium">Quantity</th>
                <th className="px-2 py-1.5 text-right font-medium">Unit price ({currency || 'foreign'})</th>
                <th className="px-2 py-1.5 text-right font-medium">Line total</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-2 py-2">
                    <div>{it.itemName || `Item ${i + 1}`}</div>
                    <div className="text-[11px] text-muted">{it.itemCode}</div>
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {it.quantity ?? '—'} <span className="text-muted">{it.uom}</span>
                  </td>
                  <td className="px-2 py-2">
                    <Input
                      type="number" min="0" step="any" className="text-right tabular-nums"
                      {...register(`items.${i}.foreignUnitPrice`)}
                      placeholder="0.00"
                    />
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{fx(lineTotal(it), currency)}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={4} className="px-2 py-6 text-center text-muted">Add items in step 1 first.</td></tr>
              )}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-line font-semibold">
                <td className="px-2 py-2" colSpan={3}>Consignment total</td>
                <td className="px-2 py-2 text-right tabular-nums">{fx(totalForeign, currency)}</td>
              </tr>
              {rate !== undefined && (
                <tr className="text-muted">
                  <td className="px-2 py-1" colSpan={3}>In PKR at {rate}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{pkr(totalLocal)}</td>
                </tr>
              )}
            </tfoot>
          </table>
        </div>
      </section>

      {/* instrument + rate */}
      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Payment instrument &amp; exchange rate
        </h3>
        <div className="grid gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Instrument" htmlFor="paymentInstrument" error={errors.paymentInstrument?.message}>
            <Select id="paymentInstrument" {...register('paymentInstrument')}>
              <option value="">Select…</option>
              {PAYMENT_INSTRUMENTS.map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
          </Field>

          <Field label={wording?.numberLabel ?? 'Instrument number'} error={errors.instrumentNo?.message}>
            <Input {...register('instrumentNo')} autoComplete="off" />
          </Field>

          <Field label={wording?.dateLabel ?? 'Instrument date'}>
            <Input type="date" {...register('instrumentDate')} />
          </Field>

          <Field label="Works" hint="The entity the import is filed under" error={errors.works?.message}>
            <Input {...register('works')} autoComplete="off" />
          </Field>

          <Field label="Exchange rate" htmlFor="exchangeRate" required error={errors.exchangeRate?.message} hint="Rate booked, not live">
            <Input id="exchangeRate" type="number" min="0" step="any" className="tabular-nums" {...register('exchangeRate')} placeholder="0.00" />
          </Field>

          <Field label="Rate date" required error={errors.rateDate?.message}>
            <Input type="date" {...register('rateDate')} />
          </Field>

          <Field label="Rate source" span hint="e.g. bank TT rate, SBP">
            <Input {...register('rateSource')} autoComplete="off" />
          </Field>
        </div>
      </section>

      <Callout>
        The consignment total is summed from the item prices above, never typed directly.
        The exchange rate is stored with its date and source — the PKR value is fixed at what was booked,
        so a report printed today and one printed next month show the same figure.
      </Callout>
    </div>
  )
}
