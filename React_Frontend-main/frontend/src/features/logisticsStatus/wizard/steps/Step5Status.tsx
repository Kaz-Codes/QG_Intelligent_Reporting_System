import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { statusesFor, type LogisticsDraft } from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

export function Step5Status() {
  const { register, control, formState: { errors } } = useFormContext<LogisticsDraft>()
  const orderType = useWatch({ control, name: 'orderType' })
  // Local orders skip the sea legs (At QFL / At Port / On Water) and close at
  // Delivered; exports run the full pipeline. statusesFor() owns that split.
  const options = statusesFor(orderType)

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="status">Status</Label>
        <select id="status" className={selectClass} {...register('status')}>
          <option value="">Select a status…</option>
          {options.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <p className="text-xs text-muted">
          {orderType === 'Export' ? 'Export pipeline (8 stages).' : 'Local pipeline (4 stages).'}
        </p>
        {errors.status && <p className="text-xs text-risk">{errors.status.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5 sm:col-span-2">
        <Label htmlFor="remarks">Remarks</Label>
        <Input id="remarks" {...register('remarks')} />
        {errors.remarks && <p className="text-xs text-risk">{errors.remarks.message}</p>}
      </div>
    </div>
  )
}
