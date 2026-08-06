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
import { useDebounced } from '@/lib/useDebounced'
import { useShipmentsDashboard } from '@/lib/api/useLogisticsDashboard'

/**
 * Backed by /dashboard/logistics/shipments. Every filter is a server-side
 * param, and the KPIs and charts are the endpoint's own figures.
 *
 * The Insights tab switcher is gone: it offered Status / By Country / By Port,
 * but the endpoint only computes a status split and cost-per-kg by country —
 * there's no shipment count by country or by port to switch to. One chart
 * doesn't need a tab bar, so it's a plain card until those figures exist.
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

  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isError, error } = useShipmentsDashboard({
    status, stage, shipping_line: shippingLine, country, customer,
    etd_from: dateFrom || undefined, etd_to: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
  })

  const kpis = data?.kpis

  return (
    <div className="flex flex-col gap-6">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by export no, customer, or country…' }}>
        <DateRangeFilter label="ETD" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Customer" options={data?.customers ?? []} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Shipment Stage" options={data?.stages ?? []} value={stage} onChange={setStage} />
        <MultiSelectFilter label="Shipment Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Shipping Line" options={data?.shippingLines ?? []} value={shippingLine} onChange={setShippingLine} />
        <MultiSelectFilter label="Country" options={data?.countries ?? []} value={country} onChange={setCountry} />
      </FilterBar>

      <LiveDataState isLoading={isLoading} isError={isError} error={error} />

      {data && kpis && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Shipments Shown" value={kpis.shipments_shown.toLocaleString()} />
            <KpiCard label="Delivered" value={`${kpis.delivered}`} direction={kpis.delivered ? 'up' : null} goodWhen="up" />
            <KpiCard label="Not Yet Linked" value={`${kpis.not_yet_linked}`} sub="tracked ahead of the export record" />
            <KpiCard label="Total Logistics Cost" value={money(kpis.total_cost)} />
            <KpiCard label="Avg Cost / kg" value={kpis.shipments_shown ? `PKR ${kpis.avg_cost_per_kg.toFixed(1)}` : '—'} />
            <KpiCard label="Countries" value={`${kpis.countries}`} />
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
