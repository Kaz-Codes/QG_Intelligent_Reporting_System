import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { HeroStat } from '@/components/HeroStat'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { DataTable, type Column } from '@/components/DataTable'
import { StatusBadge } from '@/components/StatusBadge'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money, shortDate, weeklyTrendPoints, monthInRange } from '@/lib/format'
import {
  getImports, type ImportRow,
  importStatusList, importDocumentationStatusList, importBranchList, importCategoryList, importSupplierList,
  importCustomerList, importCountryList, importShippingLineList, importModeOfShipmentList, importBankList,
} from '@/lib/mockData/imports'

const INSIGHT_TABS = [
  { value: 'status', label: 'Clearance Status' },
  { value: 'country', label: 'By Country' },
  { value: 'category', label: 'By Category' },
] as const

const OPEN_EXCLUDED = ['Arrived at Works', 'Order Cancelled']

function sumBy(rows: ImportRow[], key: 'supplier_country' | 'category' | 'supplier') {
  const map = new Map<string, number>()
  for (const r of rows) map.set(r[key], (map.get(r[key]) ?? 0) + r.total_value_pkr)
  return [...map.entries()].map(([label, total_value_pkr]) => ({ [key]: label, total_value_pkr }) as Record<string, number | string>)
    .sort((a, b) => (b.total_value_pkr as number) - (a.total_value_pkr as number))
}

export function Imports() {
  const [status, setStatus] = useState<string[]>([])
  const [documentationStatus, setDocumentationStatus] = useState<string[]>([])
  const [branch, setBranch] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [supplier, setSupplier] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [country, setCountry] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [shippingLine, setShippingLine] = useState<string[]>([])
  const [modeOfShipment, setModeOfShipment] = useState<string[]>([])
  const [bank, setBank] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('status')

  const filtered = useMemo(
    () => getImports({ status, documentationStatus, branch, category, supplier, customer, country, shippingLine, modeOfShipment, bank }),
    [status, documentationStatus, branch, category, supplier, customer, country, shippingLine, modeOfShipment, bank],
  )
  const data = useMemo(
    () => filtered.filter((r) => monthInRange(r.demand_date, dateFrom, dateTo)),
    [filtered, dateFrom, dateTo],
  )

  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) => [r.import_ref, r.customer, r.supplier].some((v) => v.toLowerCase().includes(needle)))
  }, [data, search])

  const totalValue = data.reduce((s, r) => s + r.total_value_pkr, 0)
  const totalWeight = data.reduce((s, r) => s + r.total_wt_ton, 0)
  const openCount = data.filter((r) => !OPEN_EXCLUDED.includes(r.current_status)).length
  const underClearance = data.filter((r) => r.current_status === 'Under Custom Clearance').length
  const supplierCount = new Set(data.map((r) => r.supplier)).size

  const trend = weeklyTrendPoints(data.map((r) => ({ date: r.demand_date, value: r.total_value_pkr / 1_000_000 })))
    .map((p) => ({ week: shortDate(p.week), value: Number(p.value.toFixed(2)) }))

  const statusCounts = importStatusList.map((s) => ({ label: s, value: data.filter((r) => r.current_status === s).length }))
    .filter((s) => s.value > 0)
  const byCountry = sumBy(data, 'supplier_country').slice(0, 8)
  const byCategory = sumBy(data, 'category')
  const bySupplier = sumBy(data, 'supplier').slice(0, 8)

  const columns: Column[] = [
    { key: 'import_ref', label: 'Import Ref' },
    { key: 'customer', label: 'Customer' },
    { key: 'supplier', label: 'Supplier' },
    { key: 'supplier_country', label: 'Country' },
    { key: 'total_value_pkr', label: 'Value', align: 'right', render: (row) => money(row.total_value_pkr as number) },
    { key: 'total_wt_ton', label: 'Weight (t)', align: 'right' },
    { key: 'current_status', label: 'Status', render: (row) => <StatusBadge label={row.current_status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Imports" subtitle="Import shipments, values, and customs clearance" module="imports" />

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by import ref, customer, or supplier…' }}>
        <DateRangeFilter label="ETA" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Works" options={importBranchList} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Supplier" options={importSupplierList} value={supplier} onChange={setSupplier} />
        <MultiSelectFilter label="Customer" options={importCustomerList} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Country" options={importCountryList} value={country} onChange={setCountry} />
        <MultiSelectFilter label="Item Category" options={importCategoryList} value={category} onChange={setCategory} />
        <MultiSelectFilter label="Show imports" options={importStatusList} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Documentation Status" options={importDocumentationStatusList} value={documentationStatus} onChange={setDocumentationStatus} />
      </FilterBar>

      <Disclosure title="More filters — shipping line, mode, bank">
        <div className="flex flex-wrap gap-4 pb-4">
          {[
            { label: 'Shipping Line', options: importShippingLineList, value: shippingLine, onChange: setShippingLine },
            { label: 'Mode of Shipment', options: importModeOfShipmentList, value: modeOfShipment, onChange: setModeOfShipment },
            { label: 'Bank', options: importBankList, value: bank, onChange: setBank },
          ].map((f) => (
            <div key={f.label} className="w-56">
              <MultiSelectFilter label={f.label} options={f.options} value={f.value} onChange={f.onChange} />
            </div>
          ))}
        </div>
      </Disclosure>

      <HeroStat
        label="Total Value"
        value={money(totalValue)}
        trendData={trend}
        trendX="week"
        trendY="value"
        caption="PKR millions per week, current filter"
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <KpiCard label="Total Weight" value={`${totalWeight.toLocaleString()} t`} />
        <KpiCard label="Shipments Shown" value={data.length.toLocaleString()} />
        <KpiCard label="Open" value={`${openCount}`} sub="not yet arrived/cancelled" />
        <KpiCard label="Under Clearance" value={`${underClearance}`} direction={underClearance ? 'up' : null} goodWhen="down" />
        <KpiCard label="Suppliers" value={`${supplierCount}`} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No imports match the current filter.</p>}
          {data.length > 0 && insightTab === 'status' && (
            <Donut labels={statusCounts.map((s) => s.label)} values={statusCounts.map((s) => s.value)} height={300} />
          )}
          {data.length > 0 && insightTab === 'country' && <RankedBar data={byCountry} category="supplier_country" value="total_value_pkr" height={300} />}
          {data.length > 0 && insightTab === 'category' && <CategoryBar data={byCategory} category="category" value="total_value_pkr" height={300} />}
        </InsightsCard>

        <ChartCard title="Top Suppliers (value)">
          {bySupplier.length > 0
            ? <RankedBar data={bySupplier} category="supplier" value="total_value_pkr" height={300} />
            : <p className="py-12 text-center text-sm text-muted">No supplier data in the current view.</p>}
        </ChartCard>
      </div>

      <Disclosure title="View data">
        <div className="pb-4">
          <DataTable columns={columns} rows={tableRows as unknown as Record<string, unknown>[]} statusColumn="current_status" height={420} />
        </div>
      </Disclosure>
    </div>
  )
}
