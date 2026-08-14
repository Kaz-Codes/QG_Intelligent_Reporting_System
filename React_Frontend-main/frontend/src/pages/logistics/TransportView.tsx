import { useState } from 'react'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { LiveDataState } from '@/components/LiveDataState'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money } from '@/lib/format'
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { DataNotes } from '@/components/DataNotes'
import { Label } from '@/components/ui/label'
import { LOGISTICS_HELP } from '@/lib/metricHelp'
import { logisticsRefPager } from '@/lib/api/dashboardReferences'
import { useDebounced } from '@/lib/useDebounced'
import { useTransportDashboard } from '@/lib/api/useLogisticsDashboard'

const TABS = [
  { value: 'status', label: 'Status' },
  { value: 'transporter', label: 'By Transporter' },
  { value: 'movement', label: 'By Movement Type' },
] as const

/**
 * Backed by /dashboard/logistics/transport.
 *
 * Two things changed with real data. The Fleet Board — the scrollable movement
 * list and its detail panel — is gone: it read one row at a time, and this
 * endpoint returns aggregates only, so there are no movements to list. And the
 * "By Province" insight is replaced by "By Movement Type", because the
 * endpoint's by_province (and by_customer) come back empty; the province and
 * customer filters below hide themselves for the same reason.
 */
export function TransportView() {
  const [status, setStatus] = useState<string[]>([])
  const [movementType, setMovementType] = useState<string[]>([])
  const [paymentStatus, setPaymentStatus] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [province, setProvince] = useState<string[]>([])
  const [transporter, setTransporter] = useState<string[]>([])
  const [source, setSource] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)
  // Execution, or arrival at works — the same pair the Overview offers, so a
  // figure can be compared across the two screens.
  const [dateField, setDateField] = useState('etd')
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')

  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isFetching, isError, error } = useTransportDashboard({
    status, movement_type: movementType, payment_status: paymentStatus,
    customer, province, transporter, source,
    exec_from: dateFrom || undefined, exec_to: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
    date_from: period.from || undefined,
    date_to: period.to || undefined,
    date_field: dateField,
  })

  const refs = data?.references

  const pager = (key: string) => logisticsRefPager(key, {
    tab: 'transport',
    status, movement_type: movementType, source, payment_status: paymentStatus,
    transporter, exec_from: dateFrom, exec_to: dateTo,
    search: debouncedSearch.trim(),
    date_from: period.from, date_to: period.to, date_field: dateField,
  })

  const kpis = data?.kpis

  return (
    <div className="flex flex-col gap-6">
      {/* The window, and which date it means — the same control, wording and
          "jump to the latest month with data" as every other dashboard. */}
      <div className="rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
            label="Reporting period" />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="transport-date-field" className="text-xs">Filter on</Label>
            <select
              id="transport-date-field"
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

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by customer, transporter, or destination…' }}>
        <DateRangeFilter label="Execution Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Movement Type" options={data?.movementTypes ?? []} value={movementType} onChange={setMovementType} />
        {(data?.customers.length ?? 0) > 0 && (
          <MultiSelectFilter label="Customer" options={data?.customers ?? []} value={customer} onChange={setCustomer} />
        )}
        {(data?.provinces.length ?? 0) > 0 && (
          <MultiSelectFilter label="Province" options={data?.provinces ?? []} value={province} onChange={setProvince} />
        )}
        <MultiSelectFilter label="Transporter" options={data?.transporters ?? []} value={transporter} onChange={setTransporter} />
        <MultiSelectFilter label="Operational Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
      </FilterBar>

      <Disclosure title="More filters — Payment Status, Source">
        <div className="flex flex-wrap gap-4 pb-4">
          <div className="w-56">
            <MultiSelectFilter label="Payment Status" options={data?.paymentStatuses ?? []} value={paymentStatus} onChange={setPaymentStatus} />
          </div>
          <div className="w-56">
            <MultiSelectFilter label="Source" options={data?.sources ?? []} value={source} onChange={setSource} />
          </div>
        </div>
      </Disclosure>

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && kpis && refs && (
        <>
          {data.dataNotes.length > 0 && <DataNotes notes={data.dataNotes} />}

          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            <KpiCard label="Trucking Jobs" value={kpis.jobs_shown.toLocaleString()}
              refs={refs.jobs} fetchRefs={pager('jobs')}
              help={LOGISTICS_HELP.jobs} />
            <KpiCard label="Delivered" value={`${kpis.delivered}`}
              direction={kpis.delivered ? 'up' : null} goodWhen="up"
              refs={refs.delivered} fetchRefs={pager('delivered')}
              help={LOGISTICS_HELP.jobsDelivered} />
            <KpiCard label="In Progress" value={`${kpis.in_progress}`}
              refs={refs.in_progress} fetchRefs={pager('in_progress')}
              help={LOGISTICS_HELP.jobsDelivered} />
            <KpiCard label="Total Freight Cost" value={money(kpis.total_freight)}
              refs={refs.jobs} fetchRefs={pager('jobs')}
              help={LOGISTICS_HELP.freight} />
            <KpiCard label="Total Savings" value={kpis.total_savings ? money(kpis.total_savings) : '—'}
              refs={refs.jobs} fetchRefs={pager('jobs')}
              help={LOGISTICS_HELP.savings} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <InsightsCard title="Insights" tabs={TABS} active={tab} onChange={setTab} className="lg:col-span-2">
              {kpis.jobs_shown === 0 && <p className="py-12 text-center text-sm text-muted">No movements match the current filter.</p>}
              {kpis.jobs_shown > 0 && tab === 'status' && (
                <Donut labels={data.statusSplit.map((s) => s.label)} values={data.statusSplit.map((s) => s.value)} height={300} />
              )}
              {kpis.jobs_shown > 0 && tab === 'transporter' && (
                <RankedBar data={data.byTransporter} category="label" value="value" height={300} unit="Movements" />
              )}
              {kpis.jobs_shown > 0 && tab === 'movement' && (
                <CategoryBar data={data.byMovementType} category="label" value="value" height={300} unit="Movements" />
              )}
            </InsightsCard>

            <ChartCard title="By Payment Status">
              {data.byPaymentStatus.length > 0 ? (
                <Donut
                  labels={data.byPaymentStatus.map((s) => s.label)}
                  values={data.byPaymentStatus.map((s) => s.value)}
                  height={300}
                />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No payment data in the current view.</p>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}
