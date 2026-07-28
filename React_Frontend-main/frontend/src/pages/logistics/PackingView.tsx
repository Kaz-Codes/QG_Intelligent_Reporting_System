import { useMemo, useState } from 'react'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { DataTable, type Column } from '@/components/DataTable'
import { StatusBadge } from '@/components/StatusBadge'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money, monthInRange } from '@/lib/format'
import {
  getPacking, packingStatusList, packingWorksList, packingCategoryList, packingBusinessTypeList, packingCustomerList,
} from '@/lib/mockData/logistics'

const TABS = [
  { value: 'status', label: 'Status' },
  { value: 'category', label: 'By Category' },
  { value: 'biztype', label: 'By Business Type' },
] as const

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

  const filtered = useMemo(
    () => getPacking({ status, works, productCategory, businessType, customer }),
    [status, works, productCategory, businessType, customer],
  )
  const data = useMemo(
    () => filtered.filter((r) => monthInRange(r.packing_date, dateFrom, dateTo)),
    [filtered, dateFrom, dateTo],
  )
  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) => [r.customer, r.jobs_no, r.product_category].some((v) => v.toLowerCase().includes(needle)))
  }, [data, search])

  const pending = data.filter((r) => r.status === 'Pending Packing').length
  const inProgress = data.filter((r) => r.status === 'In Progress').length
  const delaySrc = data.filter((r) => r.rfd_delay_days != null)
  const avgDelay = delaySrc.length ? delaySrc.reduce((s, r) => s + r.rfd_delay_days!, 0) / delaySrc.length : null
  const totalCost = data.reduce((s, r) => s + r.actual_packing_cost, 0)
  const categories = new Set(data.map((r) => r.product_category)).size

  const byStatus = [...new Set(data.map((r) => r.status))].map((s) => ({ label: s, value: data.filter((r) => r.status === s).length }))
  const byCategory = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.product_category, (map.get(r.product_category) ?? 0) + 1)
    return [...map.entries()].map(([category, jobs]) => ({ category, jobs })).sort((a, b) => b.jobs - a.jobs).slice(0, 8)
  }, [data])
  const byBizType = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.business_type, (map.get(r.business_type) ?? 0) + 1)
    return [...map.entries()].map(([business_type, jobs]) => ({ business_type, jobs })).sort((a, b) => b.jobs - a.jobs)
  }, [data])
  const byCustomer = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.customer, (map.get(r.customer) ?? 0) + 1)
    return [...map.entries()].map(([customer, jobs]) => ({ customer, jobs })).sort((a, b) => b.jobs - a.jobs).slice(0, 8)
  }, [data])

  const columns: Column[] = [
    { key: 'jobs_no', label: 'Job No' },
    { key: 'customer', label: 'Customer' },
    { key: 'works', label: 'Works' },
    { key: 'product_category', label: 'Category' },
    { key: 'business_type', label: 'Business Type' },
    { key: 'actual_packing_cost', label: 'Cost', align: 'right', render: (row) => money(row.actual_packing_cost as number) },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge label={row.status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by customer, job no, or product category…' }}>
        <DateRangeFilter label="Packing Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Customer" options={packingCustomerList} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Works" options={packingWorksList} value={works} onChange={setWorks} />
        <MultiSelectFilter label="Product Category" options={packingCategoryList} value={productCategory} onChange={setProductCategory} />
        <MultiSelectFilter label="Overall Status" options={packingStatusList} value={status} onChange={setStatus} />
      </FilterBar>

      <Disclosure title="More filters — Business Type">
        <div className="flex flex-wrap gap-4 pb-4">
          <div className="w-56">
            <MultiSelectFilter label="Business Type" options={packingBusinessTypeList} value={businessType} onChange={setBusinessType} />
          </div>
        </div>
      </Disclosure>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Packing Jobs Shown" value={data.length.toLocaleString()} />
        <KpiCard label="Pending Packing" value={`${pending}`} direction={pending ? 'up' : null} goodWhen="down" />
        <KpiCard label="In Progress" value={`${inProgress}`} />
        <KpiCard label="Avg RFD Delay" value={avgDelay != null ? `${avgDelay.toFixed(1)} days` : '—'}
          direction={avgDelay != null && avgDelay > 0 ? 'up' : null} goodWhen="down" />
        <KpiCard label="Total Packing Cost" value={money(totalCost)} />
        <KpiCard label="Product Categories" value={`${categories}`} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={TABS} active={tab} onChange={setTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No packing jobs match the current filter.</p>}
          {data.length > 0 && tab === 'status' && <Donut labels={byStatus.map((s) => s.label)} values={byStatus.map((s) => s.value)} height={300} />}
          {data.length > 0 && tab === 'category' && <RankedBar data={byCategory} category="category" value="jobs" height={300} />}
          {data.length > 0 && tab === 'biztype' && <CategoryBar data={byBizType} category="business_type" value="jobs" height={300} />}
        </InsightsCard>
        <ChartCard title="By Customer (job count)">
          {byCustomer.length > 0
            ? <RankedBar data={byCustomer} category="customer" value="jobs" height={300} />
            : <p className="py-12 text-center text-sm text-muted">No customer data in the current view.</p>}
        </ChartCard>
      </div>

      <Disclosure title="View data">
        <div className="pb-4">
          <DataTable columns={columns} rows={tableRows as unknown as Record<string, unknown>[]} statusColumn="status" height={420} />
        </div>
      </Disclosure>
    </div>
  )
}
