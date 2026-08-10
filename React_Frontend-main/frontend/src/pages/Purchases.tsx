import { useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { LiveDataState } from '@/components/LiveDataState'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { HeroStat } from '@/components/HeroStat'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { AgingBuckets } from '@/components/charts/AgingBuckets'
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { money } from '@/lib/format'
import { PURCHASES_HELP, withBasis } from '@/lib/metricHelp'
import { usePurchasesDashboard } from '@/lib/api/usePurchasesDashboard'

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
  // Empty = "this month", resolved by the backend.
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('branch')

  // Every filter here is applied server-side, so the KPIs and charts below can
  // be rendered straight from the endpoint's own figures. There's no search box
  // on this page: search only ever narrowed the row table, which is gone.
  const { data, isLoading, isError, error } = usePurchasesDashboard({
    status, supplier, branch, item_category: category, mop, sourcing_o: sourcingOfficer,
    po_from_date: dateFrom || undefined, po_to_date: dateTo || undefined,
    // Both omitted = the backend's own default, the current month.
    date_from: period.from || undefined, date_to: period.to || undefined,
  })

  const kpis = data?.kpis
  const proc = data?.procurementKpis
  // Buckets are sized to the window by the API — 3-day steps inside a month,
  // months across a year — and empty ones are included, so the line never
  // draws straight across a gap it has no data for.
  const trend = (data?.valueTrend?.points ?? []).map((p) => ({
    month: p.label, value: Number((p.value / 1_000_000).toFixed(2)),
  }))

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Purchases" subtitle="Track purchase orders, suppliers, and delivery status" module="purchases" />

      <div className="rounded-xl border border-line bg-surface p-4">
        <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
          label="Reporting period (purchase date)" />
        {data && (
          <div className="mt-3">
            <PeriodSummary period={data.period} coverage={data.coverage} onJumpToLatest={setPeriod} />
          </div>
        )}
      </div>

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

      <LiveDataState isLoading={isLoading} isError={isError} error={error} skeleton="dashboard" />

      {data && kpis && (
        <>
          <HeroStat
            label="Total Value"
            value={money(kpis.total_value)}
            trendData={trend}
            trendX="month"
            trendY="value"
            caption={`PKR millions per ${data.valueTrend.granularity === 'day'
              ? `${data.valueTrend.bucket_days} days` : data.valueTrend.granularity
              } — empty buckets are shown as zero, not skipped`}
            trendUnit="PKR (millions)"
          />

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Orders" value={kpis.orders_count.toLocaleString()}
              help={PURCHASES_HELP.orders} />
            <KpiCard label="Avg Order Value" value={kpis.orders_count ? money(kpis.avg_order_value) : '—'}
              help={PURCHASES_HELP.avgOrderValue} />
            <KpiCard label="Delayed Orders" value={kpis.delayed_orders.toLocaleString()}
              direction={kpis.delayed_orders ? 'up' : null} goodWhen="down"
              help={PURCHASES_HELP.delayed} />
            <KpiCard label="Avg Delay"
              value={proc?.avg_delay_days != null ? `${proc.avg_delay_days} days` : '—'}
              sub="late lines only"
              help={withBasis(PURCHASES_HELP.avgDelay,
                proc ? `Measured on ${proc.basis.toLocaleString()} lines that have both a purchase and a required date.` : undefined)} />
            <KpiCard label="On-Time Rate" value={kpis.orders_count ? `${kpis.on_time_pct}%` : '—'}
              help={PURCHASES_HELP.onTimeRate} />
            <KpiCard label="Top Supplier" value={kpis.top_supplier ?? '—'}
              sub={kpis.top_supplier ? money(kpis.top_supplier_amount) : undefined}
              help={withBasis(PURCHASES_HELP.topSupplier,
                kpis.excluded_supplier_value
                  ? `Import (IOL) is excluded from supplier figures; its ${money(kpis.excluded_supplier_value)} is still inside Total Value.`
                  : undefined)} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
              {kpis.orders_count === 0 && (
                <p className="py-12 text-center text-sm text-muted">
                  No purchases in {data.period.label}
                  {data.coverage.latest ? ` — data runs to ${data.coverage.latest}.` : '.'}
                </p>
              )}
              {kpis.orders_count > 0 && insightTab === 'branch' && (
                <CategoryBar data={data.valueByBranch} category="label" value="count"
                  valueKey="value" countNoun="order" height={300} unit="Orders" />
              )}
              {kpis.orders_count > 0 && insightTab === 'status' && (
                <Donut labels={data.statusSplit.map((s) => s.label)} values={data.statusSplit.map((s) => s.count)} height={300} />
              )}
              {kpis.orders_count > 0 && insightTab === 'suppliers' && (
                <>
                  <RankedBar data={data.valueBySupplier} category="label" value="count"
                    valueKey="value" countNoun="order" height={300} unit="Orders" />
                  <p className="mt-2 text-xs text-muted">
                    Excludes Import (IOL) — the in-house import channel rather than a
                    vendor. Its {money(kpis.excluded_supplier_value)} is still counted in
                    Total Value above.
                  </p>
                </>
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
