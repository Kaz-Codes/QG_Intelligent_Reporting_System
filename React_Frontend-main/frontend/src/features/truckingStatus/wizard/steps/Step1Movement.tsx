import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  MOVEMENT_TYPES,
  SHIFTING_TYPES,
  QG_FACTORIES,
  usesFactoryDropdowns,
  usesReferenceNo,
  emptyTruckItem,
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
  const sourceRef = useWatch({ control, name: 'sourceRef' })
  const takenAt = useWatch({ control, name: 'takenAt' })
  const { fields: itemFields, append: appendItem, remove: removeItem } = useFieldArray({
    control, name: 'items',
  })

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {sourceRef && (
        <div className="rounded-lg border border-line bg-canvas-alt px-4 py-3 text-sm text-muted sm:col-span-2">
          Taken from {sourceRef}{takenAt ? ` on ${new Date(takenAt).toLocaleString()}` : ''} — fields below are
          pre-filled from that record; this job is now independent of it.
        </div>
      )}

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

      {/* Repeatable item lines — one job can carry several items, each with
          its own details/weight/pickup/destination/IDM. Item[0] mirrors onto
          the legacy singular fields at the map layer for backend compatibility. */}
      <div className="flex flex-col gap-2 sm:col-span-2">
        <div className="flex items-center justify-between">
          <Label>Items</Label>
          <Button
            type="button"
            variant="outline"
            onClick={() => appendItem(emptyTruckItem())}
          >
            + Add item
          </Button>
        </div>
        {itemFields.map((field, i) => (
          <div key={field.id} className="grid gap-3 rounded-lg border border-line p-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <Label htmlFor={`items.${i}.itemDetails`}>Item Details</Label>
              <Input id={`items.${i}.itemDetails`} {...register(`items.${i}.itemDetails`)} />
              {errors.items?.[i]?.itemDetails && (
                <p className="text-xs text-risk">{errors.items[i]?.itemDetails?.message}</p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`items.${i}.weight`}>Weight (kg)</Label>
              <Input
                id={`items.${i}.weight`}
                type="number"
                step="0.001"
                {...register(`items.${i}.weight`, { valueAsNumber: true })}
              />
              {errors.items?.[i]?.weight && (
                <p className="text-xs text-risk">{errors.items[i]?.weight?.message}</p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`items.${i}.pickup`}>Pickup</Label>
              {factoryMode ? (
                <select id={`items.${i}.pickup`} className={selectClass} {...register(`items.${i}.pickup`)}>
                  <option value="">Select a factory…</option>
                  {QG_FACTORIES.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              ) : (
                <Input id={`items.${i}.pickup`} {...register(`items.${i}.pickup`)} />
              )}
              {errors.items?.[i]?.pickup && (
                <p className="text-xs text-risk">{errors.items[i]?.pickup?.message}</p>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`items.${i}.destination`}>Destination</Label>
              {factoryMode ? (
                <select id={`items.${i}.destination`} className={selectClass} {...register(`items.${i}.destination`)}>
                  <option value="">Select a factory…</option>
                  {QG_FACTORIES.map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              ) : (
                <Input id={`items.${i}.destination`} {...register(`items.${i}.destination`)} />
              )}
              {errors.items?.[i]?.destination && (
                <p className="text-xs text-risk">{errors.items[i]?.destination?.message}</p>
              )}
            </div>

            {showReference && (
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <Label htmlFor={`items.${i}.referenceNo`}>Shipment Reference No. / IDM</Label>
                <Input id={`items.${i}.referenceNo`} {...register(`items.${i}.referenceNo`)} />
                {errors.items?.[i]?.referenceNo && (
                  <p className="text-xs text-risk">{errors.items[i]?.referenceNo?.message}</p>
                )}
              </div>
            )}

            {itemFields.length > 1 && (
              <div className="sm:col-span-2">
                <Button type="button" variant="outline" onClick={() => removeItem(i)}>
                  Remove
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
