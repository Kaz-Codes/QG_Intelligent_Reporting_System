import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { SegmentedControl } from '@/components/SegmentedControl'
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
  getPurchases,
  purchaseBranchList, purchaseCategoryList,
} from '@/lib/mockData/purchases'
import { getStock } from '@/lib/mockData/inventory'
import { getImports } from '@/lib/mockData/imports'

// The Reports tab is a consolidated, read-only executive view. Unlike the
// per-module dashboards it doesn't own its own data — it pulls the same mock
// sources (later: same API endpoints) into one comparable summary. A single
// module switch drives the whole page so the layout stays identical across
// modules and only the numbers change.
const MODULES = [
  { value: 'purchases', label: 'Purchases' },
  { value: 'inventory', label: 'Inventory' },
  { value: 'imports', label: 'Imports' },
] as const

type ModuleKey = (typeof MODULES)[number]['value']

const INSIGHT_TABS = [
  { value: 'branch', label: 'By Branch' },
  { value: 'category', label: 'By Category' },
  { value: 'status', label: 'By Status' },
] as const

type InsightTab = (typeof INSIGHT_TABS)[number]['value']

interface Normalized {
  ref: string
  name: string
  branch: string
  category: string
  status: string
  value: number
  date: Date
}

// Collapse each module's row shape into one comparable record so the summary
// KPIs, charts and table are written once rather than three times.
function normalize(module: ModuleKey, branch: string[], category: string[]): Normalized[] {
  if (module === 'purchases') {
    return getPurchases({ branch, category }).map((r) => ({
      ref: r.po_number, name: r.item, branch: r.branch, category: r.category,
      status: r.status, value: r.amount, date: r.purchase_date,
    }))
  }
  if (module === 'imports') {
    return getImports({ branch, category }).map((r) => ({
      ref: r.import_ref, name: r.customer, branch: r.branch, category: r.category,
      status: r.current_status, value: r.total_value_pkr, date: r.demand_date,
    }))
  }
  // inventory — value here is available quantity, not PKR. Stock is a
  // point-in-time snapshot with no real date, so spread rows across recent
  // weeks purely to give the hero trend a meaningful shape (never presented
  // as a real time series).
  const now = Date.now()
  return getStock({ branch, category }).map((r, i) => ({
    ref: r.item_code, name: r.item, branch: r.branch, category: r.item_category,
    status: r.stock_status, value: r.available_qty,
    date: new Date(now - (i % 12) * 7 * 24 * 60 * 60 * 1000),
  }))
}

function sumBy(rows: Normalized[], key: 'branch' | 'category') {
  const map = new Map<string, number>()
  for (const r of rows) map.set(r[key], (map.get(r[key]) ?? 0) + r.value)
  return [...map.entries()]
    .map(([label, value]) => ({ [key]: label, value }) as Record<string, number | string>)
    .sort((a, b) => (b.value as number) - (a.value as number))
}

function toCsv(rows: Normalized[], isInventory: boolean): string {
  const header = ['Ref', 'Name', 'Branch', 'Category', 'Status', isInventory ? 'Available Qty' : 'Value (PKR)']
  const lines = rows.map((r) =>
    [r.ref, r.name, r.branch, r.category, r.status, r.value]
      .map((c) => {
        const s = String(c)
        return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
      })
      .join(','),
  )
  return [header.join(','), ...lines].join('\n')
}

export function Reports() {
  const [module, setModule] = useState<ModuleKey>('purchases')
  const [branch, setBranch] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [insightTab, setInsightTab] = useState<InsightTab>('branch')
  const [search, setSearch] = useState('')

  const isInventory = module === 'inventory'

  const normalized = useMemo(() => normalize(module, branch, category), [module, branch, category])
  const data = useMemo(
    () => normalized.filter((r) => monthInRange(r.date, dateFrom, dateTo)),
    [normalized, dateFrom, dateTo],
  )

  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) =>
      [r.ref, r.name, r.branch, r.category, r.status].some((v) => v.toLowerCase().includes(needle)),
    )
  }, [data, search])

  const total = data.reduce((s, r) => s + r.value, 0)
  const count = data.length
  const avg = count ? total / count : 0
  const branches = new Set(data.map((r) => r.branch)).size
  const topBranch = sumBy(data, 'branch')[0]?.branch as string | undefined

  const valueLabel = isInventory ? 'Total Available Qty' : 'Total Value'
  const fmtValue = (v: number) => (isInventory ? Math.round(v).toLocaleString() : money(v))

  const trend = weeklyTrendPoints(
    data.map((r) => ({ date: r.date, value: isInventory ? r.value : r.value / 1_000_000 })),
  ).map((p) => ({ week: shortDate(p.week), value: Number(p.value.toFixed(2)) }))

  const byBranch = sumBy(data, 'branch')
  const byCategory = sumBy(data, 'category').slice(0, 8)

  const statusCounts = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.status, (map.get(r.status) ?? 0) + 1)
    return [...map.entries()].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value)
  }, [data])

  const columns: Column[] = [
    { key: 'ref', label: 'Ref' },
    { key: 'name', label: 'Name' },
    { key: 'branch', label: 'Branch' },
    { key: 'category', label: 'Category' },
    {
      key: 'value',
      label: isInventory ? 'Available Qty' : 'Value',
      align: 'right',
      render: (row) => fmtValue(row.value as number),
    },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge label={row.status as string} /> },
  ]

  function handleExport() {
    const csv = toCsv(tableRows, isInventory)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `qg-irs-report-${module}-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title="Reports"
          subtitle="Consolidated cross-module summary — switch module to compare"
          module="reports"
        />
        <SegmentedControl options={MODULES} value={module} onChange={setModule} />
      </div>

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by ref, name, branch, category, or status…' }}>
        <DateRangeFilter label="Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Branch" options={purchaseBranchList} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Category" options={purchaseCategoryList} value={category} onChange={setCategory} />
      </FilterBar>

      <HeroStat
        label={valueLabel}
        value={fmtValue(total)}
        trendData={trend}
        trendX="week"
        trendY="value"
        caption={isInventory ? 'Available qty per week, current filter' : 'PKR millions per week, current filter'}
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <KpiCard label="Records" value={count.toLocaleString()} />
        <KpiCard label={isInventory ? 'Avg Qty / Item' : 'Avg Value'} value={count ? fmtValue(avg) : '—'} />
        <KpiCard label="Branches" value={`${branches}`} />
        <KpiCard label="Top Branch" value={topBranch ?? '—'} sub="by value, current filter" />
        <KpiCard label="Status Types" value={`${statusCounts.length}`} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard
          title="Breakdown"
          tabs={INSIGHT_TABS}
          active={insightTab}
          onChange={setInsightTab}
          className="lg:col-span-2"
        >
          {data.length === 0 && (
            <p className="py-12 text-center text-sm text-muted">No records match the current filter.</p>
          )}
          {data.length > 0 && insightTab === 'branch' && (
            <CategoryBar data={byBranch} category="branch" value="value" height={300} />
          )}
          {data.length > 0 && insightTab === 'category' && (
            <RankedBar data={byCategory} category="category" value="value" height={300} />
          )}
          {data.length > 0 && insightTab === 'status' && (
            <Donut labels={statusCounts.map((s) => s.label)} values={statusCounts.map((s) => s.value)} height={300} />
          )}
        </InsightsCard>

        <ChartCard title="Status Split">
          {statusCounts.length > 0 ? (
            <Donut
              labels={statusCounts.map((s) => s.label)}
              values={statusCounts.map((s) => s.value)}
              height={300}
              compact
            />
          ) : (
            <p className="py-12 text-center text-sm text-muted">No data.</p>
          )}
        </ChartCard>
      </div>

      <Disclosure title="View data / export">
        <div className="flex flex-col gap-3 pb-4">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleExport}
              disabled={tableRows.length === 0}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-surface px-3 text-sm font-medium text-ink transition-colors hover:bg-canvas-alt disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Download size={15} />
              Export CSV
            </button>
          </div>
          <DataTable
            columns={columns}
            rows={tableRows as unknown as Record<string, unknown>[]}
            statusColumn="status"
            height={420}
          />
        </div>
      </Disclosure>
    </div>
  )
}
