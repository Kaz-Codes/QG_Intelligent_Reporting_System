import { useFormContext, useFieldArray, useWatch } from 'react-hook-form'
import { useParams } from 'react-router-dom'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { daysBetween, emptyContainer, type LogisticsDraft } from '../../schema'
import { isContainerNumberTaken } from '@/lib/logisticsStatusData'

const normContainer = (s: string) => s.replace(/\s+/g, '').toUpperCase()

const CONTAINER_TYPES = ["20' Dry", "40' Dry", "40' High Cube", "20' Reefer", "40' Reefer", "20' Open Top", "Flat Rack"]
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

export function Step3Shipping() {
  const { register, control, formState: { errors } } = useFormContext<LogisticsDraft>()
  const { id } = useParams()
  const { fields: containerFields, append: appendContainer, remove: removeContainer } = useFieldArray({ control, name: 'containers' })
  const [cro, actualArrival, orderType, watchedContainers] = useWatch({
    control,
    name: ['croArrivalDate', 'actualArrivalDate', 'orderType', 'containers'],
  })

  const arrivalDelay = daysBetween(cro, actualArrival)

  // Live duplicate check: a container number can't repeat across orders, nor
  // twice within THIS order. Returns a reason string when taken, else null.
  const duplicateReason = (value: string | undefined, index: number): string | null => {
    const v = (value ?? '').trim()
    if (!v) return null
    const norm = normContainer(v)
    // within this order (another row with the same number)
    const localDup = (watchedContainers ?? []).some(
      (c, i) => i !== index && c?.containerNo && normContainer(c.containerNo) === norm,
    )
    if (localDup) return 'Already entered on another container in this order'
    // across all other orders
    if (isContainerNumberTaken(v, id)) return 'This container number is already used by another order'
    return null
  }

  return (
    <div className="flex flex-col gap-4">
      {orderType === 'Local' && (
        <div className="rounded-lg border border-line bg-canvas-alt px-4 py-3 text-sm text-muted">
          Shipping details usually apply to export orders. Leave these blank for a local order.
        </div>
      )}

      <section className="rounded-xl border border-line bg-surface">
        <h3 className="border-b border-line px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Containers — a shipment can mix types
        </h3>
        <div className="space-y-2 p-4">
          {containerFields.map((f, i) => (
            <div key={f.id} className="grid grid-cols-[1fr_1fr_auto] items-end gap-3 rounded-lg border border-line bg-canvas-alt/40 p-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`containers.${i}.containerType`}>Container Type</Label>
                <select id={`containers.${i}.containerType`} className={selectClass} {...register(`containers.${i}.containerType`)}>
                  <option value="">Select…</option>
                  {CONTAINER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`containers.${i}.containerNo`}>Container No. <span className="font-normal text-muted">(unique)</span></Label>
                <Input
                  id={`containers.${i}.containerNo`}
                  placeholder="e.g. MSKU1234567"
                  aria-invalid={!!duplicateReason(watchedContainers?.[i]?.containerNo, i)}
                  className={duplicateReason(watchedContainers?.[i]?.containerNo, i) ? 'border-risk focus-visible:ring-risk/40' : ''}
                  {...register(`containers.${i}.containerNo`, {
                    validate: (value) =>
                      duplicateReason(value as string | undefined, i) ?? true,
                  })}
                />
                {(() => {
                  const reason = duplicateReason(watchedContainers?.[i]?.containerNo, i)
                  return reason
                    ? <p className="text-xs text-risk">{reason}</p>
                    : errors.containers?.[i]?.containerNo
                      ? <p className="text-xs text-risk">{String(errors.containers[i]?.containerNo?.message)}</p>
                      : null
                })()}
              </div>
              <button
                type="button"
                onClick={() => removeContainer(i)}
                className="h-10 w-10 rounded border border-line text-muted hover:border-risk hover:text-risk"
                title="Remove container"
              >×</button>
            </div>
          ))}

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => appendContainer(emptyContainer(`container-${Date.now()}`))}
              className="rounded-lg border border-line px-3 py-1.5 text-xs hover:border-muted"
            >
              + Add container
            </button>
            <span className="text-xs text-muted">
              {containerFields.length === 0 ? 'No containers added yet' : `${containerFields.length} container${containerFields.length === 1 ? '' : 's'}`}
            </span>
          </div>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
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
