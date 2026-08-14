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
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { DataNotes } from '@/components/DataNotes'
import { Label } from '@/components/ui/label'
import { LOGISTICS_HELP } from '@/lib/metricHelp'
import { logisticsRefPager } from '@/lib/api/dashboardReferences'
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
  // Empty = this month, resolved by the backend.
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)
  // Packed, or ready-for-dispatch — two real events with two different dates.
  const [dateField, setDateField] = useState('packed')
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')

  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isFetching, isError, error } = usePackingDashboard({
    status, works, product_category: productCategory, business_type: businessType, customer,
    packing_from: dateFrom || undefined, packing_to: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
    date_from: period.from || undefined,
    date_to: period.to || undefined,
    date_field: dateField,
  })

  const refs = data?.references

  const pager = (key: string) => logisticsRefPager(key, {
    tab: 'packing',
    status, works, product_category: productCategory, business_type: businessType,
    customer, packing_from: dateFrom, packing_to: dateTo,
    search: debouncedSearch.trim(),
    date_from: period.from, date_to: period.to, date_field: dateField,
  })

  const kpis = data?.kpis

  return (
    <div className="flex flex-col gap-6">
      {/* The window, and which date it means — the same control, wording and
          "jump to the latest month with data" as every other dashboard. */}
      <div className="rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
            label="Reporting period" />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="packing-date-field" className="text-xs">Filter on</Label>
            <select
              id="packing-date-field"
              value={dateField}
              onChange={(e) => setDateField(e.target.value)}
              className="h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            >
              {(data?.dateFieldOptions ?? []).map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>
        {data && (
          <div className="mt-3">
            <PeriodSummary period={data.period} coverage={data.coverage} onJumpToLatest={setPeriod} />
          </div>
        )}
      </div>

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

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && kpis && refs && (
        <>
          {data.dataNotes.length > 0 && <DataNotes notes={data.dataNotes} />}

          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            <KpiCard label="Packages" value={kpis.packing_jobs_shown.toLocaleString()}
              refs={refs.packages} fetchRefs={pager('packages')}
              help={LOGISTICS_HELP.packages} />
            <KpiCard label="Packed" value={`${kpis.packed}`}
              direction={kpis.packed ? 'up' : null} goodWhen="up"
              refs={refs.packed} fetchRefs={pager('packed')}
              help={LOGISTICS_HELP.packed} />
            <KpiCard
              label="Avg RFD Delay"
              value={kpis.avg_rfd_delay_days != null ? `${kpis.avg_rfd_delay_days.toFixed(1)} days` : '—'}
              direction={kpis.avg_rfd_delay_days != null && kpis.avg_rfd_delay_days > 0 ? 'up' : null}
              goodWhen="down"
            />
            <KpiCard label="Total Packing Cost" value={money(kpis.total_cost)}
              refs={refs.packages} fetchRefs={pager('packages')}
              help={LOGISTICS_HELP.packingCost} />
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
