import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { daysBetween, ratePerWeight, type LogisticsDraft } from '../../schema'

/** Read-only derived output: greyed, with the derivation stated. Mirrors the
 * imports module's "calculated values are computed, never keyed in" rule. */
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

export function Step2Transportation() {
  const { register, control, formState: { errors } } = useFormContext<LogisticsDraft>()
  const [gateOut, dispatch, actualFreight, grossWeight, orderType] = useWatch({
    control,
    name: ['gateOutDate', 'dispatchNoteDate', 'actualFreight', 'grossWeight', 'orderType'],
  })

  const delay = daysBetween(dispatch, gateOut)
  const rate = ratePerWeight(actualFreight, grossWeight)

  // Copy hint changes by order type: for exports the delivery date is when the
  // goods reach QFL; for local it is when they reach the customer (which also
  // closes the order).
  const deliveryHint =
    orderType === 'Export'
      ? 'Exports: date delivered at QFL'
      : 'Local: date delivered to customer — completes the order'

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="transporterName">Transporter Name</Label>
        <Input id="transporterName" {...register('transporterName')} />
        {errors.transporterName && <p className="text-xs text-risk">{errors.transporterName.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="vehicleType">Vehicle Type</Label>
        <Input id="vehicleType" placeholder="e.g. 40ft trailer" {...register('vehicleType')} />
        {errors.vehicleType && <p className="text-xs text-risk">{errors.vehicleType.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="gateOutDate">Gate Out Date</Label>
        <Input id="gateOutDate" type="date" {...register('gateOutDate')} />
        {errors.gateOutDate && <p className="text-xs text-risk">{errors.gateOutDate.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="dispatchNoteDate">Dispatch Note Date</Label>
        <Input id="dispatchNoteDate" type="date" {...register('dispatchNoteDate')} />
        {errors.dispatchNoteDate && <p className="text-xs text-risk">{errors.dispatchNoteDate.message}</p>}
      </div>

      <DerivedField
        label="Delay (days)"
        value={delay === null ? '—' : String(delay)}
        derivation="Gate out date − dispatch note date"
      />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="quotedFreight">Quoted Freight</Label>
        <Input id="quotedFreight" type="number" step="0.01" {...register('quotedFreight', { valueAsNumber: true })} />
        {errors.quotedFreight && <p className="text-xs text-risk">{errors.quotedFreight.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="actualFreight">Actual Freight</Label>
        <Input id="actualFreight" type="number" step="0.01" {...register('actualFreight', { valueAsNumber: true })} />
        {errors.actualFreight && <p className="text-xs text-risk">{errors.actualFreight.message}</p>}
      </div>

      <DerivedField
        label="Rate per Weight"
        value={rate === null ? '—' : rate.toFixed(2)}
        derivation="Actual freight ÷ gross weight (kg)"
      />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="actualDeliveryDate">Actual Delivery Date</Label>
        <Input id="actualDeliveryDate" type="date" {...register('actualDeliveryDate')} />
        <p className="text-xs text-muted">{deliveryHint}</p>
        {errors.actualDeliveryDate && <p className="text-xs text-risk">{errors.actualDeliveryDate.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="originFactory">Origin Factory</Label>
        <Input id="originFactory" {...register('originFactory')} />
        {errors.originFactory && <p className="text-xs text-risk">{errors.originFactory.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="destination">Destination</Label>
        <Input id="destination" {...register('destination')} />
        {errors.destination && <p className="text-xs text-risk">{errors.destination.message}</p>}
      </div>
    </div>
  )
}
