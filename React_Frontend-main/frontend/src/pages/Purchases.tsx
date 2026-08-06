import { useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { HeroStat } from '@/components/HeroStat'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { Card, CardContent } from '@/components/ui/card'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { AgingBuckets } from '@/components/charts/AgingBuckets'
import { money } from '@/lib/format'
import { usePurchasesDashboard } from '@/lib/api/usePurchasesDashboard'
import { ApiError } from '@/lib/api/auth'

const INSIGHT_TABS = [
  { value: 'branch', label: 'Branch' },
  { value: 'status', label: 'Status' },
  { value: 'suppliers', label: 'Suppliers' },
] as const

export function Purchases() {
  const [status, setStatus] = useState<string[]>([])
  const [supplier, setSupplier] = useState<string[]>([])
  const [branch, setBranch] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [mop, setMop] = useState<string[]>([])
  const [sourcingOfficer, setSourcingOfficer] = useState<string[]>([])
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('branch')

  // Every filter here is applied server-side, so the KPIs and charts below can
  // be rendered straight from the endpoint's own figures. There's no search box
  // on this page: search only ever narrowed the row table, which is gone.
  const { data, isLoading, isError, error } = usePurchasesDashboard({
    status, supplier, branch, item_category: category, mop, sourcing_o: sourcingOfficer,
    po_from_date: dateFrom || undefined, po_to_date: dateTo || undefined,
  })

  const kpis = data?.kpis
  const trend = (data?.monthlyValueTrend ?? []).map((p) => ({ month: p.month, value: Number((p.value / 1_000_000).toFixed(2)) }))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Purchases" subtitle="Track purchase orders, suppliers, and delivery status" module="purchases" />

      <FilterBar>
        <DateRangeFilter label="PO Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Branch" options={data?.branches ?? []} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Supplier" options={data?.suppliers ?? []} value={supplier} onChange={setSupplier} />
        <MultiSelectFilter label="Item Category" options={data?.itemCategories ?? []} value={category} onChange={setCategory} />
        <MultiSelectFilter label="Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
      </FilterBar>

      <Disclosure title="More filters — Mode of Purchase, Sourcing Officer">
        <div className="flex flex-wrap gap-4 pb-4">
          <div className="w-56">
            <MultiSelectFilter label="Mode of Purchase" options={data?.mops ?? []} value={mop} onChange={setMop} />
          </div>
          <div className="w-56">
            <MultiSelectFilter label="Sourcing Officer" options={data?.sourcingOfficers ?? []} value={sourcingOfficer} onChange={setSourcingOfficer} />
          </div>
        </div>
      </Disclosure>

      {isLoading && (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted">Loading live data…</CardContent>
        </Card>
      )}

      {isError && (
        <Card>
          <CardContent className="flex items-start gap-2 p-5 text-sm text-risk">
            <ShieldAlert size={16} className="mt-0.5 shrink-0" />
            <span>
              {error instanceof ApiError && error.status === 401
                ? 'Signed in, but not with an account the backend recognizes yet — only the seeded admin account has live access right now.'
                : 'Could not reach the backend — is it running?'}
            </span>
          </CardContent>
        </Card>
      )}

      {data && kpis && (
        <>
          <HeroStat
            label="Total Value"
            value={money(kpis.total_value)}
            trendData={trend}
            trendX="month"
            trendY="value"
            caption="PKR millions per month, current filter"
            trendUnit="PKR (millions)"
          />

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <KpiCard label="Orders" value={kpis.orders_count.toLocaleString()} />
            <KpiCard label="Avg Order Value" value={kpis.orders_count ? money(kpis.avg_order_value) : '—'} />
            <KpiCard label="Delayed" value={`${kpis.delayed_orders}`} direction={kpis.delayed_orders ? 'up' : null} goodWhen="down" />
            <KpiCard label="On-Time Rate" value={kpis.orders_count ? `${kpis.on_time_pct}%` : '—'} />
            <KpiCard label="Top Supplier" value={kpis.top_supplier ?? '—'} sub="by value, current filter" />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
              {kpis.orders_count === 0 && <p className="py-12 text-center text-sm text-muted">No orders match the current filter.</p>}
              {kpis.orders_count > 0 && insightTab === 'branch' && (
                <CategoryBar data={data.valueByBranch} category="label" value="value" height={300} unit="PKR" />
              )}
              {kpis.orders_count > 0 && insightTab === 'status' && (
                <Donut labels={data.statusSplit.map((s) => s.label)} values={data.statusSplit.map((s) => s.value)} height={300} />
              )}
              {kpis.orders_count > 0 && insightTab === 'suppliers' && (
                <RankedBar data={data.valueBySupplier} category="label" value="value" height={300} unit="PKR" />
              )}
            </InsightsCard>

            <ChartCard title="Delayed Orders — Days Overdue">
              <AgingBuckets data={data.overdueBuckets} height={300} unit="Orders" />
            </ChartCard>
          </div>

        </>
      )}
    </div>
  )
}
