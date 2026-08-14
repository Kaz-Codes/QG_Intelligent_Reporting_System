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
import { DataNotes } from '@/components/DataNotes'
import { Label } from '@/components/ui/label'
import { money } from '@/lib/format'
import { IMPORTS_HELP, withBasis } from '@/lib/metricHelp'
import { useState } from 'react'
import { useImportsDashboard } from '@/lib/api/useImportsDashboard'
import { importsRefPager } from '@/lib/api/dashboardReferences'

/** The one sub-line every count-and-value tile uses, so a row reads across. */
function countLine(count: number, pct?: number | null): string {
  const base = `${count.toLocaleString()} consignment${count === 1 ? '' : 's'}`
  return pct != null ? `${base} · ${pct}% of value` : base
}


/**
 * All imports, or shafts only.
 *
 * Same control as the Overview's, and it does the same thing: narrows every
 * figure on the screen at once. The category-delay chart is withheld while it
 * is on — with the set restricted to shafts, "delay by item category" is a
 * single bar pretending to be a comparison.
 */
function ShaftsTab({ active, onChange }: { active: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="inline-flex rounded-lg border border-line p-0.5" role="tablist">
      {[
        { label: 'All imports', value: false },
        { label: 'Shafts only', value: true },
      ].map((tab) => (
        <button
          key={tab.label}
          type="button"
          role="tab"
          aria-selected={active === tab.value}
          onClick={() => onChange(tab.value)}
          className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
            active === tab.value ? 'bg-brand-soft text-brand' : 'text-muted hover:text-ink'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}


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
  const [search, setSearch] = useState('')
  // Which date the reporting window applies to — the same choice the Overview
  // offers, so the two screens can be put on one window and compared.
  const [dateField, setDateField] = useState('eta_works')
  // The Shafts tab: narrows every figure on the screen, rather than sitting
  // beside them as tiles counting a different population.
  const [shaftsOnly, setShaftsOnly] = useState(false)

  const { data, isLoading, isFetching, isError, error } = useImportsDashboard({
    work: works || undefined,
    supplier: supplier || undefined,
    country: country || undefined,
    item_category: itemCategory || undefined,
    status: status || undefined,
    from_date: dateFrom || undefined,
    to_date: dateTo || undefined,
    date_from: period.from || undefined,
    date_to: period.to || undefined,
    date_field: dateField,
    search: search || undefined,
    shafts_only: shaftsOnly,
  })

  // Bound to the same filters the screen was rendered with, so page 2 of a
  // reference list describes the same set as page 1.
  const refs = (key: string) => importsRefPager(key, {
    work: works, supplier, country, item_category: itemCategory, status,
    from_date: dateFrom, to_date: dateTo,
    date_from: period.from, date_to: period.to,
    date_field: dateField, search, shafts_only: shaftsOnly,
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
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
            label="Reporting period" />
          <div className="flex items-end gap-3">
            {/* Which date the window means. "Value that ARRIVED in August" and
                "value that was NEEDED in August" are both real questions and
                they are not the same set. */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="imports-date-field" className="text-xs">Filter on</Label>
              <select
                id="imports-date-field"
                value={dateField}
                onChange={(e) => setDateField(e.target.value)}
                className="h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
              >
                {(data?.date_field_options ?? []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <ShaftsTab active={shaftsOnly} onChange={setShaftsOnly} />
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
        placeholder: 'Payment ref, GD, supplier, item…',
      }}>
        <DateRangeFilter label="ETA at Works" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <SingleSelectFilter label="Works" options={data?.works ?? []} value={works} onChange={setWorks} />
        <SingleSelectFilter label="Supplier" options={data?.suppliers ?? []} value={supplier} onChange={setSupplier} />
        <SingleSelectFilter label="Country" options={data?.countries ?? []} value={country} onChange={setCountry} />
        <SingleSelectFilter label="Item Category" options={data?.item_categories ?? []} value={itemCategory} onChange={setItemCategory} />
        <SingleSelectFilter label="Status" options={data?.status ?? []} value={status} onChange={setStatus} />
      </FilterBar>

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && c && (
        <>
          {c.data_notes?.length > 0 && <DataNotes notes={c.data_notes} />}

          <HeroStat
            label="Total Value"
            value={money(c.kpis.total_value_pkr)}
            trendData={trend}
            trendX="month"
            trendY="value"
            caption={`PKR millions per ${c.value_trend.granularity === 'day'
              ? `${c.value_trend.bucket_days} days` : c.value_trend.granularity}, current filter`}
            trendUnit="PKR (millions)"
            refs={c.references}
            fetchRefs={refs('total')}
          />

          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            {/* The count tile is gone; In Process and Arrived are tiles of
                their own rather than a hidden status filter.

                No separate "Total Import Value" tile here on purpose: it
                duplicated the HeroStat's "Total Value" above (which carries
                the trend chart) on a DIFFERENT basis — this tile summed value
                per LINE, dated by each line's own ETA, while the hero sums
                per CONSIGNMENT, dated by the header — so the two could show
                different numbers under two labels that looked like they
                should agree. Removed instead of unified; see calculations.md
                if that basis is needed again (still served by the API as
                `period_value`, just not rendered here). */}
            <KpiCard label="In Process" value={money(c.population.in_process.value)}
              sub={countLine(c.population.in_process.count, c.population.in_process.value_pct)}
              refs={c.population.references.in_process}
              fetchRefs={refs('in_process')}
              help={IMPORTS_HELP.inProcess} />
            <KpiCard label="Arrived" value={money(c.population.arrived.value)}
              sub={countLine(c.population.arrived.count, c.population.arrived.value_pct)}
              refs={c.population.references.arrived}
              fetchRefs={refs('arrived')}
              help={IMPORTS_HELP.arrived} />
            <KpiCard label="Shafts Value" value={money(c.shafts.value)}
              sub={`${c.shafts.lines.toLocaleString()} line${c.shafts.lines === 1 ? '' : 's'} · ${c.shafts.consignments.toLocaleString()} consignment${c.shafts.consignments === 1 ? '' : 's'}`}
              refs={c.shafts.references}
              fetchRefs={refs('shafts')}
              help={withBasis(IMPORTS_HELP.shaftsValue,
                c.shafts.unpriced_lines
                  ? `${c.shafts.unpriced_lines} shaft line(s) carry no price or no booked rate, so the total is short by that much.`
                  : undefined)} />
            {/* Value on top, count under it — the same layout as the tiles
                beside it, so the row reads across. */}
            <KpiCard label="EFS Shipments" value={money(c.efs_split.efs_value)}
              sub={`${c.efs_split.efs} EFS · ${c.efs_split.regular} regular · ${c.efs_split.not_stated} not stated`}
              refs={c.efs_split.efs_references}
              fetchRefs={refs('efs')}
              help={withBasis(IMPORTS_HELP.efs,
                `${c.efs_split.efs_pct_of_stated ?? 0}% of the ${c.efs_split.stated_basis} consignments that state it. ${c.efs_split.not_stated} do not say.`)} />
            <KpiCard label="Cancelled" value={money(c.population.cancelled.value)}
              sub={countLine(c.population.cancelled.count, c.population.cancelled.value_pct)}
              refs={c.population.references.cancelled}
              fetchRefs={refs('cancelled')}
              help={IMPORTS_HELP.cancelled} />
            <KpiCard label="Delivery Delay"
              value={c.delivery_delay.delay_pct != null ? `${c.delivery_delay.delay_pct}%` : '—'}
              sub={`more than ${c.delivery_delay.grace_days} days late`}
              direction={c.delivery_delay.delayed ? 'up' : null} goodWhen="down"
              refs={c.delivery_delay.delayed_references}
              fetchRefs={refs('delayed')}
              help={withBasis(IMPORTS_HELP.deliveryDelay,
                `Measured on ${c.delivery_delay.basis} of ${c.kpis.consignments_shown} consignments; ${c.delivery_delay.not_measurable} lack one of the two dates. ${c.delivery_delay.within_grace} arrived late but inside the ${c.delivery_delay.grace_days}-day grace and count as on time.`)} />
            <KpiCard label="Avg Days Late"
              value={c.delivery_delay.avg_days_late != null ? `${c.delivery_delay.avg_days_late}` : '—'}
              sub={c.delivery_delay.worst_days_late != null ? `worst ${c.delivery_delay.worst_days_late} days` : undefined}
              refs={c.delivery_delay.delayed_references}
              fetchRefs={refs('delayed')}
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

          {/* Withheld on the Shafts tab: with the set restricted to shafts,
              "delay by item category" is one bar pretending to be a comparison.
              The backend returns null rather than the screen guessing. */}
          {c.category_delays && (
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
          )}
        </>
      )}
    </div>
  )
}
