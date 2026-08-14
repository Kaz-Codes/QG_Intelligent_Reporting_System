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
import { Label } from '@/components/ui/label'
import { money } from '@/lib/format'
import { PURCHASES_HELP, withBasis } from '@/lib/metricHelp'
import { purchasesRefPager } from '@/lib/api/dashboardReferences'
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
  // Which procurement event the period measures. The backend resolves an
  // unknown value back to its default and echoes the choice, so this and the
  // server cannot disagree about what is being filtered.
  const [dateField, setDateField] = useState('purchase')
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('branch')
  const [search, setSearch] = useState('')

  // Every filter here is applied server-side, so the KPIs and charts below can
  // be rendered straight from the endpoint's own figures. Search is a server
  // param here, so it narrows the KPIs and charts too, not just a row table.
  const { data, isLoading, isFetching, isError, error } = usePurchasesDashboard({
    status, supplier, branch, item_category: category, mop, sourcing_o: sourcingOfficer,
    po_from_date: dateFrom || undefined, po_to_date: dateTo || undefined,
    // Both omitted = the backend's own default, the current month.
    date_from: period.from || undefined, date_to: period.to || undefined,
    date_field: dateField,
    search: search || undefined,
  })

  // Bound to the same filters the screen was rendered with, so page 2 of a
  // reference list describes the same set as page 1.
  const refs = (key: string) => purchasesRefPager(key, {
    status, supplier, branch, item_category: category, mop, sourcing_o: sourcingOfficer,
    po_from_date: dateFrom, po_to_date: dateTo,
    date_from: period.from, date_to: period.to,
    date_field: dateField, search,
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
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
            label="Reporting period" />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="purchases-date-field" className="text-xs">Filter on</Label>
            <select
              id="purchases-date-field"
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

      <FilterBar search={{
        value: search, onChange: setSearch,
        placeholder: 'PO number, item, supplier, bill…',
      }}>
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

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && kpis && (
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
            refs={data.references.orders}
            fetchRefs={refs('orders')}
          />

          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            <KpiCard label="Orders" value={kpis.orders_count.toLocaleString()}
              refs={data.references.orders}
              fetchRefs={refs('orders')}
              help={PURCHASES_HELP.orders} />
            <KpiCard label="Avg Order Value" value={kpis.orders_count ? money(kpis.avg_order_value) : '—'}
              refs={data.references.orders}
              fetchRefs={refs('orders')}
              help={PURCHASES_HELP.avgOrderValue} />
            {/* A PERCENTAGE, like On-Time beside it — the two rest on the same
                denominator and sum to 100, which a count against a percentage
                could never show. The count is in the sub-line and the list. */}
            <KpiCard label="Delayed Orders" value={kpis.orders_count ? `${kpis.delayed_pct}%` : '—'}
              sub={`${kpis.delayed_orders.toLocaleString()} of ${kpis.purchased_orders.toLocaleString()} orders`}
              direction={kpis.delayed_orders ? 'up' : null} goodWhen="down"
              refs={data.references.delayed}
              fetchRefs={refs('delayed')}
              help={PURCHASES_HELP.delayed} />
            <KpiCard label="Avg Delay"
              value={proc?.avg_delay_days != null ? `${proc.avg_delay_days} days` : '—'}
              sub={`across ${kpis.delayed_orders.toLocaleString()} late orders`}
              refs={data.delayedLineReferences}
              fetchRefs={refs('delayed_lines')}
              help={withBasis(PURCHASES_HELP.avgDelay,
                proc ? `Measured on ${proc.basis.toLocaleString()} lines that have both a purchase and a required date.` : undefined)} />
            <KpiCard label="On-Time Rate" value={kpis.orders_count ? `${kpis.on_time_pct}%` : '—'}
              sub={`${kpis.completed_orders.toLocaleString()} of ${kpis.purchased_orders.toLocaleString()} orders`}
              refs={data.references.on_time}
              fetchRefs={refs('on_time')}
              help={PURCHASES_HELP.onTimeRate} />
            <KpiCard label="Top Supplier" value={kpis.top_supplier ?? '—'}
              sub={kpis.top_supplier ? money(kpis.top_supplier_amount) : undefined}
              refs={data.references.top_supplier}
              fetchRefs={refs('top_supplier')}
              help={withBasis(PURCHASES_HELP.topSupplier,
                kpis.excluded_supplier_value || kpis.unattributed_value
                  ? [
                      kpis.excluded_supplier_value
                        ? `Import (IOL) is excluded from supplier figures; its ${money(kpis.excluded_supplier_value)} is still inside Total Value.`
                        : '',
                      kpis.unattributed_lines
                        ? `${money(kpis.unattributed_value)} carries no supplier at all (in-house purchases) and is in Total Value but in no supplier figure.`
                        : '',
                    ].filter(Boolean).join(' ')
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
                    {kpis.unattributed_lines > 0 && (
                      <> A further {money(kpis.unattributed_value)} across{' '}
                      {kpis.unattributed_lines.toLocaleString()} lines carries no supplier
                      at all — in-house purchases, where the group is buying from itself.
                      That money is in Total Value too, but in no bar here.</>
                    )}
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
