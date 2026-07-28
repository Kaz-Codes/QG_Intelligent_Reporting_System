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
import { AgingBuckets } from '@/components/charts/AgingBuckets'
import { money, shortDate, weeklyTrendPoints, agingBuckets, monthInRange } from '@/lib/format'
import {
  getPurchases, type PurchaseRow,
  purchaseStatusList, purchaseSupplierList, purchaseBranchList, purchaseCategoryList,
  purchaseMaterialList, purchasePpcStoreList, purchaseMopList, purchaseSourcingOfficerList,
} from '@/lib/mockData/purchases'

const INSIGHT_TABS = [
  { value: 'branch', label: 'Branch' },
  { value: 'status', label: 'Status' },
  { value: 'suppliers', label: 'Suppliers' },
] as const

function sumBy(rows: PurchaseRow[], key: 'branch' | 'supplier') {
  const map = new Map<string, number>()
  for (const r of rows) map.set(r[key], (map.get(r[key]) ?? 0) + r.amount)
  return [...map.entries()].map(([label, amount]) => ({ [key]: label, amount }) as Record<string, number | string>)
    .sort((a, b) => (b.amount as number) - (a.amount as number))
}

export function Purchases() {
  const [status, setStatus] = useState<string[]>([])
  const [supplier, setSupplier] = useState<string[]>([])
  const [branch, setBranch] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [material, setMaterial] = useState<string[]>([])
  const [ppcStore, setPpcStore] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [mop, setMop] = useState<string[]>([])
  const [sourcingOfficer, setSourcingOfficer] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('branch')

  const filtered = useMemo(
    () => getPurchases({ status, supplier, branch, category, material, ppcStore, mop, sourcingOfficer }),
    [status, supplier, branch, category, material, ppcStore, mop, sourcingOfficer],
  )
  const data = useMemo(
    () => filtered.filter((r) => monthInRange(r.purchase_date, dateFrom, dateTo)),
    [filtered, dateFrom, dateTo],
  )

  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) =>
      [r.item, r.po_number, r.ref_no, r.supplier, r.bill_no].some((v) => v.toLowerCase().includes(needle)),
    )
  }, [data, search])

  const totalValue = data.reduce((s, r) => s + r.amount, 0)
  const orders = data.length
  const avgOrderValue = orders ? totalValue / orders : 0
  const delayedCount = data.filter((r) => r.status === 'Delayed').length
  const onTimePct = orders ? Math.round(((orders - delayedCount) / orders) * 100) : 0
  const topSupplier = sumBy(data, 'supplier')[0]?.supplier as string | undefined

  const trend = weeklyTrendPoints(data.map((r) => ({ date: r.purchase_date, value: r.amount / 1_000_000 })))
    .map((p) => ({ week: shortDate(p.week), value: Number(p.value.toFixed(2)) }))

  const byBranch = sumBy(data, 'branch')
  const bySupplier = sumBy(data, 'supplier').slice(0, 8)
  const statusCounts = ['Pending', 'Completed', 'Delayed'].map((s) => ({
    label: s, value: data.filter((r) => r.status === s).length,
  })).filter((s) => s.value > 0)
  const aging = agingBuckets(data.filter((r) => r.status === 'Delayed' && r.days_overdue != null).map((r) => r.days_overdue!))

  const columns: Column[] = [
    { key: 'po_number', label: 'PO Number' },
    { key: 'item', label: 'Item' },
    { key: 'supplier', label: 'Supplier' },
    { key: 'branch', label: 'Branch' },
    { key: 'quantity', label: 'Qty', align: 'right' },
    { key: 'amount', label: 'Amount', align: 'right', render: (row) => money(row.amount as number) },
    { key: 'purchase_date', label: 'Purchase Date', render: (row) => shortDate(row.purchase_date as Date) },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge label={row.status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Purchases" subtitle="Track purchase orders, suppliers, and delivery status" module="purchases" />

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by item, supplier, PO number, ref no, or bill no…' }}>
        <DateRangeFilter label="PO Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Branch" options={purchaseBranchList} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Supplier" options={purchaseSupplierList} value={supplier} onChange={setSupplier} />
        <MultiSelectFilter label="Item Category" options={purchaseCategoryList} value={category} onChange={setCategory} />
        <MultiSelectFilter label="Material" options={purchaseMaterialList} value={material} onChange={setMaterial} />
        <MultiSelectFilter label="Status" options={purchaseStatusList} value={status} onChange={setStatus} />
        <MultiSelectFilter label="PPC / Store" options={purchasePpcStoreList} value={ppcStore} onChange={setPpcStore} />
      </FilterBar>

      <Disclosure title="More filters — Mode of Purchase, Sourcing Officer">
        <div className="flex flex-wrap gap-4 pb-4">
          <div className="w-56">
            <MultiSelectFilter label="Mode of Purchase" options={purchaseMopList} value={mop} onChange={setMop} />
          </div>
          <div className="w-56">
            <MultiSelectFilter label="Sourcing Officer" options={purchaseSourcingOfficerList} value={sourcingOfficer} onChange={setSourcingOfficer} />
          </div>
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
        <KpiCard label="Orders" value={orders.toLocaleString()} />
        <KpiCard label="Avg Order Value" value={orders ? money(avgOrderValue) : '—'} />
        <KpiCard label="Delayed" value={`${delayedCount}`} direction={delayedCount ? 'up' : null} goodWhen="down" />
        <KpiCard label="On-Time Rate" value={orders ? `${onTimePct}%` : '—'} />
        <KpiCard label="Top Supplier" value={topSupplier ?? '—'} sub="by value, current filter" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No orders match the current filter.</p>}
          {data.length > 0 && insightTab === 'branch' && <CategoryBar data={byBranch} category="branch" value="amount" height={300} />}
          {data.length > 0 && insightTab === 'status' && (
            <Donut labels={statusCounts.map((s) => s.label)} values={statusCounts.map((s) => s.value)} height={300} />
          )}
          {data.length > 0 && insightTab === 'suppliers' && <RankedBar data={bySupplier} category="supplier" value="amount" height={300} />}
        </InsightsCard>

        <ChartCard title="Delayed Orders — Days Overdue">
          <AgingBuckets data={aging} height={300} />
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
