import { PageHeader } from '@/components/PageHeader'
import { LiveDataState } from '@/components/LiveDataState'
import { FilterBar } from '@/components/FilterBar'
import { SingleSelectFilter } from '@/components/SingleSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { KpiCard } from '@/components/KpiCard'
import { HeroStat } from '@/components/HeroStat'
import { ChartCard } from '@/components/ChartCard'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { money } from '@/lib/format'
import { IMPORTS_HELP, withBasis } from '@/lib/metricHelp'
import { useState } from 'react'
import { useImportsDashboard } from '@/lib/api/useImportsDashboard'

export function Imports() {
  const [works, setWorks] = useState('')
  const [supplier, setSupplier] = useState('')
  const [country, setCountry] = useState('')
  const [itemCategory, setItemCategory] = useState('')
  const [status, setStatus] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  // Empty = "this month", resolved by the backend.
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)

  const { data, isLoading, isError, error } = useImportsDashboard({
    work: works || undefined,
    supplier: supplier || undefined,
    country: country || undefined,
    item_category: itemCategory || undefined,
    status: status || undefined,
    from_date: dateFrom || undefined,
    to_date: dateTo || undefined,
    date_from: period.from || undefined,
    date_to: period.to || undefined,
  })

  const c = data?.consignments
  // Buckets sized to the window by the API (3-day steps inside a month), with
  // empty ones kept so the line never spans a gap it has no data for.
  const trend =
    c?.value_trend.points.map((p) => ({ month: p.label, value: Number((p.value / 1_000_000).toFixed(2)) })) ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Imports" subtitle="Import shipments, values, and customs clearance" module="imports" />

      <div className="rounded-xl border border-line bg-surface p-4">
        <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
          label="Reporting period (ETA at Works)" />
        {data && (
          <div className="mt-3">
            <PeriodSummary period={data.period} coverage={data.coverage} onJumpToLatest={setPeriod} />
          </div>
        )}
      </div>

      <FilterBar>
        <DateRangeFilter label="ETA at Works" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <SingleSelectFilter label="Works" options={data?.works ?? []} value={works} onChange={setWorks} />
        <SingleSelectFilter label="Supplier" options={data?.suppliers ?? []} value={supplier} onChange={setSupplier} />
        <SingleSelectFilter label="Country" options={data?.countries ?? []} value={country} onChange={setCountry} />
        <SingleSelectFilter label="Item Category" options={data?.item_categories ?? []} value={itemCategory} onChange={setItemCategory} />
        <SingleSelectFilter label="Status" options={data?.status ?? []} value={status} onChange={setStatus} />
      </FilterBar>

      <LiveDataState isLoading={isLoading} isError={isError} error={error} skeleton="dashboard" />

      {data && c && (
        <>
          <HeroStat
            label="Total Value"
            value={money(c.kpis.total_value_pkr)}
            trendData={trend}
            trendX="month"
            trendY="value"
            caption={`PKR millions per ${c.value_trend.granularity === 'day'
              ? `${c.value_trend.bucket_days} days` : c.value_trend.granularity}, current filter`}
            trendUnit="PKR (millions)"
          />

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Consignments" value={c.kpis.consignments_shown.toLocaleString()}
              help={IMPORTS_HELP.consignments} />
            <KpiCard label="Shafts Value" value={money(c.shafts.value)}
              sub={`across ${c.shafts.consignments} consignments`}
              help={withBasis(IMPORTS_HELP.shaftsValue,
                c.shafts.incomplete_consignments
                  ? `${c.shafts.incomplete_consignments} consignment(s) have a shaft row with no price or booked rate, so the total is short by that much.`
                  : undefined)} />
            <KpiCard label="EFS Shipments" value={c.efs_split.efs.toLocaleString()}
              sub={`${c.efs_split.regular} regular · ${c.efs_split.not_stated} not stated`}
              help={withBasis(IMPORTS_HELP.efs,
                `${c.efs_split.efs_pct_of_stated ?? 0}% of the ${c.efs_split.stated_basis} consignments that state it. ${c.efs_split.not_stated} do not say.`)} />
            <KpiCard label="In Process" value={c.demands.in_process.toLocaleString()}
              sub={`${c.demands.processed} processed`}
              help={IMPORTS_HELP.inProcess} />
            <KpiCard label="Delivery Delay"
              value={c.delivery_delay.delay_pct != null ? `${c.delivery_delay.delay_pct}%` : '—'}
              direction={c.delivery_delay.delayed ? 'up' : null} goodWhen="down"
              help={withBasis(IMPORTS_HELP.deliveryDelay,
                `Measured on ${c.delivery_delay.basis} of ${c.kpis.consignments_shown} consignments; ${c.delivery_delay.not_measurable} lack one of the two dates.`)} />
            <KpiCard label="Avg Days Late"
              value={c.delivery_delay.avg_days_late != null ? `${c.delivery_delay.avg_days_late}` : '—'}
              sub={c.delivery_delay.worst_days_late != null ? `worst ${c.delivery_delay.worst_days_late} days` : undefined}
              help={withBasis(IMPORTS_HELP.avgDaysLate,
                `Averaged over the ${c.delivery_delay.delayed} delayed consignments only.`)} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard title="Consignments by Country" className="lg:col-span-2">
              {c.value_by_country.length > 0 ? (
                <RankedBar data={c.value_by_country} category="label" value="count"
                  valueKey="value" countNoun="consignment" height={280} unit="Consignments" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No country data in the current view.</p>
              )}
            </ChartCard>

            <ChartCard title="Status Split">
              {c.status_split.length > 0 ? (
                <Donut
                  labels={c.status_split.map((s) => s.label)}
                  values={c.status_split.map((s) => s.count)}
                  height={260}
                />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No status breakdown yet.</p>
              )}
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* The plain "value by supplier" bar was dropped: this is the same
                breakdown with the cumulative line, so the other was a strictly
                worse copy of it. */}
            <ChartCard title="Consignments by Supplier">
              {c.supplier_pareto.rows.length > 0 ? (
                <>
                  <RankedBar data={c.supplier_pareto.rows} category="label" value="count"
                    valueKey="value" countNoun="consignment" height={280} unit="Consignments" />
                  <p className="mt-2 text-xs text-muted">
                    Top {c.supplier_pareto.rows.length} of {c.supplier_pareto.suppliers_total} suppliers.
                    The top {c.supplier_pareto.rows.length} account for{' '}
                    {c.supplier_pareto.rows[c.supplier_pareto.rows.length - 1]?.cumulative_pct ?? 0}% of spend.
                  </p>
                </>
              ) : (
                <p className="py-12 text-center text-sm text-muted">No supplier data in the current view.</p>
              )}
            </ChartCard>

            <ChartCard title="Consignments by Works">
              {c.value_by_branch.length > 0 ? (
                <RankedBar data={c.value_by_branch} category="label" value="count"
                  valueKey="value" countNoun="consignment" height={300} unit="Consignments" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No branch data in the current view.</p>
              )}
            </ChartCard>
          </div>

          <ChartCard title="Category Delays">
            {c.category_delays.length > 0 ? (
              <>
                <p className="-mt-2 mb-3 text-xs text-muted">
                  Ranked by the NUMBER of delayed consignments, not the percentage — a
                  category with one late consignment at 100% is noise, not a problem.
                  A consignment counts once for every category it carries.
                </p>
                <RankedBar data={c.category_delays} category="category" value="delayed" height={280} invertColor unit="Delayed consignments" />
              </>
            ) : (
              <p className="py-12 text-center text-sm text-muted">
                No consignment in this period has both a required date and an ETA Works,
                so delay cannot be measured.
              </p>
            )}
          </ChartCard>
        </>
      )}
    </div>
  )
}
