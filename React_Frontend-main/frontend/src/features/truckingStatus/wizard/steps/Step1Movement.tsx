import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import {
  MOVEMENT_TYPES,
  SHIFTING_TYPES,
  QG_FACTORIES,
  usesFactoryDropdowns,
  usesReferenceNo,
  type TruckingDraft,
} from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

export function Step1Movement() {
  const { register, control, formState: { errors } } = useFormContext<TruckingDraft>()
  // Single conditional driver for the whole module.
  const movementType = useWatch({ control, name: 'movementType' })
  const factoryMode = usesFactoryDropdowns(movementType)
  const showReference = usesReferenceNo(movementType)

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="movementType">Movement Type</Label>
        <select id="movementType" className={selectClass} {...register('movementType')}>
          {MOVEMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
              {t === 'Inbound' ? ' (Import FOB)' : ''}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted">
          {movementType === 'Intrafactory'
            ? 'Movement between Qadri Group factories.'
            : movementType === 'Outbound'
              ? 'Export & local deliveries to customers.'
              : 'Import FOB — clearance managed in-house from supplier origin.'}
        </p>
        {errors.movementType && <p className="text-xs text-risk">{errors.movementType.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="executionDate">Execution Date</Label>
        <Input id="executionDate" type="date" {...register('executionDate')} />
        {errors.executionDate && <p className="text-xs text-risk">{errors.executionDate.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="transporterName">Transporter Name</Label>
        <Input id="transporterName" {...register('transporterName')} />
        {errors.transporterName && <p className="text-xs text-risk">{errors.transporterName.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="shiftingType">Shifting Type</Label>
        <select id="shiftingType" className={selectClass} {...register('shiftingType')}>
          {SHIFTING_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        {errors.shiftingType && <p className="text-xs text-risk">{errors.shiftingType.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5 sm:col-span-2">
        <Label htmlFor="itemDetails">Item Details</Label>
        <Input id="itemDetails" {...register('itemDetails')} />
        {errors.itemDetails && <p className="text-xs text-risk">{errors.itemDetails.message}</p>}
      </div>

      {/* Pickup / destination: factory dropdowns for intrafactory, free text otherwise. */}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="pickup">Pickup</Label>
        {factoryMode ? (
          <select id="pickup" className={selectClass} {...register('pickup')}>
            <option value="">Select a factory…</option>
            {QG_FACTORIES.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        ) : (
          <Input id="pickup" {...register('pickup')} />
        )}
        {errors.pickup && <p className="text-xs text-risk">{errors.pickup.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="destination">Destination</Label>
        {factoryMode ? (
          <select id="destination" className={selectClass} {...register('destination')}>
            <option value="">Select a factory…</option>
            {QG_FACTORIES.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
        ) : (
          <Input id="destination" {...register('destination')} />
        )}
        {errors.destination && <p className="text-xs text-risk">{errors.destination.message}</p>}
      </div>

      {/* Reference / IDM: outbound + inbound only. */}
      {showReference && (
        <div className="flex flex-col gap-1.5 sm:col-span-2">
          <Label htmlFor="referenceNo">Shipment Reference No. / IDM</Label>
          <Input id="referenceNo" {...register('referenceNo')} />
          {errors.referenceNo && <p className="text-xs text-risk">{errors.referenceNo.message}</p>}
        </div>
      )}
    </div>
  )
}
