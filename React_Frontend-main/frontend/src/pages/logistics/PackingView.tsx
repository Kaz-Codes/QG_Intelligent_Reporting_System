import { useState } from 'react'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { LiveDataState } from '@/components/LiveDataState'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money } from '@/lib/format'
import { useDebounced } from '@/lib/useDebounced'
import { usePackingDashboard } from '@/lib/api/useLogisticsDashboard'

const TABS = [
  { value: 'status', label: 'Status' },
  { value: 'category', label: 'By Category' },
  { value: 'biztype', label: 'By Business Type' },
] as const

/** Backed by /dashboard/logistics/packing — all filters are server-side params
 * and every figure below is the endpoint's own. */
export function PackingView() {
  const [status, setStatus] = useState<string[]>([])
  const [works, setWorks] = useState<string[]>([])
  const [productCategory, setProductCategory] = useState<string[]>([])
  const [businessType, setBusinessType] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')

  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isError, error } = usePackingDashboard({
    status, works, product_category: productCategory, business_type: businessType, customer,
    packing_from: dateFrom || undefined, packing_to: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
  })

  const kpis = data?.kpis

  return (
    <div className="flex flex-col gap-6">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by customer, job no, or product category…' }}>
        <DateRangeFilter label="Packing Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Customer" options={data?.customers ?? []} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Works" options={data?.works ?? []} value={works} onChange={setWorks} />
        <MultiSelectFilter label="Product Category" options={data?.productCategories ?? []} value={productCategory} onChange={setProductCategory} />
        <MultiSelectFilter label="Overall Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
      </FilterBar>

      <Disclosure title="More filters — Business Type">
        <div className="flex flex-wrap gap-4 pb-4">
          <div className="w-56">
            <MultiSelectFilter label="Business Type" options={data?.businessTypes ?? []} value={businessType} onChange={setBusinessType} />
          </div>
        </div>
      </Disclosure>

      <LiveDataState isLoading={isLoading} isError={isError} error={error} />

      {data && kpis && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <KpiCard label="Packing Jobs Shown" value={kpis.packing_jobs_shown.toLocaleString()} />
            <KpiCard label="Packed" value={`${kpis.packed}`} direction={kpis.packed ? 'up' : null} goodWhen="up" />
            <KpiCard
              label="Avg RFD Delay"
              value={kpis.avg_rfd_delay_days != null ? `${kpis.avg_rfd_delay_days.toFixed(1)} days` : '—'}
              direction={kpis.avg_rfd_delay_days != null && kpis.avg_rfd_delay_days > 0 ? 'up' : null}
              goodWhen="down"
            />
            <KpiCard label="Total Packing Cost" value={money(kpis.total_cost)} />
            <KpiCard label="Product Categories" value={`${kpis.categories}`} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <InsightsCard title="Insights" tabs={TABS} active={tab} onChange={setTab} className="lg:col-span-2">
              {kpis.packing_jobs_shown === 0 && (
                <p className="py-12 text-center text-sm text-muted">No packing jobs match the current filter.</p>
              )}
              {kpis.packing_jobs_shown > 0 && tab === 'status' && (
                <Donut labels={data.statusSplit.map((s) => s.label)} values={data.statusSplit.map((s) => s.value)} height={300} />
              )}
              {kpis.packing_jobs_shown > 0 && tab === 'category' && (
                <RankedBar data={data.byCategory} category="label" value="value" height={300} unit="Jobs" />
              )}
              {kpis.packing_jobs_shown > 0 && tab === 'biztype' && (
                <CategoryBar data={data.byBusinessType} category="label" value="value" height={300} unit="Jobs" />
              )}
            </InsightsCard>

            <ChartCard title="By Customer (job count)">
              {data.byCustomer.length > 0 ? (
                <RankedBar data={data.byCustomer} category="label" value="value" height={300} unit="Jobs" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No customer data in the current view.</p>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}
