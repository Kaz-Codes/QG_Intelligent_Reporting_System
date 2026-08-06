import { ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { SingleSelectFilter } from '@/components/SingleSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { KpiCard } from '@/components/KpiCard'
import { HeroStat } from '@/components/HeroStat'
import { ChartCard } from '@/components/ChartCard'
import { Card, CardContent } from '@/components/ui/card'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money } from '@/lib/format'
import { useState } from 'react'
import { useImportsDashboard } from '@/lib/api/useImportsDashboard'
import { ApiError } from '@/lib/api/auth'
import type { ValueRow } from '@/lib/api/importsDashboard'

// Backed by the real database (app/dashboard/imports). The backend's filters
// only take one value each (plain query params, not arrays), so its filters
// are single-select. Like the other live dashboards, this page is KPIs and
// charts only.
function toMillions(rows: ValueRow[]): ValueRow[] {
  return rows.map((r) => ({ ...r, value: Number((r.value / 1_000_000).toFixed(2)) }))
}

export function Imports() {
  const [works, setWorks] = useState('')
  const [supplier, setSupplier] = useState('')
  const [country, setCountry] = useState('')
  const [itemCategory, setItemCategory] = useState('')
  const [status, setStatus] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const { data, isLoading, isError, error } = useImportsDashboard({
    work: works || undefined,
    supplier: supplier || undefined,
    country: country || undefined,
    item_category: itemCategory || undefined,
    status: status || undefined,
    from_date: dateFrom || undefined,
    to_date: dateTo || undefined,
  })

  const trend =
    data?.consignments.monthly_value_trend.map((p) => ({ month: p.month, value: Number((p.value / 1_000_000).toFixed(2)) })) ?? []

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Imports" subtitle="Import shipments, values, and customs clearance" module="imports" />

      <FilterBar>
        <DateRangeFilter label="ETA at Works" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <SingleSelectFilter label="Works" options={data?.works ?? []} value={works} onChange={setWorks} />
        <SingleSelectFilter label="Supplier" options={data?.suppliers ?? []} value={supplier} onChange={setSupplier} />
        <SingleSelectFilter label="Country" options={data?.countries ?? []} value={country} onChange={setCountry} />
        <SingleSelectFilter label="Item Category" options={data?.item_categories ?? []} value={itemCategory} onChange={setItemCategory} />
        <SingleSelectFilter label="Status" options={data?.status ?? []} value={status} onChange={setStatus} />
      </FilterBar>

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

      {data && (
        <>
          <HeroStat
            label="Total Value"
            value={money(data.consignments.kpis.total_value_pkr)}
            trendData={trend}
            trendX="month"
            trendY="value"
            caption="PKR millions per month, current filter"
            trendUnit="PKR (millions)"
          />

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <KpiCard label="Consignments" value={data.consignments.kpis.consignments_shown.toLocaleString()} />
            <KpiCard label="Open" value={`${data.consignments.kpis.open}`} sub="not yet arrived at works" />
            <KpiCard
              label="Under Clearance"
              value={`${data.consignments.kpis.under_clearance}`}
              direction={data.consignments.kpis.under_clearance ? 'up' : null}
              goodWhen="down"
            />
            <KpiCard label="Suppliers" value={`${data.consignments.kpis.suppliers}`} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <ChartCard title="Value by Country (PKR millions)" className="lg:col-span-2">
              {data.consignments.value_by_country.length > 0 ? (
                <RankedBar data={toMillions(data.consignments.value_by_country)} category="label" value="value" height={280} unit="PKR (millions)" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No country data in the current view.</p>
              )}
            </ChartCard>

            <ChartCard title="Status Split">
              {data.consignments.status_split.length > 0 ? (
                <Donut
                  labels={data.consignments.status_split.map((s) => s.label)}
                  values={data.consignments.status_split.map((s) => s.value)}
                  height={260}
                />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No status breakdown yet.</p>
              )}
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ChartCard title="Value by Supplier (PKR millions)">
              {data.consignments.value_by_supplier.length > 0 ? (
                <RankedBar data={toMillions(data.consignments.value_by_supplier)} category="label" value="value" height={300} unit="PKR (millions)" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No supplier data in the current view.</p>
              )}
            </ChartCard>

            <ChartCard title="Value by Branch (PKR millions)">
              {data.consignments.value_by_branch.length > 0 ? (
                <RankedBar data={toMillions(data.consignments.value_by_branch)} category="label" value="value" height={300} unit="PKR (millions)" />
              ) : (
                <p className="py-12 text-center text-sm text-muted">No branch data in the current view.</p>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}
