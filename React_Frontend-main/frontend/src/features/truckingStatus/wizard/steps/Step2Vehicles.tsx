import { useFieldArray, useFormContext, useWatch } from 'react-hook-form'
import { Plus, Trash2 } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { getImportConsignmentOptions } from '@/lib/truckingStatusData'
import {
  CONTAINER_TYPES,
  VEHICLE_TRACKING_STATUSES,
  emptyVehicle,
  usesContainers,
  totalGrossWeight,
  totalNetWeight,
  assignedPackageIds,
  type TruckingDraft,
  type Vehicle,
  type VehiclePackageRef,
  type VehicleImportRef,
} from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

/**
 * Package-wise allocation checklist for one vehicle — only rendered when the
 * job's takenSnapshot actually carries package references (i.e. it came from
 * a taken Logistics order that has packages; manual jobs and item-wise
 * snapshots never render this). Package→vehicle is intentionally NOT 1:1 (a
 * package may fill a whole vehicle, or several may share one), so double
 * assignment is only warned about, never blocked.
 */
function PackageAllocation({
  vehicleIndex, vehicles, setValue,
}: {
  vehicleIndex: number
  vehicles: Vehicle[]
  setValue: (name: `vehicles.${number}.packageRefs`, value: VehiclePackageRef[], opts?: { shouldDirty?: boolean }) => void
}) {
  const { control } = useFormContext<TruckingDraft>()
  const takenSnapshot = useWatch({ control, name: 'takenSnapshot' }) ?? []
  const packageSnapshots = takenSnapshot.filter((s) => s.sourcePackageId)
  if (packageSnapshots.length === 0) return null

  const thisVehicle = vehicles[vehicleIndex]
  const refs = thisVehicle?.packageRefs ?? []
  const assignedElsewhere = assignedPackageIds(vehicles.filter((_, i) => i !== vehicleIndex))

  function toggle(packageId: string, checked: boolean) {
    const next = checked
      ? [...refs, { packageId }]
      : refs.filter((r) => r.packageId !== packageId)
    setValue(`vehicles.${vehicleIndex}.packageRefs`, next, { shouldDirty: true })
  }

  return (
    <div className="mt-3 rounded-lg border border-line bg-canvas-alt/40 p-3 sm:col-span-2 lg:col-span-3">
      <Label>Packages on this vehicle</Label>
      <div className="mt-1.5 flex flex-col gap-1.5">
        {packageSnapshots.map((p) => {
          const checked = refs.some((r) => r.packageId === p.sourcePackageId)
          const elsewhere = !checked && assignedElsewhere.has(p.sourcePackageId!)
          return (
            <label key={p.sourcePackageId} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => toggle(p.sourcePackageId!, e.target.checked)}
              />
              {p.label}
              {p.itemDetails && <span className="text-muted"> — {p.itemDetails}</span>}
              {elsewhere && (
                <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[10.5px] text-[var(--color-watch)]">
                  already assigned to another vehicle
                </span>
              )}
            </label>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Import-consignment checklist for one vehicle — two or more import
 * shipments can legitimately ride the same truck, so this is a many-to-many
 * checklist, the same shape as the package allocation above. Only shown for
 * Inbound movements (the same condition that shows the container fields),
 * since that's the only movement type import consignments apply to.
 */
function ImportConsignmentAllocation({
  vehicleIndex, vehicles, setValue,
}: {
  vehicleIndex: number
  vehicles: Vehicle[]
  setValue: (name: `vehicles.${number}.importConsignmentRefs`, value: VehicleImportRef[], opts?: { shouldDirty?: boolean }) => void
}) {
  const options = getImportConsignmentOptions()
  if (options.length === 0) return null

  const thisVehicle = vehicles[vehicleIndex]
  const refs = thisVehicle?.importConsignmentRefs ?? []

  function toggle(consignmentId: string, checked: boolean) {
    const opt = options.find((o) => o.systemId === consignmentId)
    const next = checked
      ? [...refs, {
          consignmentId,
          // Pre-fill from the consignment's real gross weight; the trucking
          // user can override per vehicle afterwards (goods may split trucks).
          grossWeight: opt?.grossWeight ?? undefined,
          label: opt?.label,
        }]
      : refs.filter((r) => r.consignmentId !== consignmentId)
    setValue(`vehicles.${vehicleIndex}.importConsignmentRefs`, next, { shouldDirty: true })
  }

  function setRefWeight(consignmentId: string, grossWeight: number | undefined) {
    const next = refs.map((r) => (r.consignmentId === consignmentId ? { ...r, grossWeight } : r))
    setValue(`vehicles.${vehicleIndex}.importConsignmentRefs`, next, { shouldDirty: true })
  }

  return (
    <div className="mt-3 rounded-lg border border-line bg-canvas-alt/40 p-3 sm:col-span-2 lg:col-span-3">
      <Label>Import consignments on this vehicle</Label>
      <div className="mt-1.5 flex flex-col gap-1.5">
        {options.map((o) => {
          const checked = refs.some((r) => r.consignmentId === o.systemId)
          return (
            <label key={o.systemId} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => toggle(o.systemId, e.target.checked)}
              />
              <span className="flex-1">{o.label}</span>
              {checked && (
                <span className="flex items-center gap-1 text-xs text-muted">
                  <Input
                    type="number"
                    value={refs.find((r) => r.consignmentId === o.systemId)?.grossWeight ?? ''}
                    onChange={(e) => setRefWeight(o.systemId, e.target.value === '' ? undefined : Number(e.target.value))}
                    className="h-7 w-24 text-right"
                    placeholder="kg"
                  />
                  kg
                </span>
              )}
            </label>
          )
        })}
      </div>
      {refs.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          {refs.length} consignment{refs.length === 1 ? '' : 's'} on this vehicle ·{' '}
          {refs.reduce((sum, r) => sum + (r.grossWeight ?? 0), 0).toLocaleString()} kg total
        </p>
      )}
    </div>
  )
}

export function Step2Vehicles() {
  const { register, control, setValue } = useFormContext<TruckingDraft>()
  const { fields, append, remove } = useFieldArray({ control, name: 'vehicles' })

  const movementType = useWatch({ control, name: 'movementType' })
  const showContainers = usesContainers(movementType)
  const isInbound = movementType === 'Inbound'

  // Live values for the system-generated summary at the bottom.
  const vehicles = useWatch({ control, name: 'vehicles' })
  const grossSum = totalGrossWeight(vehicles)
  const netSum = totalNetWeight(vehicles)
  // Weight coming from checked import consignments (pre-filled from imports,
  // editable per vehicle) — surfaced so selecting consignments visibly
  // changes the footer, and totalled across all vehicles.
  const importRefGross = (v?: Vehicle) =>
    (v?.importConsignmentRefs ?? []).reduce((s, r) => s + (r.grossWeight ?? 0), 0)
  const importRefTotal = (vehicles ?? []).reduce((s, v) => s + importRefGross(v), 0)
  const importRefCount = (vehicles ?? []).reduce((s, v) => s + (v?.importConsignmentRefs?.length ?? 0), 0)

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

            <PackageAllocation vehicleIndex={i} vehicles={vehicles ?? []} setValue={setValue} />
            {isInbound && <ImportConsignmentAllocation vehicleIndex={i} vehicles={vehicles ?? []} setValue={setValue} />}
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
                <th className="py-1 pr-3">Consignments</th>
                <th className="py-1 pr-3">Gross (kg)</th>
                <th className="py-1 pr-3">Import wt (kg)</th>
                <th className="py-1 pr-3">Tracking</th>
              </tr>
            </thead>
            <tbody className="text-ink">
              {(vehicles ?? []).map((v, i) => {
                const refs = v?.importConsignmentRefs ?? []
                return (
                  <tr key={i} className="border-t border-line">
                    <td className="py-1 pr-3">{i + 1}</td>
                    <td className="py-1 pr-3">{v?.vehicleNumber || '—'}</td>
                    <td className="py-1 pr-3 tabular-nums">{v?.noOfPackages ?? '—'}</td>
                    <td className="py-1 pr-3" title={refs.map((r) => r.consignmentId).join(', ') || undefined}>
                      {refs.length === 0 ? '—' : refs.length === 1 ? refs[0].consignmentId : `${refs.length} consignments`}
                    </td>
                    <td className="py-1 pr-3 tabular-nums">{v?.grossWeight ?? '—'}</td>
                    <td className="py-1 pr-3 tabular-nums">{importRefGross(v) ? importRefGross(v).toLocaleString() : '—'}</td>
                    <td className="py-1 pr-3">{v?.trackingStatus || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot className="text-muted">
              <tr className="border-t border-line">
                <td className="py-1 pr-3" colSpan={3}>Totals</td>
                <td className="py-1 pr-3 tabular-nums">{importRefCount || '—'}</td>
                <td className="py-1 pr-3 tabular-nums">{grossSum.toFixed(2)}</td>
                <td className="py-1 pr-3 tabular-nums">{importRefTotal ? importRefTotal.toLocaleString() : '—'}</td>
                <td className="py-1 pr-3">Net {netSum.toFixed(2)} kg</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  )
}
