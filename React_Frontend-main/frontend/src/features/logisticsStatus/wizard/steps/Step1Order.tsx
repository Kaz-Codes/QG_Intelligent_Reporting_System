import { useFormContext, useWatch } from 'react-hook-form'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { ORDER_TYPES, type LogisticsDraft } from '../../schema'

const selectClass =
  'flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50'

export function Step1Order() {
  const { register, control, formState: { errors } } = useFormContext<LogisticsDraft>()
  // Single rules driver for the screen — origin shape and the export no. field
  // both key off this, so nothing branches on a string literal in the markup.
  const orderType = useWatch({ control, name: 'orderType' })
  const isExport = orderType === 'Export'

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="orderType">Order Type</Label>
        <select id="orderType" className={selectClass} {...register('orderType')}>
          {ORDER_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        {errors.orderType && <p className="text-xs text-risk">{errors.orderType.message}</p>}
      </div>

      {/* Origin: country for exports; city + province for local. */}
      {isExport ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="originCountry">Customer Origin — Country</Label>
          <Input id="originCountry" placeholder="e.g. United Arab Emirates" {...register('originCountry')} />
          {errors.originCountry && <p className="text-xs text-risk">{errors.originCountry.message}</p>}
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="originCity">Customer Origin — City</Label>
            <Input id="originCity" placeholder="e.g. Lahore" {...register('originCity')} />
            {errors.originCity && <p className="text-xs text-risk">{errors.originCity.message}</p>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="originProvince">Customer Origin — Province</Label>
            <Input id="originProvince" placeholder="e.g. Punjab" {...register('originProvince')} />
            {errors.originProvince && <p className="text-xs text-risk">{errors.originProvince.message}</p>}
          </div>
        </>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="customerName">Customer Name</Label>
        <Input id="customerName" {...register('customerName')} />
        {errors.customerName && <p className="text-xs text-risk">{errors.customerName.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5 sm:col-span-2">
        <Label htmlFor="itemDetail">Item Detail</Label>
        <Input id="itemDetail" {...register('itemDetail')} />
        {errors.itemDetail && <p className="text-xs text-risk">{errors.itemDetail.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="quantity">Quantity</Label>
        <Input id="quantity" type="number" step="1" {...register('quantity', { valueAsNumber: true })} />
        {errors.quantity && <p className="text-xs text-risk">{errors.quantity.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="netWeight">Net Weight (kg)</Label>
        <Input id="netWeight" type="number" step="0.01" {...register('netWeight', { valueAsNumber: true })} />
        {errors.netWeight && <p className="text-xs text-risk">{errors.netWeight.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="grossWeight">Gross Weight (kg)</Label>
        <Input id="grossWeight" type="number" step="0.01" {...register('grossWeight', { valueAsNumber: true })} />
        {errors.grossWeight && <p className="text-xs text-risk">{errors.grossWeight.message}</p>}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="idm">IDM</Label>
        <Input id="idm" {...register('idm')} />
        {errors.idm && <p className="text-xs text-risk">{errors.idm.message}</p>}
      </div>

      {/* Export orders additionally carry an export number. */}
      {isExport && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="exportNo">Export No.</Label>
          <Input id="exportNo" {...register('exportNo')} />
          {errors.exportNo && <p className="text-xs text-risk">{errors.exportNo.message}</p>}
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="batchNo">
          Batch No. <span className="font-normal text-muted">(optional)</span>
        </Label>
        <Input id="batchNo" {...register('batchNo')} />
        {errors.batchNo && <p className="text-xs text-risk">{errors.batchNo.message}</p>}
      </div>
    </div>
  )
}
