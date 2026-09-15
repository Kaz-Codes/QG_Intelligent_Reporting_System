import { useFormContext, useWatch } from 'react-hook-form'
import {
  type ConsignmentDraft, PAYMENT_INSTRUMENTS, INSTRUMENT_WORDING, RATE_SOURCES,
  foreignTotal, localTotal, lineTotal,
} from '../../schema'
import { Field, FrozenField, Input, Select, Callout, CarriedContext } from './fields'
import { EnteredOnBatchOne } from './EnteredOnBatchOne'
import { useBatchContext, frozenReason } from '../BatchContext'
import { useAuth } from '@/features/auth/AuthContext'

const fx = (v: number | undefined, code: string | undefined) =>
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

  // WHICH OF THIS STEP'S FIELDS THE ORDER HAS SETTLED. The tier lists come
  // from the server on `group_frozen`; this only asks.
  const batchCtx = useBatchContext()
  const { user } = useAuth()
  const frozen = (key: string) => frozenReason(batchCtx, key, !!user?.isAdmin)
  const draft = { items, exchangeRate: rate } as ConsignmentDraft
  const totalForeign = foreignTotal(draft)
  const totalLocal = localTotal(draft)

  return (
    <EnteredOnBatchOne what="Finance">
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
                <th className="px-2 py-1.5 text-center font-medium">Priced by</th>
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
                  {/* PRICED BY — per item, because one consignment can carry a
                      bar sold per piece and a powder sold per kilo. */}
                  <td className="px-2 py-2 text-center">
                    <Select
                      className="w-28"
                      aria-label={`How ${it.itemName || `item ${i + 1}`} is priced`}
                      {...register(`items.${i}.priceBasis`)}
                    >
                      <option value="quantity">Quantity</option>
                      <option value="weight">Weight</option>
                    </Select>
                  </td>
                  {/* ONE PRICE FIELD, NOT TWO SIDE BY SIDE. The unused basis's
                      price is not read at all, so showing it would leave a
                      number on screen that nothing multiplies - which is the
                      thing the requirements ask to make visible rather than
                      hide. Swapping the input says it plainly. */}
                  <td className="px-2 py-2">
                    {it.priceBasis === 'weight' ? (
                      <div className="flex items-center gap-1.5">
                        <Input
                          type="number" min="0" step="any" className="text-right tabular-nums"
                          aria-label={`Weight per unit of ${it.itemName || `item ${i + 1}`} in kg`}
                          {...register(`items.${i}.unitWeight`)}
                          placeholder="kg / unit"
                        />
                        <span className="text-[11px] text-muted">×</span>
                        <Input
                          type="number" min="0" step="any" className="text-right tabular-nums"
                          aria-label={`Price per kg of ${it.itemName || `item ${i + 1}`}`}
                          {...register(`items.${i}.weightUnitPrice`)}
                          placeholder="per kg"
                        />
                      </div>
                    ) : (
                      <Input
                        type="number" min="0" step="any" className="text-right tabular-nums"
                        {...register(`items.${i}.foreignUnitPrice`)}
                        placeholder="0.00"
                      />
                    )}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">{fx(lineTotal(it), currency)}</td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr><td colSpan={5} className="px-2 py-6 text-center text-muted">Add items in step 1 first.</td></tr>
              )}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-line font-semibold">
                <td className="px-2 py-2" colSpan={4}>Consignment total</td>
                <td className="px-2 py-2 text-right tabular-nums">{fx(totalForeign, currency)}</td>
              </tr>
              {rate !== undefined && (
                <tr className="text-muted">
                  <td className="px-2 py-1" colSpan={4}>In PKR at {rate}</td>
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

          {/* "WORKS" WAS HERE AND IS NOW STEP 1'S "Works / Branch" DROPDOWN.
              It was free text that reached no column: `works` is retired on
              the server (helpers.RETIRED_PAYLOAD_FIELDS — accepted from the
              payload and discarded), superseded by the order's
              `works_branch_id`, which Step 1's Branch select already writes.
              The serializer even returns the BRANCH NAME under `works` now,
              so this input round-tripped a value it could not change. Two
              editable controls over one stored value is the thing to avoid,
              so the duplicate goes rather than becoming a second dropdown. */}

          {/* THE RATE IS TIER 1 — once a batch has arrived, nobody may restate
              it, including an admin. Rendered settled rather than disabled, and
              rendered BEFORE the operator types, which is the whole point: a
              423 on save arrives after the work (design §3.9). */}
          {frozen('exchange_rate') ? (
            <FrozenField label="Exchange rate" value={watch('exchangeRate')} reason={frozen('exchange_rate')!} />
          ) : (
            <Field label="Exchange rate" htmlFor="exchangeRate" required error={errors.exchangeRate?.message} hint="Rate booked, not live">
              <Input id="exchangeRate" type="number" min="0" step="any" className="tabular-nums" {...register('exchangeRate')} placeholder="0.00" />
            </Field>
          )}

          {frozen('rate_booked_on') ? (
            <FrozenField label="Rate date" value={watch('rateDate')} reason={frozen('rate_booked_on')!} />
          ) : (
            <Field label="Rate date" required error={errors.rateDate?.message}>
              <Input type="date" {...register('rateDate')} />
            </Field>
          )}

          {/* Tier 1 as well. Leaving it editable beside two settled neighbours
              would say the freeze is about particular inputs rather than about
              the valuation, which is the wrong lesson to teach. */}
          {frozen('rate_source') ? (
            <FrozenField label="Rate source" value={watch('rateSource')} reason={frozen('rate_source')!} span />
          ) : (
            <Field label="Rate source" span hint="Where the booked rate came from — needed to reconcile against a bank advice later">
              <Select {...register('rateSource')}>
                <option value="">Select…</option>
                {RATE_SOURCES.map((s) => <option key={s} value={s}>{s}</option>)}
              </Select>
            </Field>
          )}
        </div>
      </section>

      <Callout>
        The consignment total is summed from the item prices above, never typed directly.
        The exchange rate is stored with its date and source — the PKR value is fixed at what was booked,
        so a report printed today and one printed next month show the same figure.
      </Callout>
    </div>
    </EnteredOnBatchOne>
  )
}
