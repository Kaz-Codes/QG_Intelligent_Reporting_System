import { useState } from 'react'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { KpiCard } from '@/components/KpiCard'
import { ChartCard } from '@/components/ChartCard'
import { LiveDataState } from '@/components/LiveDataState'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money } from '@/lib/format'
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { DataNotes } from '@/components/DataNotes'
import { Label } from '@/components/ui/label'
import { LOGISTICS_HELP, withBasis } from '@/lib/metricHelp'
import { useDebounced } from '@/lib/useDebounced'
import { useShipmentsDashboard } from '@/lib/api/useLogisticsDashboard'
import { logisticsRefPager } from '@/lib/api/dashboardReferences'

/**
 * Backed by /dashboard/logistics/shipments. Every filter is a server-side
 * param, and the KPIs and charts are the endpoint's own figures.
 *
 * The Insights tab switcher is gone: it offered Status / By Country / By Port,
 * but the endpoint only computes a status split and cost-per-kg by country —
 * there's no shipment count by country or by port to switch to. One chart
 * doesn't need a tab bar, so it's a plain card until those figures exist.
 *
 * THE TAB IS "EXPORT SHIPMENTS", and that is accurate rather than a
 * simplification: local orders carry no date at all — no ETD, no arrival, no
 * gate-out — so every windowed view of this screen contains only exports.
 *
 * That is also why there is no Local/Export FILTER. Filtering a windowed screen
 * by a type only one value of which is ever dated would have appeared to work
 * while always returning nothing for local.
 *
 * The Orders tile shows the split anyway. Its zero for local is explained in
 * the tooltip rather than by a tile of its own: those orders exist, they simply
 * carry no date and so fall in no period.
 */
export function ShipmentsView() {
  const [status, setStatus] = useState<string[]>([])
  const [stage, setStage] = useState<string[]>([])
  const [shippingLine, setShippingLine] = useState<string[]>([])
  const [country, setCountry] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  // Empty = this month, resolved by the backend.
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)
  // Sailing or arrival. "What sailed in August" and "what landed in August" are
  // different questions and neither is the obvious default for everyone.
  const [dateField, setDateField] = useState('etd')

  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isFetching, isError, error } = useShipmentsDashboard({
    status, stage, shipping_line: shippingLine, country, customer,
    etd_from: dateFrom || undefined, etd_to: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
    date_from: period.from || undefined,
    date_to: period.to || undefined,
    date_field: dateField,
  })

  const kpis = data?.kpis
  const refs = data?.references

  // Bound to the same filters the screen was rendered with, so page 2 of a
  // reference list describes the same set as page 1.
  const pager = (key: string) => logisticsRefPager(key, {
    tab: 'shipments',
    status, stage, shipping_line: shippingLine, country, customer,
    etd_from: dateFrom, etd_to: dateTo, search: debouncedSearch.trim(),
    date_from: period.from, date_to: period.to, date_field: dateField,
  })

  return (
    <div className="flex flex-col gap-6">
      {/* The window, and which date it means. Same control, same wording and
          same "jump to the latest month with data" as every other dashboard. */}
      <div className="rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
            label="Reporting period" />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="shipments-date-field" className="text-xs">Filter on</Label>
            <select
              id="shipments-date-field"
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

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by export no, customer, or country…' }}>
        <DateRangeFilter label="ETD" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Customer" options={data?.customers ?? []} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Shipment Stage" options={data?.stages ?? []} value={stage} onChange={setStage} />
        <MultiSelectFilter label="Shipment Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Shipping Line" options={data?.shippingLines ?? []} value={shippingLine} onChange={setShippingLine} />
        <MultiSelectFilter label="Country" options={data?.countries ?? []} value={country} onChange={setCountry} />
      </FilterBar>

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && kpis && refs && (
        <>
          {/* Where these figures rest on a partly-filled column, said here
              rather than left to be discovered. */}
          {data.dataNotes.length > 0 && <DataNotes notes={data.dataNotes} />}

          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            <KpiCard label="Orders"
              value={data.orderTypeCounts.total.toLocaleString()}
              sub={`${data.orderTypeCounts.export.toLocaleString()} export · ${data.orderTypeCounts.local.toLocaleString()} local · ${data.orderTypeCounts.not_stated.toLocaleString()} not stated`}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={withBasis(LOGISTICS_HELP.orderTypes,
                data.orderTypeCounts.undated.total
                  ? `${data.orderTypeCounts.undated.total.toLocaleString()} orders carry no ${data.dateField.toUpperCase()} at all and fall in no period — ${data.orderTypeCounts.undated.local.toLocaleString()} of them local. Open the Undated tile to see them.`
                  : undefined)} />
            <KpiCard label="Shipments" value={kpis.shipments_shown.toLocaleString()}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={LOGISTICS_HELP.shipments} />
            <KpiCard label="Delivered" value={`${kpis.delivered}`}
              sub={kpis.shipments_shown ? `${Math.round(kpis.delivered / kpis.shipments_shown * 100)}% of shipments` : undefined}
              direction={kpis.delivered ? 'up' : null} goodWhen="up"
              refs={refs.delivered} fetchRefs={pager('delivered')}
              help={LOGISTICS_HELP.delivered} />
            <KpiCard label="Total Logistics Cost" value={money(kpis.total_cost)}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={LOGISTICS_HELP.totalCost} />
            <KpiCard label="Avg Cost / kg"
              value={kpis.shipments_shown ? `PKR ${kpis.avg_cost_per_kg.toFixed(1)}` : '—'}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={LOGISTICS_HELP.costPerKg} />
            <KpiCard label="Countries" value={`${kpis.countries}`}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={LOGISTICS_HELP.countries} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard title="Shipment Status" className="lg:col-span-2">
              {data.statusSplit.length > 0 ? (
                <Donut labels={data.statusSplit.map((s) => s.label)} values={data.statusSplit.map((s) => s.value)} height={300} />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No shipments match the current filter.</p>
              )}
            </ChartCard>

            <ChartCard title="Avg Cost / kg by Country">
              {data.costPerKgByCountry.length > 0 ? (
                <RankedBar data={data.costPerKgByCountry} category="label" value="value" height={300} unit="PKR / kg" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No cost/kg data in the current view.</p>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}
