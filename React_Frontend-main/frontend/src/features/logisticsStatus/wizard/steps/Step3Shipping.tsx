import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { daysBetween, type LogisticsDraft } from '../../schema'

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

export function Step3Shipping() {
  const { register, control, formState: { errors } } = useFormContext<LogisticsDraft>()
  const [cro, actualArrival, orderType] = useWatch({
    control,
    name: ['croArrivalDate', 'actualArrivalDate', 'orderType'],
  })

  const arrivalDelay = daysBetween(cro, actualArrival)

  return (
    <div className="flex flex-col gap-4">
      {orderType === 'Local' && (
        <div className="rounded-lg border border-line bg-canvas-alt px-4 py-3 text-sm text-muted">
          Shipping details usually apply to export orders. Leave these blank for a local order.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="containerCount">No. of Containers</Label>
          <Input id="containerCount" type="number" step="1" {...register('containerCount', { valueAsNumber: true })} />
          {errors.containerCount && <p className="text-xs text-risk">{errors.containerCount.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="containerType">Type of Containers</Label>
          <Input id="containerType" placeholder="e.g. 20ft / 40ft HC" {...register('containerType')} />
          {errors.containerType && <p className="text-xs text-risk">{errors.containerType.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pol">POL (Port of Loading)</Label>
          <Input id="pol" {...register('pol')} />
          {errors.pol && <p className="text-xs text-risk">{errors.pol.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="pod">POD (Port of Discharge)</Label>
          <Input id="pod" {...register('pod')} />
          {errors.pod && <p className="text-xs text-risk">{errors.pod.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="shippingLine">Shipping Line</Label>
          <Input id="shippingLine" {...register('shippingLine')} />
          {errors.shippingLine && <p className="text-xs text-risk">{errors.shippingLine.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="clearingAgent">Clearing Agent</Label>
          <Input id="clearingAgent" {...register('clearingAgent')} />
          {errors.clearingAgent && <p className="text-xs text-risk">{errors.clearingAgent.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="bookingNo">Booking No.</Label>
          <Input id="bookingNo" {...register('bookingNo')} />
          {errors.bookingNo && <p className="text-xs text-risk">{errors.bookingNo.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="portInDate">Port In Date</Label>
          <Input id="portInDate" type="date" {...register('portInDate')} />
          {errors.portInDate && <p className="text-xs text-risk">{errors.portInDate.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="etdSailingDate">ETD / Sailing Date</Label>
          <Input id="etdSailingDate" type="date" {...register('etdSailingDate')} />
          {errors.etdSailingDate && <p className="text-xs text-risk">{errors.etdSailingDate.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="croArrivalDate">CRO Arrival Date</Label>
          <Input id="croArrivalDate" type="date" {...register('croArrivalDate')} />
          {errors.croArrivalDate && <p className="text-xs text-risk">{errors.croArrivalDate.message}</p>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="actualArrivalDate">Actual Arrival Date</Label>
          <Input id="actualArrivalDate" type="date" {...register('actualArrivalDate')} />
          {errors.actualArrivalDate && <p className="text-xs text-risk">{errors.actualArrivalDate.message}</p>}
        </div>

        <DerivedField
          label="Arrival Delay (days)"
          value={arrivalDelay === null ? '—' : String(arrivalDelay)}
          derivation="Actual arrival date − CRO arrival date"
        />
      </div>
    </div>
  )
}
