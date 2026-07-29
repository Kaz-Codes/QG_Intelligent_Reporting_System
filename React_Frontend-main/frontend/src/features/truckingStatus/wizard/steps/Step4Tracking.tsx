import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { VEHICLE_TRACKING_STATUSES, trackingRollup, type TruckingDraft } from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

export function Step4Tracking() {
  const { register, control } = useFormContext<TruckingDraft>()
  const vehicles = useWatch({ control, name: 'vehicles' })
  const rollup = trackingRollup(vehicles)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="dispatchNoteDate">Dispatch Note Date</Label>
          <Input id="dispatchNoteDate" type="date" {...register('dispatchNoteDate')} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="etaWorks">ETA Works</Label>
          <Input id="etaWorks" type="date" {...register('etaWorks')} />
        </div>
      </div>

      {/* Per-vehicle tracking — each truck advances independently. */}
      <div className="rounded-lg border border-line p-4">
        <p className="mb-3 text-sm font-medium text-ink">Per-vehicle tracking</p>
        <div className="flex flex-col gap-3">
          {(vehicles ?? []).map((v, i) => (
            <div key={i} className="grid items-center gap-3 sm:grid-cols-[1fr_auto]">
              <span className="text-sm text-ink">
                Vehicle {i + 1}
                {v?.vehicleNumber ? ` — ${v.vehicleNumber}` : ''}
              </span>
              <select
                className={selectClass + ' sm:w-48'}
                {...register(`vehicles.${i}.trackingStatus`)}
                aria-label={`Tracking status for vehicle ${i + 1}`}
              >
                {VEHICLE_TRACKING_STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          ))}
          {(!vehicles || vehicles.length === 0) && (
            <p className="text-sm text-muted">No vehicles added yet — add them on the Vehicles step.</p>
          )}
        </div>
      </div>

      {/* Derived consignment rollup: fraction + slowest stage. */}
      <div className="flex items-center justify-between rounded-lg border border-line bg-canvas-alt px-4 py-3">
        <div>
          <span className="text-sm font-medium text-ink">Consignment tracking</span>
          <p className="text-xs text-muted">Delivered fraction · slowest (least-advanced) vehicle stage</p>
        </div>
        <span className="text-sm font-semibold text-ink">{rollup.label}</span>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="remarks">Remarks</Label>
        <Input id="remarks" {...register('remarks')} />
      </div>
    </div>
  )
}
