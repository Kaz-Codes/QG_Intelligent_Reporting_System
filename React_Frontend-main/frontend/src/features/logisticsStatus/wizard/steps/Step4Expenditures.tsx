import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import type { LogisticsDraft } from '../../schema'

// The expenditure set depends on order type. Kept as data (not scattered
// if-blocks) so adding a cost line later is a one-row change — the same
// "single rules object per screen" convention the imports module uses.
const EXPORT_COSTS: { name: keyof LogisticsDraft; label: string }[] = [
  { name: 'packingCost', label: 'Packing Cost' },
  { name: 'insurance', label: 'Insurance' },
  { name: 'truckingLhrToKhi', label: 'Trucking (Lhr → Khi / QFL)' },
  { name: 'fumigationCost', label: 'Fumigation Cost' },
  { name: 'lashing', label: 'Lashing' },
  { name: 'qflCharges', label: 'QFL Charges' },
  { name: 'qflContainerMovement', label: 'QFL Transportation (Port → QFL → Port)' },
  { name: 'customClearanceCharges', label: 'Custom Clearance Charges' },
  { name: 'portCharges', label: 'Port Charges' },
  { name: 'dhlCharges', label: 'DHL Charges' },
  { name: 'seaAirFreight', label: 'Sea Freight / Air Freight' },
]

const LOCAL_COSTS: { name: keyof LogisticsDraft; label: string }[] = [
  { name: 'packingCost', label: 'Packing Cost' },
  { name: 'transportationCharges', label: 'Transportation Charges' },
]

export function Step4Expenditures() {
  const { register, control, formState: { errors } } = useFormContext<LogisticsDraft>()
  const orderType = useWatch({ control, name: 'orderType' })
  const costs = orderType === 'Export' ? EXPORT_COSTS : LOCAL_COSTS

  // Provisional running total across the visible lines. Partial data produces
  // a provisional figure marked with an asterisk, never a blank.
  const values = useWatch({ control, name: costs.map((c) => c.name) as (keyof LogisticsDraft)[] })
  const total = (values as (number | undefined)[]).reduce<number>((s, v) => s + (Number(v) || 0), 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {costs.map(({ name, label }) => (
          <div key={name} className="flex flex-col gap-1.5">
            <Label htmlFor={name}>{label}</Label>
            <Input
              id={name}
              type="number"
              step="0.01"
              {...register(name as keyof LogisticsDraft, { valueAsNumber: true })}
            />
            {errors[name] && <p className="text-xs text-risk">{String(errors[name]?.message)}</p>}
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between rounded-lg border border-line bg-canvas-alt px-4 py-3">
        <span className="text-sm font-medium text-ink">Total Expenditure*</span>
        <span className="text-sm font-semibold tabular-nums text-ink">{total.toFixed(2)}</span>
      </div>
      <p className="-mt-2 text-xs text-muted">
        *Provisional — sums the {orderType === 'Export' ? 'export' : 'local'} cost lines entered so far.
      </p>
    </div>
  )
}
