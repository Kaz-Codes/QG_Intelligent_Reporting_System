import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { Card, CardContent } from '@/components/ui/card'
import { DataTable, type Column } from '@/components/DataTable'
import { StatusBadge } from '@/components/StatusBadge'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { RankedBar } from '@/components/charts/RankedBar'
import { Donut } from '@/components/charts/Donut'
import { BRAND, VIOLET } from '@/theme/tokens'
import { monthInRange } from '@/lib/format'
import {
  getStock, type StockRow,
  inventoryStatusList, inventoryReorderStatusList, inventoryCategoryList, inventoryBranchList, inventoryItemList,
} from '@/lib/mockData/inventory'

const INSIGHT_TABS = [
  { value: 'branch', label: 'Items by Branch' },
  { value: 'risk', label: 'At-Risk Rate' },
  { value: 'top', label: 'Top Items' },
] as const

const RISK_TIERS = ['Out of Stock', 'Below Reorder']

function countBy(rows: StockRow[], key: 'branch') {
  const map = new Map<string, number>()
  for (const r of rows) map.set(r[key], (map.get(r[key]) ?? 0) + 1)
  return [...map.entries()].map(([branch, items]) => ({ branch, items })).sort((a, b) => b.items - a.items)
}

export function Inventory() {
  const [status, setStatus] = useState<string[]>([])
  const [reorderStatus, setReorderStatus] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [branch, setBranch] = useState<string[]>([])
  const [item, setItem] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('branch')

  const base = useMemo(
    () => getStock({ status, reorderStatus, category, branch, item }),
    [status, reorderStatus, category, branch, item],
  )
  const dated = useMemo(
    () => base.filter((r) => monthInRange(r.last_restocked, dateFrom, dateTo)),
    [base, dateFrom, dateTo],
  )

  const data = useMemo(() => {
    if (!search.trim()) return dated
    const needle = search.toLowerCase()
    return dated.filter((r) =>
      [r.item, r.item_code, r.branch, r.item_category, r.specs].some((v) => v.toLowerCase().includes(needle)),
    )
  }, [dated, search])

  const availableUnits = data.reduce((s, r) => s + r.available_qty, 0)
  const totalStock = data.reduce((s, r) => s + r.stock_qty, 0)
  const onHold = data.reduce((s, r) => s + r.hold_qty, 0)
  const outOfStock = data.filter((r) => r.stock_status === 'Out of Stock').length
  const belowReorder = data.filter((r) => r.stock_status === 'Below Reorder').length
  const atRiskPct = data.length ? Math.round(((outOfStock + belowReorder) / data.length) * 100) : 0

  const itemsByBranch = countBy(data, 'branch')
  const atRiskByBranch = useMemo(() => {
    const map = new Map<string, { total: number; risk: number }>()
    for (const r of data) {
      const entry = map.get(r.branch) ?? { total: 0, risk: 0 }
      entry.total += 1
      if (RISK_TIERS.includes(r.stock_status)) entry.risk += 1
      map.set(r.branch, entry)
    }
    return [...map.entries()]
      .map(([branchName, v]) => ({ branch: branchName, at_risk: Math.round((v.risk / v.total) * 100) }))
      .sort((a, b) => b.at_risk - a.at_risk)
  }, [data])
  const topItems = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.item, (map.get(r.item) ?? 0) + r.stock_qty)
    return [...map.entries()].map(([item, stock_qty]) => ({ item, stock_qty })).sort((a, b) => b.stock_qty - a.stock_qty).slice(0, 8)
  }, [data])
  const lowestRunway = useMemo(
    () => data.filter((r) => r.days_of_stock != null)
      .sort((a, b) => a.days_of_stock! - b.days_of_stock!)
      .slice(0, 8)
      .map((r) => ({ item: `${r.item} (${r.branch})`, days_of_stock: r.days_of_stock })),
    [data],
  )
  const healthSplit = ['OK', 'Below Reorder', 'Out of Stock'].map((s) => ({
    label: s, value: data.filter((r) => r.stock_status === s).length,
  })).filter((s) => s.value > 0)

  const columns: Column[] = [
    { key: 'item_code', label: 'Item Code' },
    { key: 'item', label: 'Item' },
    { key: 'branch', label: 'Branch' },
    { key: 'item_category', label: 'Category' },
    { key: 'available_qty', label: 'Available', align: 'right' },
    { key: 'stock_qty', label: 'Stock Qty', align: 'right' },
    { key: 'hold_qty', label: 'On Hold', align: 'right' },
    { key: 'stock_status', label: 'Status', render: (row) => <StatusBadge label={row.stock_status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Inventory" subtitle="Current stock levels and usage-based reorder risk" module="inventory" />

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by item, item code, branch, category, or specs…' }}>
        <DateRangeFilter label="Last Restocked" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Branch" options={inventoryBranchList} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Category" options={inventoryCategoryList} value={category} onChange={setCategory} />
        <MultiSelectFilter label="Item" options={inventoryItemList} value={item} onChange={setItem} />
        <MultiSelectFilter label="Stock Status" options={inventoryStatusList} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Reorder Status" options={inventoryReorderStatusList} value={reorderStatus} onChange={setReorderStatus} />
      </FilterBar>

      {/* Spotlight: at-risk headline + stock health composition, in place of a
          trend hero — inventory is a snapshot, not a time series. */}
      <Card className="overflow-hidden border-0 text-white shadow-lg" style={{ background: `linear-gradient(135deg, ${BRAND} 0%, ${VIOLET} 100%)` }}>
        <CardContent className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_auto]">
          <div className="flex flex-col justify-center">
            <p className="text-sm font-medium text-white/70">% At Risk</p>
            <p className="font-display mt-1 text-4xl font-extrabold tracking-tight">{data.length ? `${atRiskPct}%` : '—'}</p>
            <p className="mt-1 text-xs text-white/60">out of stock + below reorder, current filter</p>
            <div className="mt-4 flex gap-3">
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">{outOfStock} out of stock</span>
              <span className="rounded-full bg-white/15 px-2.5 py-1 text-xs font-semibold">{belowReorder} below reorder</span>
            </div>
          </div>
          <div className="w-full lg:w-56">
            {data.length > 0 && <Donut labels={healthSplit.map((s) => s.label)} values={healthSplit.map((s) => s.value)} height={190} compact />}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <KpiCard label="Available Units" value={availableUnits.toLocaleString()} />
        <KpiCard label="Total Stock Qty" value={totalStock.toLocaleString()} />
        <KpiCard label="On Hold" value={onHold.toLocaleString()} sub="reserved, not available" />
        <KpiCard label="Items Shown" value={data.length.toLocaleString()} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No items match the current filter.</p>}
          {data.length > 0 && insightTab === 'branch' && <CategoryBar data={itemsByBranch} category="branch" value="items" height={300} />}
          {data.length > 0 && insightTab === 'risk' && <RankedBar data={atRiskByBranch} category="branch" value="at_risk" height={300} invertColor />}
          {data.length > 0 && insightTab === 'top' && <RankedBar data={topItems} category="item" value="stock_qty" height={300} />}
        </InsightsCard>

        <ChartCard title="Lowest Days of Stock Remaining">
          {lowestRunway.length > 0
            ? <RankedBar data={lowestRunway} category="item" value="days_of_stock" height={300} />
            : <p className="py-12 text-center text-sm text-muted">No recent issuance history to estimate a runway from.</p>}
        </ChartCard>
      </div>

      <Disclosure title="View data">
        <div className="pb-4">
          <DataTable columns={columns} rows={data as unknown as Record<string, unknown>[]} statusColumn="stock_status" height={420} />
        </div>
      </Disclosure>
    </div>
  )
}
