import { useMemo, useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { LiveDataState } from '@/components/LiveDataState'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { Card, CardContent } from '@/components/ui/card'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { RankedBar } from '@/components/charts/RankedBar'
import { Donut } from '@/components/charts/Donut'
import { MetricInfo } from '@/components/MetricInfo'
import { useTheme } from '@/theme/ThemeContext'
import { money } from '@/lib/format'
import { INVENTORY_HELP, withBasis } from '@/lib/metricHelp'
import { useDebounced } from '@/lib/useDebounced'
import { useInventoryDashboard } from '@/lib/api/useInventoryDashboard'

// "At-Risk Rate" and "Top Items" are gone. At-risk said an item was in trouble
// without saying whether anyone wants it — Movement answers that from real
// issuance. Top Items ranked by stock QUANTITY, adding kilograms to pieces.
const INSIGHT_TABS = [
  { value: 'movement', label: 'Movement by Branch' },
  { value: 'stockdays', label: 'Stock Days by Branch' },
  { value: 'branch', label: 'Items by Branch' },
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
  const [movement, setMovement] = useState<string[]>([])
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
    status, reorder_status: reorderStatus, movement, category, branch, item,
    search: debouncedSearch.trim() || undefined,
  })

  // Stock is a point-in-time snapshot — the table has no restock date at all,
  // so unlike Purchases there is no date filter to offer here.
  const kpis = data?.kpis

  const mov = data?.movementKpis
  // One sentence naming the exact dates the 12m/3m windows cover, reused by
  // every tooltip that depends on them — so "last 12 months" is never assumed
  // to end today when the issuance data stops earlier.
  const windowNote = data
    ? `Windows end at the latest issuance in the data (${data.issuanceWindows.latest_issuance}): 12 months from ${data.issuanceWindows.from_12m}, 3 months from ${data.issuanceWindows.from_3m}.`
    : undefined

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
        <MultiSelectFilter label="Movement" options={data?.movementClasses ?? []} value={movement} onChange={setMovement} />
      </FilterBar>

      <LiveDataState isLoading={isLoading} isError={isError} error={error} skeleton="dashboard" />

      {data && kpis && mov && (
        <>
          {/* Spotlight: stock days, the single number that says how long the
              money on the shelf lasts. Inventory is a snapshot, not a series,
              so there is no trend hero here. */}
          <Card className="overflow-hidden">
            <CardContent className="grid grid-cols-1 gap-6 p-6 lg:grid-cols-[1fr_auto]">
              <div className="flex flex-col justify-center">
                <p className="flex items-center gap-1.5 text-sm font-medium text-muted">
                  Stock Days
                  <MetricInfo help={withBasis(INVENTORY_HELP.stockDays, windowNote)} label="Stock Days" />
                </p>
                <p className="font-display mt-1 text-5xl font-extrabold tracking-tight text-navy">
                  {data.stockDays.total_days_of_stock != null
                    ? `${data.stockDays.total_days_of_stock}`
                    : '—'}
                  <span className="ml-2 text-2xl font-semibold text-muted">days</span>
                </p>
                <p className="mt-1 text-xs text-muted">
                  how long stock on hand lasts at the last 12 months' usage rate
                </p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <span className="rounded-full px-2.5 py-1 text-xs font-semibold" style={{ backgroundColor: colors.riskBg, color: colors.risk }}>
                    {kpis.out_of_stock.toLocaleString()} out of stock
                  </span>
                  <span className="rounded-full px-2.5 py-1 text-xs font-semibold" style={{ backgroundColor: colors.watchBg, color: colors.watch }}>
                    {kpis.below_reorder.toLocaleString()} below reorder
                  </span>
                </div>
              </div>
              <div className="w-full lg:w-56">
                {kpis.items_total > 0 && (
                  <Donut
                    labels={data.movementSplit.map((s) => s.movement)}
                    values={data.movementSplit.map((s) => s.items)}
                    // Item counts, not value: the donut answers "how much of the
                    // catalogue is dead", and the value split sits beside it.
                    height={190}
                    compact
                  />
                )}
                <p className="mt-1 text-center text-xs text-muted">items by movement</p>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Stock Value" value={money(kpis.total_stock_value)}
              help={INVENTORY_HELP.stockValue} />
            <KpiCard label="Available Value" value={money(kpis.available_value)}
              help={INVENTORY_HELP.availableValue} />
            <KpiCard label="Issued (12m)" value={money(mov.issued_value_12m)}
              help={withBasis(INVENTORY_HELP.issued12m, windowNote)} />
            <KpiCard label="Issued (3m)" value={money(mov.issued_value_3m)}
              sub="included in the 12m figure"
              help={withBasis(INVENTORY_HELP.issued3m, windowNote)} />
            <KpiCard label="Dead Stock" value={money(mov.dead_value)}
              sub={`${mov.dead_items.toLocaleString()} lines · ${mov.dead_value_pct ?? 0}% of value`}
              direction={mov.dead_items ? 'up' : null} goodWhen="down"
              help={withBasis(INVENTORY_HELP.deadStock, windowNote)} />
            <KpiCard label="Items in Stock" value={kpis.items_shown.toLocaleString()}
              sub={`of ${kpis.items_total.toLocaleString()} items`}
              help={INVENTORY_HELP.outOfStock} />
          </div>

          {/* Dead stock is half the LINES but a seventh of the VALUE — stating
              both stops the count being read as the whole story. */}
          <ChartCard title="Movement — lines against value">
            <p className="-mt-2 mb-3 text-xs text-muted">
              Fast = issued in the last 3 months · Slow = issued within 12 months but
              not the last 3 · Dead = no issuance in 12 months. Windows end at the
              latest issuance in the data ({data.issuanceWindows.latest_issuance}).
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {data.movementSplit.map((m) => (
                <div key={m.movement} className="rounded-lg border border-line p-3">
                  <p className="text-sm font-semibold text-ink">{m.movement}</p>
                  <p className="font-display mt-1 text-2xl font-bold text-navy">{money(m.value)}</p>
                  <p className="text-xs text-muted">
                    {m.value_pct ?? 0}% of value · {m.items.toLocaleString()} items ({m.items_pct ?? 0}%)
                  </p>
                </div>
              ))}
            </div>
          </ChartCard>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
              {kpis.items_total === 0 && <p className="py-12 text-center text-sm text-muted">No items match the current filter.</p>}
              {kpis.items_total > 0 && insightTab === 'movement' && (
                <>
                  <RankedBar data={data.movementByBranch} category="branch" value="count"
                    valueKey="value" countNoun="dead item" height={280} invertColor unit="Dead items" />
                  <p className="mt-2 text-xs text-muted">
                    Dead items per store. Hover a bar for what that stock is worth.
                  </p>
                </>
              )}
              {kpis.items_total > 0 && insightTab === 'stockdays' && (
                <>
                  <RankedBar data={data.stockDays.by_branch} category="branch" value="days_of_stock" height={280} unit="Days of stock" />
                  <p className="mt-2 text-xs text-muted">
                    Stock value divided by the daily usage rate over the last 12 months.
                    A store with no issuance has no runway and is not shown.
                  </p>
                </>
              )}
              {kpis.items_total > 0 && insightTab === 'branch' && (
                <CategoryBar data={data.itemsByBranch} category="branch" value="count"
                  valueKey="value" countNoun="item" height={300} unit="Items" />
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
