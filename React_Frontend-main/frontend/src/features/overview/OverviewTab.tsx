import { useState, type ReactNode } from 'react'
import { Sparkles, Ship, Wallet, Truck, Warehouse, Boxes, Timer, type LucideIcon } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { KpiCard } from '@/components/KpiCard'
import { ChartCard } from '@/components/ChartCard'
import { LiveDataState } from '@/components/LiveDataState'
import { RankedBar } from '@/components/charts/RankedBar'
import { PeriodFilter, PeriodSummary, EMPTY_PERIOD, type Period, type ResolvedPeriod, type Coverage } from '@/components/PeriodFilter'
import { DataNotes, type DataNote } from '@/components/DataNotes'
import { Label } from '@/components/ui/label'
import type { DateFieldOption } from '@/lib/api/overviewDashboard'
import { useAuth } from '@/features/auth/AuthContext'
import { money, compactMoney } from '@/lib/format'
import { OVERVIEW_HELP, withBasis } from '@/lib/metricHelp'
import { useOverviewDashboard } from '@/lib/api/useOverviewDashboard'
import { overviewRefPager } from '@/lib/api/dashboardReferences'

/**
 * The cross-module overview, on live data.
 *
 * Previously this whole screen was mock — hardcoded KPIs, a fabricated weekly
 * trend, invented alerts and supplier scores. Every number is now a real
 * aggregate from `/dashboard/overview`.
 *
 * Counting units match the module screens exactly: ORDERS for procurement,
 * CONSIGNMENTS for imports, ITEMS for stock. The MONEY behind imports is summed
 * over lines and dated by each line's own arrival, because the rows sharing a
 * payment reference do not all land in the same month — but a tile still counts
 * consignments, and its reference list says how many lines that was.
 *
 * Period vs lifetime is labelled per section rather than left to be inferred:
 * imports and procurement follow the window; logistics and stores are running
 * totals and snapshots, and say so.
 */

/**
 * The one sub-line every count-and-value tile uses.
 *
 * Related KPIs have to be formatted the same or they cannot be read against
 * each other, so this is the only place a count is rendered under a value.
 */
function countLine(count: number, noun: string, pct?: number | null): string {
  const base = `${count.toLocaleString()} ${noun}${count === 1 ? '' : 's'}`
  return pct != null ? `${base} · ${pct}% of value` : base
}


/**
 * All imports figures, or shafts only.
 *
 * A tab rather than two extra tiles: as tiles, "9 shafts in process" sat beside
 * a 30 that counted everything, and the two could not be compared. As a filter
 * it narrows the whole section — tiles, stage chart and every reference list —
 * so each figure keeps its meaning over a smaller population.
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
            active === tab.value
              ? 'bg-brand-soft text-brand'
              : 'text-muted hover:text-ink'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}


function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}


/**
 * A section's own heading, window and data notes.
 *
 * Each area of the business is filtered on its own date, and where two dates
 * are both meaningful (imports: landed vs needed; logistics: departed vs
 * arrived) the choice sits right next to the filter rather than in a global
 * control that would mean something different per section.
 *
 * The notes render underneath, so a figure resting on a partly-filled column
 * says so where it is read rather than in a footnote.
 */
function SectionHeader({
  title, icon: Icon, period, onPeriodChange, meta,
  fieldOptions, field, onFieldChange, snapshotLabel, children,
}: {
  title: string
  icon: LucideIcon
  period?: Period
  onPeriodChange?: (p: Period) => void
  meta?: { period: ResolvedPeriod | null; data_notes: DataNote[]; coverage?: Coverage }
  fieldOptions?: DateFieldOption[]
  field?: string
  onFieldChange?: (v: string) => void
  /** For a section with no date column at all. */
  snapshotLabel?: string
  /** Rendered between the filter and the notes — the Shafts tab, for one. */
  children?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Icon size={15} className="text-muted" /> {title}
          {snapshotLabel
            ? <span className="text-xs font-normal text-muted">· {snapshotLabel}</span>
            : meta?.period && <span className="text-xs font-normal text-muted">· {meta.period.label}</span>}
        </h2>

        {fieldOptions && onFieldChange && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${title}-date-field`} className="text-xs">Filter on</Label>
            <select
              id={`${title}-date-field`}
              value={field}
              onChange={(e) => onFieldChange(e.target.value)}
              className="h-8 rounded-lg border border-line bg-surface px-2 text-xs text-ink focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
            >
              {fieldOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {period && onPeriodChange && (
        <PeriodFilter
          period={period} onChange={onPeriodChange} label="Period"
          range={meta?.coverage
            ? { earliest: meta.coverage.earliest, latest: meta.coverage.latest }
            : undefined}
        />
      )}

      {children}

      {/* What the source actually holds against what the window caught, plus
          the jump to the latest month that has data — so an empty section reads
          as "the data stops in January", never as a confident zero. */}
      {meta?.period && meta?.coverage && (
        <PeriodSummary
          period={meta.period} coverage={meta.coverage}
          onJumpToLatest={onPeriodChange}
        />
      )}

      {meta?.data_notes?.length ? <DataNotes notes={meta.data_notes} /> : null}
    </div>
  )
}

export function OverviewTab() {
  const { user } = useAuth()
  // A window per section: a consignment's arrival, a PO's date and a truck's
  // run are different events, so one shared filter compared unlike things.
  const [importsPeriod, setImportsPeriod] = useState<Period>(EMPTY_PERIOD)
  const [importsField, setImportsField] = useState('eta_works')
  const [purchasesPeriod, setPurchasesPeriod] = useState<Period>(EMPTY_PERIOD)
  const [purchasesField, setPurchasesField] = useState('po_date')
  const [logisticsPeriod, setLogisticsPeriod] = useState<Period>(EMPTY_PERIOD)
  const [logisticsField, setLogisticsField] = useState('etd')
  // Stock is a snapshot, but what was ISSUED happens in a period, so Stores has
  // a window of its own covering that one figure.
  const [storesPeriod, setStoresPeriod] = useState<Period>(EMPTY_PERIOD)
  // The Shafts tab. Not two extra tiles: it narrows every imports figure at
  // once, so each tile keeps its meaning over the shaft subset instead of
  // sitting beside figures that count a different population.
  const [shaftsOnly, setShaftsOnly] = useState(false)

  const { data, isLoading, isFetching, isError, error } = useOverviewDashboard({
    imports_date_from: importsPeriod.from || undefined,
    imports_date_to: importsPeriod.to || undefined,
    imports_date_field: importsField,
    purchases_date_from: purchasesPeriod.from || undefined,
    purchases_date_to: purchasesPeriod.to || undefined,
    purchases_date_field: purchasesField,
    logistics_date_from: logisticsPeriod.from || undefined,
    logistics_date_to: logisticsPeriod.to || undefined,
    logistics_date_field: logisticsField,
    stores_date_from: storesPeriod.from || undefined,
    stores_date_to: storesPeriod.to || undefined,
    shafts_only: shaftsOnly,
  })

  // Every pager is bound to the SAME filters the section was rendered with, so
  // page 2 of a list describes the same set as page 1.
  const importsRefs = (key: string) => overviewRefPager(key, {
    date_from: importsPeriod.from, date_to: importsPeriod.to,
    date_field: importsField, shafts_only: shaftsOnly,
  })
  const procurementRefs = (key: string) => overviewRefPager(key, {
    date_from: purchasesPeriod.from, date_to: purchasesPeriod.to,
    date_field: purchasesField,
  })
  const logisticsRefs = (key: string, movement?: string) => overviewRefPager(key, {
    date_from: logisticsPeriod.from, date_to: logisticsPeriod.to,
    date_field: logisticsField, movement,
  })
  const storesRefs = (key: string) => overviewRefPager(key, {
    date_from: storesPeriod.from, date_to: storesPeriod.to,
  })

  const firstName = user?.username?.split(/[.\s_]/)[0] ?? ''

  return (
    <div className="flex flex-col gap-5">
      <Card className="p-6 lg:p-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <span className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-brand/25 bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">
              <Sparkles size={12} />
              Executive Overview
            </span>
            <h1 className="font-display text-3xl font-extrabold leading-tight tracking-tight text-navy lg:text-4xl">
              {greeting()}{firstName ? `, ${firstName}` : ''}
            </h1>
            <p className="mt-1 max-w-lg text-sm text-muted">
              Imports, procurement, logistics and stores. Each section sets its
              own period, because each depends on a different date — and each
              states where its data is incomplete.
            </p>
          </div>
        </div>


      </Card>

      <LiveDataState isLoading={isLoading} isFetching={isFetching} isError={isError} error={error} skeleton="dashboard" />

      {!isFetching && data && (
        <>
          {/* ---------------------------------------------------- imports */}
          <section className="flex flex-col gap-3">
            <SectionHeader
              title="Imports" icon={Ship}
              period={importsPeriod} onPeriodChange={setImportsPeriod}
              meta={data.imports}
              fieldOptions={data.date_field_options.imports}
              field={importsField} onFieldChange={setImportsField}
            >
              <ShaftsTab active={shaftsOnly} onChange={setShaftsOnly} />
            </SectionHeader>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
              {/* Value first, count underneath — the SAME layout on all five,
                  so the row can be read across. In Process used to show a bare
                  count, which said 30 consignments were moving without saying
                  whether that was Rs 4m or Rs 400m. */}
              <KpiCard label="Import Value" value={money(data.imports.period_value.value)}
                sub={`${data.imports.period_value.consignments.toLocaleString()} consignment${data.imports.period_value.consignments === 1 ? '' : 's'} · ${data.imports.period_value.lines.toLocaleString()} lines`}
                icon={Wallet}
                refs={data.imports.references.period_value}
                fetchRefs={importsRefs('imports.period_value')}
                help={withBasis(OVERVIEW_HELP.importValue,
                  data.imports.period_value.undated.consignments
                    ? `${data.imports.period_value.undated.consignments} consignments worth ${compactMoney(data.imports.period_value.undated.value)} have no date in this column, so they fall in no period at all.`
                    : undefined)} />
              <KpiCard label="In Process" value={money(data.imports.in_process.value)}
                sub={countLine(data.imports.in_process.count, 'consignment', data.imports.in_process.value_pct)}
                icon={Ship}
                refs={data.imports.references.in_process}
                fetchRefs={importsRefs('imports.in_process')}
                help={OVERVIEW_HELP.importsInProcess} />
              <KpiCard label="Arrived" value={money(data.imports.arrived.value)}
                sub={countLine(data.imports.arrived.count, 'consignment', data.imports.arrived.value_pct)}
                refs={data.imports.references.arrived}
                fetchRefs={importsRefs('imports.arrived')}
                help={OVERVIEW_HELP.importsArrived} />
              <KpiCard label="Cancelled" value={money(data.imports.cancelled.value)}
                sub={countLine(data.imports.cancelled.count, 'consignment', data.imports.cancelled.value_pct)}
                refs={data.imports.references.cancelled}
                fetchRefs={importsRefs('imports.cancelled')}
                help={OVERVIEW_HELP.importsCancelled} />
              <KpiCard label="Delayed" value={money(data.imports.delayed.value)}
                sub={countLine(data.imports.delayed.count, 'consignment')}
                direction={data.imports.delayed.count ? 'up' : null} goodWhen="down"
                refs={data.imports.references.delayed}
                fetchRefs={importsRefs('imports.delayed')}
                help={withBasis(OVERVIEW_HELP.importsDelayed,
                  `More than ${data.imports.delayed.grace_days} days past the required date. Measured on the ${data.imports.delayed.basis} consignments carrying both dates${data.imports.delayed.delay_pct != null ? ` — ${data.imports.delayed.delay_pct}% of them` : ''}.`)} />
            </div>

            {data.imports.in_process.by_stage.length > 0 && (
              <ChartCard title={shaftsOnly ? 'Shafts in process, by stage' : 'Imports in process, by stage'}>
                <RankedBar data={data.imports.in_process.by_stage} category="stage"
                  value="consignments" countNoun="consignment" height={220} unit="Consignments" />
              </ChartCard>
            )}
          </section>

          {/* ----------------------------------------------- procurement */}
          <section className="flex flex-col gap-3">
            <SectionHeader
              title="Purchases" icon={Wallet}
              period={purchasesPeriod} onPeriodChange={setPurchasesPeriod}
              meta={data.procurement}
              fieldOptions={data.date_field_options.purchases}
              field={purchasesField} onFieldChange={setPurchasesField}
            />
            {/* Categories is gone: it counted the bars in the chart directly
                below it, which is not a KPI. */}
            <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
              <KpiCard label="Procurement Value" value={money(data.procurement.period_value.value)}
                sub={countLine(data.procurement.period_value.orders, 'order')}
                icon={Wallet} refs={data.procurement.references.period_value}
                fetchRefs={procurementRefs('procurement.period_value')}
                help={OVERVIEW_HELP.procurementValue} />
              <KpiCard label="Delay Rate"
                value={data.procurement.delay.delay_pct != null ? `${data.procurement.delay.delay_pct}%` : '—'}
                direction={data.procurement.delay.late_orders ? 'up' : null} goodWhen="down"
                refs={data.procurement.references.delay}
                fetchRefs={procurementRefs('procurement.delay')}
                help={withBasis(OVERVIEW_HELP.procurementDelay,
                  `${data.procurement.delay.late_orders.toLocaleString()} late of ${data.procurement.delay.basis.toLocaleString()} orders with a required date.`)} />
              <KpiCard label="Average Cycle Time"
                value={data.procurement.cycle_time.store_to_purchase_days != null
                  ? `${data.procurement.cycle_time.store_to_purchase_days} days` : '—'}
                sub="store demand to purchase" icon={Timer}
                help={withBasis(OVERVIEW_HELP.cycleTime,
                  `Measured on ${data.procurement.cycle_time.store_to_purchase_basis.toLocaleString()} orders. Order-to-purchase is ${data.procurement.cycle_time.po_to_purchase_days ?? '—'} days.`)} />
            </div>

            {data.procurement.category_split.split.length > 0 && (
              <ChartCard title="Spend by category — top 4 and everything else">
                <RankedBar
                  data={data.procurement.category_split.split.map((c) => ({
                    ...c, label: c.category, count: Math.round(c.share_pct ?? 0),
                  }))}
                  category="label" value="count" valueKey="value"
                  height={220} unit="% of spend" />
                <p className="mt-2 text-xs text-muted">
                  Bars are each category's share of period spend; hover for the rupees.
                  "Other" gathers the remaining {(data.procurement.category_split.split.find((c) => c.category === 'Other')?.categories ?? 0)} categories.
                </p>
              </ChartCard>
            )}
          </section>

          {/* ------------------------------------------------- logistics */}
          <section className="flex flex-col gap-3">
            <SectionHeader
              title="Logistics" icon={Truck}
              period={logisticsPeriod} onPeriodChange={setLogisticsPeriod}
              meta={data.logistics}
              fieldOptions={data.date_field_options.logistics}
              field={logisticsField} onFieldChange={setLogisticsField}
            />
            <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
              <KpiCard label="Trucking Cost" value={money(data.logistics.trucking_cost.total)}
                sub="all jobs to date" icon={Truck}
                refs={data.logistics.references.trucking_cost}
                fetchRefs={logisticsRefs('logistics.trucking_cost')}
                help={OVERVIEW_HELP.truckingCost} />
              {data.logistics.trucking_cost.by_movement.slice(0, 2).map((m) => (
                <KpiCard key={m.movement_type} label={`${m.movement_type} Freight`}
                  value={money(m.actual_freight)}
                  sub={`${m.jobs} jobs · ${m.share_pct ?? 0}% of cost`}
                  refs={data.logistics.references.by_movement[m.movement_type]}
                  fetchRefs={logisticsRefs('logistics.trucking_cost', m.movement_type)}
                  help={OVERVIEW_HELP.truckingCost} />
              ))}
              <KpiCard label="Shipments Handled"
                value={data.logistics.shipments_handled.total.toLocaleString()}
                sub={`${data.logistics.shipments_handled.export_shipments} export · ${data.logistics.shipments_handled.import_shipments} import`}
                icon={Ship}
                refs={data.logistics.references.shipments_handled}
                fetchRefs={logisticsRefs('logistics.shipments_handled')}
                help={withBasis(OVERVIEW_HELP.shipmentsHandled,
                  `Only ${data.logistics.shipments_handled.coverage.export_datable.toLocaleString()} of ${data.logistics.shipments_handled.coverage.export_total.toLocaleString()} logistics orders carry this date, so the export count covers the dated ones only.`)} />

              {/* One figure from each of the section's three areas. The tiles
                  above are both about road movement, which made "logistics"
                  read as a synonym for trucking. */}
              <KpiCard label="Packed Tonnage"
                value={`${data.logistics.packed_tonnage.tonnes.toLocaleString()} t`}
                sub={countLine(data.logistics.packed_tonnage.packages, 'package')}
                icon={Boxes}
                help={withBasis(OVERVIEW_HELP.packedTonnage,
                  `Weighed on ${data.logistics.packed_tonnage.basis.toLocaleString()} of ${data.logistics.packed_tonnage.packages.toLocaleString()} packages; the rest record no weight and add nothing.`)} />
              <KpiCard label="Freight / kg"
                value={data.logistics.freight_per_kg.rate != null
                  ? `PKR ${data.logistics.freight_per_kg.rate.toFixed(2)}` : '—'}
                sub={`${Math.round(data.logistics.freight_per_kg.kilograms / 1000).toLocaleString()} t moved`}
                icon={Truck}
                help={withBasis(OVERVIEW_HELP.freightPerKg,
                  `Measured on the ${data.logistics.freight_per_kg.basis.toLocaleString()} jobs that record both a freight figure and a vehicle weight.`)} />
              {/* Export is windowed like everything else here. LOCAL IS NOT,
                  and its label says so on its face: not one local order carries
                  a business date, so a windowed local count is zero in every
                  period there has ever been. All-time is the only basis on
                  which it says anything, and two bases shown visibly beat two
                  bases shown silently. */}
              <KpiCard label="Export Orders"
                value={data.logistics.order_types.export.toLocaleString()}
                sub={data.logistics.order_types.total
                  ? `${Math.round(data.logistics.order_types.export / data.logistics.order_types.total * 100)}% of ${data.logistics.order_types.total.toLocaleString()} in period`
                  : 'none in this period'}
                icon={Ship}
                refs={data.logistics.references.export_orders}
                fetchRefs={logisticsRefs('logistics.export_orders')}
                help={OVERVIEW_HELP.exportOrders} />
              <KpiCard label="Local Orders (all time)"
                value={data.logistics.order_types.all_time.local.toLocaleString()}
                sub="not period-filtered"
                icon={Truck}
                refs={data.logistics.references.local_orders}
                fetchRefs={logisticsRefs('logistics.local_orders')}
                help={OVERVIEW_HELP.localOrders} />
              <KpiCard label="Transit Time"
                value={data.logistics.transit_time.days != null
                  ? `${data.logistics.transit_time.days} days` : '—'}
                sub="sailing to arrival" icon={Timer}
                help={withBasis(OVERVIEW_HELP.transitTime,
                  `Measured on the ${data.logistics.transit_time.basis.toLocaleString()} orders recording both an ETD and an arrival date.`)} />
            </div>
          </section>

          {/* ---------------------------------------------------- stores */}
          <section className="flex flex-col gap-3">
            {/* Stores has no date column at all — it is today's position — so
                it gets no period filter, and says so instead of offering one
                that would do nothing. */}
            <SectionHeader
              title="Stores" icon={Warehouse}
              period={storesPeriod} onPeriodChange={setStoresPeriod}
              meta={data.stores}
              snapshotLabel="stock is today's position; the period applies to issuance"
            />
            <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
              <KpiCard label="Stock Value" value={money(data.stores.stock_value.stock_value)}
                sub={`${data.stores.stock_value.items.toLocaleString()} items`}
                icon={Warehouse} refs={data.stores.references.stock_value}
                fetchRefs={storesRefs('stores.stock_value')}
                help={OVERVIEW_HELP.stockValue} />
              <KpiCard label="Stock Days"
                value={data.stores.stock_days.total_days_of_stock != null
                  ? `${data.stores.stock_days.total_days_of_stock}` : '—'}
                sub="at the last 12 months' usage" icon={Timer}
                help={OVERVIEW_HELP.stockDays} />
              <KpiCard label="Dead Stock" value={money(data.stores.dead_stock.value)}
                sub={`${data.stores.dead_stock.items.toLocaleString()} items · ${data.stores.dead_stock.value_pct ?? 0}% of value`}
                direction={data.stores.dead_stock.items ? 'up' : null} goodWhen="down"
                refs={data.stores.references.dead_stock}
                fetchRefs={storesRefs('stores.dead_stock')}
                help={withBasis(OVERVIEW_HELP.deadStock,
                  data.stores.dead_stock.exceeds_history
                    ? `The ${data.stores.dead_stock.threshold_days}-day threshold reaches further back than the ${data.stores.dead_stock.history_days} days of issuance history, so this really means "never issued in the data we hold".`
                    : `No issuance in ${data.stores.dead_stock.threshold_days} days, against ${data.stores.dead_stock.history_days} days of history.`)} />
              {/* Replaces the old "Stores holding stock" count, which changed
                  about once a year and said nothing about how the stores run.
                  Same layout as Stock Value: money on top, the item count under
                  it, both for the window in the section header. */}
              <KpiCard label="Issued" value={money(data.stores.issuance.value)}
                sub={countLine(data.stores.issuance.items, 'item')}
                icon={Boxes}
                refs={data.stores.references.issuance}
                fetchRefs={storesRefs('stores.issuance')}
                help={withBasis(OVERVIEW_HELP.issued,
                  `${data.stores.issuance.lines.toLocaleString()} issuance lines in ${data.stores.period?.label ?? 'the period'}, over ${data.stores.issuance.items.toLocaleString()} distinct item codes.`)} />
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ChartCard title="Stock value by store">
                <RankedBar data={data.stores.value_by_store.map((s) => ({
                  ...s, label: s.branch, count: s.items, value: s.stock_value,
                }))} category="label" value="count" valueKey="value"
                  countNoun="item" height={220} unit="Items" />
              </ChartCard>

              <ChartCard title="Stock days by store">
                <RankedBar data={data.stores.stock_days.by_branch.map((s) => ({
                  ...s, label: s.branch, count: s.days_of_stock ?? 0, value: s.stock_value,
                }))} category="label" value="count" valueKey="value"
                  height={220} unit="Days of stock" />
                <p className="mt-2 text-xs text-muted">
                  Stock value divided by the daily usage rate over the last{' '}
                  {data.stores.stock_days.window_days} days. Hover for the stock value.
                </p>
              </ChartCard>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
