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
import { ReferenceList } from '@/components/ReferenceList'
import { useTheme } from '@/theme/ThemeContext'
import { money } from '@/lib/format'
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { inventoryRefPager } from '@/lib/api/dashboardReferences'
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
/** The chart's own class names against the reference keys the API serves them
 *  under — declared once so a renamed class cannot silently break a drill-down. */
const MOVEMENT_KEYS: Record<string, string> = {
  'Fast moving': 'fast',
  'Slow moving': 'slow',
  Dead: 'dead',
}


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
  // Stock itself is a snapshot with no date at all, but what was ISSUED happens
  // in a period — so the window here covers that one figure. Empty = this
  // month, resolved by the backend.
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)

  // Search narrows the KPIs and charts on this page (not just the table, the
  // way it does on Purchases), so it has to reach the server for those figures
  // to match. Debounced so typing sends one request at the end rather than one
  // per keystroke.
  const debouncedSearch = useDebounced(search)

  const { data, isLoading, isFetching, isError, error } = useInventoryDashboard({
    status, reorder_status: reorderStatus, movement, category, branch, item,
    search: debouncedSearch.trim() || undefined,
    date_from: period.from || undefined,
    date_to: period.to || undefined,
  })

  // Bound to the same filters the screen was rendered with, so page 2 of a
  // reference list describes the same set as page 1.
  const pager = (key: string) => inventoryRefPager(key, {
    status, reorder_status: reorderStatus, movement, category, branch, item,
    search: debouncedSearch.trim(),
    date_from: period.from, date_to: period.to,
  })

  const kpis = data?.kpis

  const mov = data?.movementKpis
  // The items behind each tile, so a count is never a dead end.
  const refs = data?.references
  const issuance = data?.issuance
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

      {/* Stock is today's position, so the window applies only to what was
          ISSUED. Said plainly on the control rather than left to be inferred
          from a tile that moves while the ones beside it do not. */}
      <div className="rounded-xl border border-line bg-surface p-4">
        <PeriodFilter period={period} onChange={setPeriod} range={data?.coverage}
          label="Issuance period (stock figures are today's position)" />
        {data && (
          <div className="mt-3">
            <PeriodSummary period={data.period} coverage={data.coverage} onJumpToLatest={setPeriod} />
          </div>
        )}
      </div>

      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by item, item code, branch, category, or specs…' }}>
        <MultiSelectFilter label="Branch" options={data?.branches ?? []} value={branch} onChange={setBranch} />
        <MultiSelectFilter label="Category" options={data?.itemCategories ?? []} value={category} onChange={setCategory} />
        <MultiSelectFilter label="Item" options={data?.items ?? []} value={item} onChange={setItem} />
        <MultiSelectFilter label="Stock Status" options={data?.statuses ?? []} value={status} onChange={setStatus} />
        <MultiSelectFilter label="Reorder Status" options={data?.reorderStatuses ?? []} value={reorderStatus} onChange={setReorderStatus} />
        <MultiSelectFilter label="Movement" options={data?.movementClasses ?? []} value={movement} onChange={setMovement} />
      </FilterBar>

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && kpis && mov && refs && issuance && (
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

          {/* auto-fit rather than a fixed 3 columns — on a wide screen three
              fixed columns leave a stretch of empty space instead of the row
              filling it, the same problem the other dashboards' KPI rows had. */}
          <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
            <KpiCard label="Stock Value" value={money(kpis.total_stock_value)}
              sub={`${kpis.items_shown.toLocaleString()} of ${kpis.items_total.toLocaleString()} items`}
              refs={refs.items}
              fetchRefs={pager('items')}
              help={INVENTORY_HELP.stockValue} />
            <KpiCard label="Available Value" value={money(kpis.available_value)}
              sub={`${kpis.out_of_stock.toLocaleString()} out of stock · ${kpis.below_reorder.toLocaleString()} below reorder`}
              refs={refs.items}
              fetchRefs={pager('items')}
              help={INVENTORY_HELP.availableValue} />
            {/* ONE issuance tile with a window you choose, replacing the fixed
                12m and 3m pair — those answered one question at two arbitrary
                lengths, neither of which anybody picked, and neither of which
                could say what went out THIS month. Same layout as Stock Value:
                money on top, the item count under it.

                The 12-month figures have not gone away; the movement split and
                the days-of-stock runway are still built on them. They are just
                no longer tiles, because the split says the same thing with a
                reason attached.

                Dead Stock and Items in Stock are gone for the same reason:
                dead stock is a block in the movement card below, with its own
                drill-down, and the item count is already on Stock Value. */}
            <KpiCard label={`Issued · ${data.period.label}`} value={money(issuance.value)}
              sub={`${issuance.items.toLocaleString()} items · ${issuance.lines.toLocaleString()} lines`}
              refs={refs.issuance}
              fetchRefs={pager('issuance')}
              help={withBasis(INVENTORY_HELP.issued,
                `${issuance.lines.toLocaleString()} issuance lines over ${issuance.items.toLocaleString()} distinct item codes.`)} />
          </div>

          {/* Dead stock is half the LINES but a seventh of the VALUE — stating
              both stops the count being read as the whole story. */}
          <ChartCard title="Movement — items against value">
            <p className="-mt-2 mb-3 text-xs text-muted">
              Fast = issued in the last 3 months · Slow = issued within 12 months but
              not the last 3 · Dead = no issuance in 12 months. Windows end at the
              latest issuance in the data ({data.issuanceWindows.latest_issuance}).
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {data.movementSplit.map((m) => (
                <div key={m.movement} className="rounded-lg border border-line p-3">
                  <div className="flex items-center gap-1">
                    <p className="text-sm font-semibold text-ink">{m.movement}</p>
                    {/* Which items — "2,387 dead" cannot be worked on, a list can. */}
                    <ReferenceList
                      label={`${m.movement} items`}
                      refs={refs.movement[m.movement]}
                      fetchPage={pager(MOVEMENT_KEYS[m.movement])}
                    />
                  </div>
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
