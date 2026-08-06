import { useMemo, useState } from 'react'
import { ShieldAlert } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { Card, CardContent } from '@/components/ui/card'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { RankedBar } from '@/components/charts/RankedBar'
import { Donut } from '@/components/charts/Donut'
import { useTheme } from '@/theme/ThemeContext'
import { useDebounced } from '@/lib/useDebounced'
import { useInventoryDashboard } from '@/lib/api/useInventoryDashboard'
import { ApiError } from '@/lib/api/auth'

const INSIGHT_TABS = [
  { value: 'branch', label: 'Items by Branch' },
  { value: 'risk', label: 'At-Risk Rate' },
  { value: 'top', label: 'Top Items' },
] as const

/**
 * Item names in this data are packed records, not names: the stock table
 * stores "Digital Weighing Scale | 100kg | No. | 10010-60", and the endpoint
 * appends the branch on top of that, so a chart tick arrives ~90 characters
 * long and reads as noise. Everything after the first "|" is spec, unit and
 * item code — none of which identifies the bar — so charts show just the
 * leading name. The table below still shows the field in full.
 */
function itemChartLabel(label: string): string {
  const [name] = label.split('|')
  return name.trim() || label
}

export function Inventory() {
  const { colors } = useTheme()
  const [status, setStatus] = useState<string[]>([])
  const [reorderStatus, setReorderStatus] = useState<string[]>([])
  const [category, setCategory] = useState<string[]>([])
  const [branch, setBranch] = useState<string[]>([])
  const [item, setItem] = useState<string[]>([])
  const [search, setSearch] = useState('')
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('branch')

  // Search narrows the KPIs and charts on this page (not just the table, the
  // way it does on Purchases), so it has to reach the server for those figures
  // to match. Debounced so typing sends one request at the end rather than one
  // per keystroke.
  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isError, error } = useInventoryDashboard({
    status, reorder_status: reorderStatus, category, branch, item,
    search: debouncedSearch.trim() || undefined,
  })

  // Stock is a point-in-time snapshot — the table has no restock date at all,
  // so unlike Purchases there is no date filter to offer here.
  const kpis = data?.kpis

  const topItems = useMemo(
    () => (data?.topItems ?? []).map((r) => ({ ...r, item: itemChartLabel(r.item) })),
    [data],
  )
  // The endpoint now excludes items already at zero from this ranking (they're
  // reported by the "out of stock" count above instead), so every entry here
  // is a real, non-zero runway — nothing left to filter client-side.
  const runningOutSoonest = useMemo(
    () => (data?.lowestDaysOfStock ?? []).map((r) => ({ ...r, item: itemChartLabel(r.item) })),
    [data],
  )

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Inventory" subtitle="Current stock levels and usage-based reorder risk" module="inventory" />

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by item, item code, branch, category, or specs…' }}>
        <MultiSelectFilter label="Branch" options={data?.branches ?? []} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Category" options={data?.itemCategories ?? []} value={category} onChange={setCategory} />
        <MultiSelectFilter label="Item" options={data?.items ?? []} value={item} onChange={setItem} />
        <MultiSelectFilter label="Stock Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Reorder Status" options={data?.reorderStatuses ?? []} value={reorderStatus} onChange={setReorderStatus} />
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

      {data && kpis && (
        <>
          {/* Spotlight: at-risk headline + stock health composition, in place of a
              trend hero — inventory is a snapshot, not a time series. */}
          <Card className="overflow-hidden">
            <CardContent className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_auto]">
              <div className="flex flex-col justify-center">
                <p className="text-sm font-medium text-muted">% At Risk</p>
                <p className="font-display mt-1 text-5xl font-extrabold tracking-tight text-navy">
                  {kpis.items_shown ? `${kpis.at_risk_pct}%` : '—'}
                </p>
                <p className="mt-1 text-xs text-muted">out of stock + below reorder, current filter</p>
                <div className="mt-4 flex gap-3">
                  <span className="rounded-full px-2.5 py-1 text-xs font-semibold" style={{ backgroundColor: colors.riskBg, color: colors.risk }}>
                    {kpis.out_of_stock} out of stock
                  </span>
                  <span className="rounded-full px-2.5 py-1 text-xs font-semibold" style={{ backgroundColor: colors.watchBg, color: colors.watch }}>
                    {kpis.below_reorder} below reorder
                  </span>
                </div>
              </div>
              <div className="w-full lg:w-56">
                {kpis.items_shown > 0 && (
                  <Donut labels={data.stockHealth.map((s) => s.label)} values={data.stockHealth.map((s) => s.value)} height={190} compact />
                )}
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <KpiCard label="Available Units" value={kpis.available_units.toLocaleString()} />
            <KpiCard label="Total Stock Qty" value={kpis.total_stock_qty.toLocaleString()} />
            <KpiCard label="On Hold" value={kpis.on_hold.toLocaleString()} sub="reserved, not available" />
            <KpiCard label="Items Shown" value={kpis.items_shown.toLocaleString()} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
              {kpis.items_shown === 0 && <p className="py-12 text-center text-sm text-muted">No items match the current filter.</p>}
              {kpis.items_shown > 0 && insightTab === 'branch' && (
                <CategoryBar data={data.itemsByBranch} category="branch" value="items" height={300} unit="Items" />
              )}
              {kpis.items_shown > 0 && insightTab === 'risk' && (
                <RankedBar data={data.atRiskByBranch} category="branch" value="at_risk" height={300} invertColor unit="% at risk" />
              )}
              {kpis.items_shown > 0 && insightTab === 'top' && (
                <RankedBar data={topItems} category="item" value="stock_qty" height={300} unit="Stock qty" />
              )}
            </InsightsCard>

            <ChartCard title="Running Out Soonest">
              {runningOutSoonest.length > 0 ? (
                <>
                  <p className="-mt-2 mb-3 text-xs text-muted">
                    Days of stock left at recent usage. Items already at zero are counted in “out of stock” above.
                  </p>
                  <RankedBar data={runningOutSoonest} category="item" value="days_of_stock" height={272} unit="Days left" />
                </>
              ) : (
                <p className="py-12 text-center text-sm text-muted">
                  Nothing with a runway to show — either every item in view is already out of stock (see the count
                  above) or there's no recent issuance history to estimate one from.
                </p>
              )}
            </ChartCard>
          </div>

        </>
      )}
    </div>
  )
}
