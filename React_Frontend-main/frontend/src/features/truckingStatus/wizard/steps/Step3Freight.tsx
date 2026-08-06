import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  PAYMENT_STATUSES,
  freightSavings,
  ratePerKg,
  totalGrossWeight,
  outstanding,
  type TruckingDraft,
} from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

function DerivedField({ label, value, derivation }: { label: string; value: string; derivation: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label>{label}</Label>
      <div className="flex h-10 w-full items-center rounded-lg border border-line bg-canvas-alt px-3 text-sm tabular-nums text-muted">
        {value}
      </div>
      <p className="text-xs text-muted">{derivation}</p>
    </div>
  )
}

export function Step3Freight() {
  const { register, control, formState: { errors } } = useFormContext<TruckingDraft>()
  const [quoted, actual, paid, vehicles] = useWatch({
    control,
    name: ['quotedFreight', 'actualFreight', 'paidAmount', 'vehicles'],
  })

  const savings = freightSavings(quoted, actual)
  const grossSum = totalGrossWeight(vehicles)
  const rate = ratePerKg(actual, grossSum)
  const outstandingAmt = outstanding(actual, paid)

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="quotedFreight">Quoted Freight (Rs.)</Label>
        <Input id="quotedFreight" type="number" step="0.01" {...register('quotedFreight', { valueAsNumber: true })} />
        {errors.quotedFreight && <p className="text-xs text-risk">{errors.quotedFreight.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="actualFreight">Actual Freight (Rs.)</Label>
        <Input id="actualFreight" type="number" step="0.01" {...register('actualFreight', { valueAsNumber: true })} />
        {errors.actualFreight && <p className="text-xs text-risk">{errors.actualFreight.message}</p>}
      </div>

      <DerivedField
        label="Savings (Rs.)"
        value={savings === null ? '—' : savings.toFixed(2)}
        derivation="Quoted freight − actual freight"
      />

      <DerivedField
        label="Rate per Kg (Rs.)"
        value={rate === null ? '—' : rate.toFixed(2)}
        derivation="Actual freight ÷ total gross weight (all vehicles)"
      />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="paymentStatus">Payment Status</Label>
        <select id="paymentStatus" className={selectClass} {...register('paymentStatus')}>
          {PAYMENT_STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        {errors.paymentStatus && <p className="text-xs text-risk">{errors.paymentStatus.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="paidAmount">Paid (Rs.)</Label>
        <Input id="paidAmount" type="number" step="0.01" {...register('paidAmount', { valueAsNumber: true })} />
        {errors.paidAmount && <p className="text-xs text-risk">{errors.paidAmount.message}</p>}
      </div>

      <DerivedField
        label="Outstanding (Rs.)"
        value={outstandingAmt === null ? '—' : outstandingAmt.toFixed(2)}
        derivation="Actual freight − paid"
      />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="detention">Detention (Rs.)</Label>
        <Input id="detention" type="number" step="0.01" {...register('detention', { valueAsNumber: true })} />
        {errors.detention && <p className="text-xs text-risk">{errors.detention.message}</p>}
      </div>
    </div>
  )
}
