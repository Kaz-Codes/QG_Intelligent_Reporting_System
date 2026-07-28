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
  getShipments, shipmentStatusList, shipmentStageList, shipmentShippingLineList, shipmentCountryList, shipmentCustomerList,
} from '@/lib/mockData/logistics'

const TABS = [
  { value: 'status', label: 'Status' },
  { value: 'country', label: 'By Country' },
  { value: 'pod', label: 'By Port' },
] as const

function countBy<T>(rows: T[], key: keyof T, label: string) {
  const map = new Map<string, number>()
  for (const r of rows) {
    const k = String(r[key])
    map.set(k, (map.get(k) ?? 0) + 1)
  }
  return [...map.entries()].map(([k, v]) => ({ [key]: k, [label]: v }) as Record<string, number | string>)
    .sort((a, b) => (b[label] as number) - (a[label] as number))
}

export function ShipmentsView() {
  const [status, setStatus] = useState<string[]>([])
  const [stage, setStage] = useState<string[]>([])
  const [shippingLine, setShippingLine] = useState<string[]>([])
  const [country, setCountry] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')

  const filtered = useMemo(
    () => getShipments({ status, stage, shippingLine, country, customer }),
    [status, stage, shippingLine, country, customer],
  )
  const data = useMemo(
    () => filtered.filter((r) => monthInRange(r.port_in_date, dateFrom, dateTo)),
    [filtered, dateFrom, dateTo],
  )
  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) => [r.exp_no, r.customer, r.country].some((v) => v.toLowerCase().includes(needle)))
  }, [data, search])

  const delivered = data.filter((r) => r.status === 'Delivered').length
  const unlinked = data.filter((r) => r.export_id === null).length
  const totalCost = data.reduce((s, r) => s + r.total_logistics_cost, 0)
  const avgCostPerKg = data.length ? data.reduce((s, r) => s + r.cost_per_kg, 0) / data.length : 0
  const countries = new Set(data.map((r) => r.country)).size

  const byStatus = [...new Set(data.map((r) => r.status))].map((s) => ({ label: s, value: data.filter((r) => r.status === s).length }))
  const byCountry = countBy(data, 'country', 'shipments').slice(0, 8)
  const byPod = countBy(data, 'pod', 'shipments')
  const costByCountry = useMemo(() => {
    const map = new Map<string, { sum: number; n: number }>()
    for (const r of data) {
      const e = map.get(r.country) ?? { sum: 0, n: 0 }
      e.sum += r.cost_per_kg; e.n += 1
      map.set(r.country, e)
    }
    return [...map.entries()].map(([country_, v]) => ({ country: country_, cost_per_kg: Math.round(v.sum / v.n) }))
      .sort((a, b) => b.cost_per_kg - a.cost_per_kg).slice(0, 8)
  }, [data])

  const columns: Column[] = [
    { key: 'exp_no', label: 'Export No' },
    { key: 'customer', label: 'Customer' },
    { key: 'country', label: 'Country' },
    { key: 'pod', label: 'Port of Discharge' },
    { key: 'shipping_line', label: 'Shipping Line' },
    { key: 'total_logistics_cost', label: 'Cost', align: 'right', render: (row) => money(row.total_logistics_cost as number) },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge label={row.status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by export no, customer, or country…' }}>
        <DateRangeFilter label="ETD" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Customer" options={shipmentCustomerList} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Shipment Stage" options={shipmentStageList} value={stage} onChange={setStage} />
        <MultiSelectFilter label="Shipment Status" options={shipmentStatusList} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Shipping Line" options={shipmentShippingLineList} value={shippingLine} onChange={setShippingLine} />
        <MultiSelectFilter label="Country" options={shipmentCountryList} value={country} onChange={setCountry} />
      </FilterBar>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Shipments Shown" value={data.length.toLocaleString()} />
        <KpiCard label="Delivered" value={`${delivered}`} direction={delivered ? 'up' : null} goodWhen="up" />
        <KpiCard label="Not Yet Linked" value={`${unlinked}`} sub="tracked ahead of the export record" />
        <KpiCard label="Total Logistics Cost" value={money(totalCost)} />
        <KpiCard label="Avg Cost / kg" value={data.length ? `PKR ${avgCostPerKg.toFixed(1)}` : '—'} />
        <KpiCard label="Countries" value={`${countries}`} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={TABS} active={tab} onChange={setTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No shipments match the current filter.</p>}
          {data.length > 0 && tab === 'status' && <Donut labels={byStatus.map((s) => s.label)} values={byStatus.map((s) => s.value)} height={300} />}
          {data.length > 0 && tab === 'country' && <RankedBar data={byCountry} category="country" value="shipments" height={300} />}
          {data.length > 0 && tab === 'pod' && <CategoryBar data={byPod} category="pod" value="shipments" height={300} />}
        </InsightsCard>
        <ChartCard title="Avg Cost / kg by Country">
          {costByCountry.length > 0
            ? <RankedBar data={costByCountry} category="country" value="cost_per_kg" height={300} />
            : <p className="py-12 text-center text-sm text-muted">No cost/kg data in the current view.</p>}
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
