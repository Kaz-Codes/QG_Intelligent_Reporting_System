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
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')

  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isError, error } = useTransportDashboard({
    status, movement_type: movementType, payment_status: paymentStatus,
    customer, province, transporter, source,
    exec_from: dateFrom || undefined, exec_to: dateTo || undefined,
    search: debouncedSearch.trim() || undefined,
  })

  const kpis = data?.kpis

  return (
    <div className="flex flex-col gap-6">
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

      <LiveDataState isLoading={isLoading} isError={isError} error={error} />

      {data && kpis && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
            <KpiCard label="Movements Shown" value={kpis.jobs_shown.toLocaleString()} />
            <KpiCard label="Delivered" value={`${kpis.delivered}`} direction={kpis.delivered ? 'up' : null} goodWhen="up" />
            <KpiCard label="In Progress" value={`${kpis.in_progress}`} />
            <KpiCard label="Total Freight Cost" value={money(kpis.total_freight)} />
            <KpiCard label="Total Savings" value={kpis.total_savings ? money(kpis.total_savings) : '—'} />
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
