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
 * THE TAB IS "SHIPMENTS", NOT "EXPORT SHIPMENTS". Local orders live in this
 * table too, and the Orders tile below shows the split.
 *
 * It is a TILE rather than a filter, because filtering by it would not work:
 * local orders carry no date at all — no ETD, no arrival, no gate-out — so
 * every windowed view of this screen contains only exports. A Local/Export
 * filter would have appeared to work while always returning nothing for local,
 * which is worse than not offering it.
 *
 * The tile is windowed like everything else here, and reports the UNDATED
 * orders beside it. That is what stops "0 local" reading as "no local
 * business" when it actually means "local orders carry no date": the orders
 * are there, in a list you can open, just in no period.
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

  const { data, isLoading, isError, error } = useShipmentsDashboard({
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

      <LiveDataState isLoading={isLoading} isError={isError} error={error} skeleton="dashboard" />

      {data && kpis && refs && (
        <>
          {/* Where these figures rest on a partly-filled column, said here
              rather than left to be discovered. */}
          {data.dataNotes.length > 0 && <DataNotes notes={data.dataNotes} />}

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-7">
            <KpiCard label="Orders"
              value={data.orderTypeCounts.total.toLocaleString()}
              sub={`${data.orderTypeCounts.export.toLocaleString()} export · ${data.orderTypeCounts.local.toLocaleString()} local · ${data.orderTypeCounts.not_stated.toLocaleString()} not stated`}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={withBasis(LOGISTICS_HELP.orderTypes,
                data.orderTypeCounts.undated.total
                  ? `${data.orderTypeCounts.undated.total.toLocaleString()} orders carry no ${data.dateField.toUpperCase()} at all and fall in no period — ${data.orderTypeCounts.undated.local.toLocaleString()} of them local. Open the Undated tile to see them.`
                  : undefined)} />
            {/* The tile that stops "0 local" being read as "no local business". */}
            {data.orderTypeCounts.undated.total > 0 && (
              <KpiCard label="Undated Orders"
                value={data.orderTypeCounts.undated.total.toLocaleString()}
                sub={`${data.orderTypeCounts.undated.export.toLocaleString()} export · ${data.orderTypeCounts.undated.local.toLocaleString()} local · ${data.orderTypeCounts.undated.not_stated.toLocaleString()} not stated`}
                refs={refs.undated} fetchRefs={pager('undated')}
                help={LOGISTICS_HELP.undatedOrders} />
            )}
            <KpiCard label="Shipments" value={kpis.shipments_shown.toLocaleString()}
              refs={refs.orders} fetchRefs={pager('orders')}
              help={LOGISTICS_HELP.shipments} />
            <KpiCard label="Delivered" value={`${kpis.delivered}`}
              sub={kpis.shipments_shown ? `${Math.round(kpis.delivered / kpis.shipments_shown * 100)}% of shipments` : undefined}
              direction={kpis.delivered ? 'up' : null} goodWhen="up"
              refs={refs.delivered} fetchRefs={pager('delivered')}
              help={LOGISTICS_HELP.delivered} />
            <KpiCard label="Not Yet Linked" value={`${kpis.not_yet_linked}`}
              sub="tracked ahead of the export record"
              refs={refs.not_linked} fetchRefs={pager('not_linked')}
              help={LOGISTICS_HELP.notLinked} />
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
