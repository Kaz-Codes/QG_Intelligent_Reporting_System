import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'
import { Plus, Trash2 } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  CONTAINER_TYPES,
  VEHICLE_TRACKING_STATUSES,
  BUILTY_STATUSES,
  emptyVehicle,
  usesContainers,
  totalGrossWeight,
  totalNetWeight,
  type TruckingDraft,
} from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

export function Step2Vehicles() {
  const { register, control } = useFormContext<TruckingDraft>()
  const { fields, append, remove } = useFieldArray({ control, name: 'vehicles' })

  const movementType = useWatch({ control, name: 'movementType' })
  const showContainers = usesContainers(movementType)

  // Live values for the system-generated summary at the bottom.
  const vehicles = useWatch({ control, name: 'vehicles' })
  const grossSum = totalGrossWeight(vehicles)
  const netSum = totalNetWeight(vehicles)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">
          One consignment can move on several vehicles. Add a row per truck — packages, weights,
          container and tracking vary per vehicle.
        </p>
        <Button type="button" variant="outline" onClick={() => append(emptyVehicle())}>
          <Plus size={16} /> Add vehicle
        </Button>
      </div>

      {fields.map((field, i) => (
        <div key={field.id} className="rounded-lg border border-line p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium text-ink">Vehicle {i + 1}</span>
            <Button
              type="button"
              variant="ghost"
              onClick={() => remove(i)}
              disabled={fields.length === 1}
              aria-label={`Remove vehicle ${i + 1}`}
            >
              <Trash2 size={16} />
            </Button>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.vehicleNumber`}>Vehicle Number</Label>
              <Input id={`vehicles.${i}.vehicleNumber`} {...register(`vehicles.${i}.vehicleNumber`)} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.vehicleType`}>Vehicle Type</Label>
              <Input id={`vehicles.${i}.vehicleType`} placeholder="e.g. Flatbed, Container" {...register(`vehicles.${i}.vehicleType`)} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.noOfPackages`}>No. of Packages</Label>
              <Input id={`vehicles.${i}.noOfPackages`} type="number" step="1" {...register(`vehicles.${i}.noOfPackages`, { valueAsNumber: true })} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.driverPhone`}>Driver Phone #</Label>
              <Input id={`vehicles.${i}.driverPhone`} type="tel" {...register(`vehicles.${i}.driverPhone`)} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.netWeight`}>Net Weight (kg)</Label>
              <Input id={`vehicles.${i}.netWeight`} type="number" step="0.01" {...register(`vehicles.${i}.netWeight`, { valueAsNumber: true })} />
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.grossWeight`}>Gross Weight (kg)</Label>
              <Input id={`vehicles.${i}.grossWeight`} type="number" step="0.01" {...register(`vehicles.${i}.grossWeight`, { valueAsNumber: true })} />
            </div>

            {/* Container fields: import FOB (inbound) only. */}
            {showContainers && (
              <>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`vehicles.${i}.containerNo`}>Container No.</Label>
                  <Input id={`vehicles.${i}.containerNo`} {...register(`vehicles.${i}.containerNo`)} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor={`vehicles.${i}.containerType`}>Container Type</Label>
                  <select id={`vehicles.${i}.containerType`} className={selectClass} {...register(`vehicles.${i}.containerType`)}>
                    <option value="">Select…</option>
                    {CONTAINER_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </>
            )}

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.trackingStatus`}>Tracking Status</Label>
              <select id={`vehicles.${i}.trackingStatus`} className={selectClass} {...register(`vehicles.${i}.trackingStatus`)}>
                {VEHICLE_TRACKING_STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`vehicles.${i}.builtyStatus`}>Builty Status</Label>
              <select id={`vehicles.${i}.builtyStatus`} className={selectClass} {...register(`vehicles.${i}.builtyStatus`)}>
                {BUILTY_STATUSES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      ))}

      {/* System-generated summary — no. of vehicles + their key details. */}
      <div className="rounded-lg border border-line bg-canvas-alt p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-ink">
            {fields.length} vehicle{fields.length === 1 ? '' : 's'} on this consignment
          </span>
          <span className="text-xs text-muted">System-generated</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted">
              <tr>
                <th className="py-1 pr-3">#</th>
                <th className="py-1 pr-3">Vehicle No.</th>
                <th className="py-1 pr-3">Packages</th>
                <th className="py-1 pr-3">Gross (kg)</th>
                <th className="py-1 pr-3">Tracking</th>
                <th className="py-1 pr-3">Builty</th>
              </tr>
            </thead>
            <tbody className="text-ink">
              {(vehicles ?? []).map((v, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="py-1 pr-3">{i + 1}</td>
                  <td className="py-1 pr-3">{v?.vehicleNumber || '—'}</td>
                  <td className="py-1 pr-3 tabular-nums">{v?.noOfPackages ?? '—'}</td>
                  <td className="py-1 pr-3 tabular-nums">{v?.grossWeight ?? '—'}</td>
                  <td className="py-1 pr-3">{v?.trackingStatus || '—'}</td>
                  <td className="py-1 pr-3">{v?.builtyStatus || '—'}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="text-muted">
              <tr className="border-t border-line">
                <td className="py-1 pr-3" colSpan={3}>Totals</td>
                <td className="py-1 pr-3 tabular-nums">{grossSum.toFixed(2)}</td>
                <td className="py-1 pr-3" colSpan={2}>Net {netSum.toFixed(2)} kg</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  )
}
