import { useState } from 'react'
import { Sparkles, Ship, Wallet, Truck, Warehouse, Boxes, Timer } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { KpiCard } from '@/components/KpiCard'
import { ChartCard } from '@/components/ChartCard'
import { LiveDataState } from '@/components/LiveDataState'
import { RankedBar } from '@/components/charts/RankedBar'
import { PeriodFilter, EMPTY_PERIOD, type Period } from '@/components/PeriodFilter'
import { useAuth } from '@/features/auth/AuthContext'
import { money, compactMoney } from '@/lib/format'
import { OVERVIEW_HELP, withBasis } from '@/lib/metricHelp'
import { useOverviewDashboard } from '@/lib/api/useOverviewDashboard'

/**
 * The cross-module overview, on live data.
 *
 * Previously this whole screen was mock — hardcoded KPIs, a fabricated weekly
 * trend, invented alerts and supplier scores. Every number is now a real
 * aggregate from `/dashboard/overview`.
 *
 * Counting units match the module screens exactly: ORDERS for procurement,
 * CONSIGNMENTS for imports, ITEMS for stock. Nothing here is line-level.
 *
 * Period vs lifetime is labelled per section rather than left to be inferred:
 * imports and procurement follow the window; logistics and stores are running
 * totals and snapshots, and say so.
 */

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export function OverviewTab() {
  const { user } = useAuth()
  const [period, setPeriod] = useState<Period>(EMPTY_PERIOD)

  const { data, isLoading, isError, error } = useOverviewDashboard({
    date_from: period.from || undefined,
    date_to: period.to || undefined,
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
              Imports, procurement, logistics and stores — every figure below is
              live, and each one names the period it covers.
            </p>
          </div>
        </div>

        <div className="mt-6 border-t border-line pt-4">
          <PeriodFilter period={period} onChange={setPeriod} label="Reporting period" />
          {data && (
            <p className="mt-3 text-xs text-muted">
              Imports and procurement figures cover{' '}
              <span className="font-medium text-ink">{data.period.label}</span>.
              Logistics and stores are running totals, not period figures.
            </p>
          )}
        </div>
      </Card>

      <LiveDataState isLoading={isLoading} isError={isError} error={error} skeleton="dashboard" />

      {data && (
        <>
          {/* ---------------------------------------------------- imports */}
          <section className="flex flex-col gap-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Ship size={15} className="text-muted" /> Imports
              <span className="text-xs font-normal text-muted">· {data.period.label}</span>
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <KpiCard label="Import Value" value={money(data.imports.period_value.value)}
                sub={`${data.imports.period_value.consignments} consignments`}
                icon={Wallet}
                help={withBasis(OVERVIEW_HELP.importValue,
                  data.imports.period_value.undated.consignments
                    ? `${data.imports.period_value.undated.consignments} consignments worth ${compactMoney(data.imports.period_value.undated.value)} have no ETD, so they fall in no period at all.`
                    : undefined)} />
              <KpiCard label="In Process" value={data.imports.in_process.total.toLocaleString()}
                sub="not yet arrived or cancelled" icon={Ship}
                help={OVERVIEW_HELP.importsInProcess} />
              <KpiCard label="Shafts In Process" value={data.imports.shafts.in_process.toLocaleString()}
                sub={`${data.imports.shafts.arrived} arrived of ${data.imports.shafts.total}`}
                help={OVERVIEW_HELP.shafts} />
              <KpiCard label="Shafts Arrived" value={data.imports.shafts.arrived.toLocaleString()}
                sub={data.imports.shafts.arrived_pct != null ? `${data.imports.shafts.arrived_pct}% of shaft consignments` : undefined}
                help={OVERVIEW_HELP.shafts} />
            </div>

            {data.imports.in_process.by_stage.length > 0 && (
              <ChartCard title="Imports in process, by stage">
                <RankedBar data={data.imports.in_process.by_stage} category="stage"
                  value="consignments" countNoun="consignment" height={220} unit="Consignments" />
              </ChartCard>
            )}
          </section>

          {/* ----------------------------------------------- procurement */}
          <section className="flex flex-col gap-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Wallet size={15} className="text-muted" /> Local Procurement
              <span className="text-xs font-normal text-muted">· {data.period.label}</span>
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <KpiCard label="Procurement Value" value={money(data.procurement.period_value.value)}
                sub={`${data.procurement.period_value.orders.toLocaleString()} orders`}
                icon={Wallet} help={OVERVIEW_HELP.procurementValue} />
              <KpiCard label="Delay Rate"
                value={data.procurement.delay.delay_pct != null ? `${data.procurement.delay.delay_pct}%` : '—'}
                direction={data.procurement.delay.late_orders ? 'up' : null} goodWhen="down"
                help={withBasis(OVERVIEW_HELP.procurementDelay,
                  `${data.procurement.delay.late_orders.toLocaleString()} late of ${data.procurement.delay.basis.toLocaleString()} orders with a required date.`)} />
              <KpiCard label="Cycle Time"
                value={data.procurement.cycle_time.store_to_purchase_days != null
                  ? `${data.procurement.cycle_time.store_to_purchase_days} days` : '—'}
                sub="store demand to purchase" icon={Timer}
                help={withBasis(OVERVIEW_HELP.cycleTime,
                  `Measured on ${data.procurement.cycle_time.store_to_purchase_basis.toLocaleString()} orders. Order-to-purchase is ${data.procurement.cycle_time.po_to_purchase_days ?? '—'} days.`)} />
              <KpiCard label="Categories"
                value={data.procurement.category_split.categories_total.toLocaleString()}
                sub="distinct item categories" icon={Boxes}
                help={OVERVIEW_HELP.categories} />
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
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Truck size={15} className="text-muted" /> Logistics
              <span className="text-xs font-normal text-muted">· running totals, not this period</span>
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <KpiCard label="Trucking Cost" value={money(data.logistics.trucking_cost.total)}
                sub="all jobs to date" icon={Truck}
                help={OVERVIEW_HELP.truckingCost} />
              {data.logistics.trucking_cost.by_movement.slice(0, 2).map((m) => (
                <KpiCard key={m.movement_type} label={`${m.movement_type} Freight`}
                  value={money(m.actual_freight)}
                  sub={`${m.jobs} jobs · ${m.share_pct ?? 0}% of cost`}
                  help={OVERVIEW_HELP.truckingCost} />
              ))}
              <KpiCard label="Shipments Handled"
                value={data.logistics.shipments_handled.total.toLocaleString()}
                sub={`${data.logistics.shipments_handled.export_shipments} export · ${data.logistics.shipments_handled.import_shipments} import`}
                icon={Ship} help={OVERVIEW_HELP.shipmentsHandled} />
            </div>
          </section>

          {/* ---------------------------------------------------- stores */}
          <section className="flex flex-col gap-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Warehouse size={15} className="text-muted" /> Stores
              <span className="text-xs font-normal text-muted">· a snapshot of today</span>
            </h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <KpiCard label="Stock Value" value={money(data.stores.stock_value.stock_value)}
                sub={`${data.stores.stock_value.items.toLocaleString()} items`}
                icon={Warehouse} help={OVERVIEW_HELP.stockValue} />
              <KpiCard label="Stock Days"
                value={data.stores.stock_days.total_days_of_stock != null
                  ? `${data.stores.stock_days.total_days_of_stock}` : '—'}
                sub="at the last 12 months' usage" icon={Timer}
                help={OVERVIEW_HELP.stockDays} />
              <KpiCard label="Dead Stock" value={money(data.stores.dead_stock.value)}
                sub={`${data.stores.dead_stock.items.toLocaleString()} items · ${data.stores.dead_stock.value_pct ?? 0}% of value`}
                direction={data.stores.dead_stock.items ? 'up' : null} goodWhen="down"
                help={withBasis(OVERVIEW_HELP.deadStock,
                  data.stores.dead_stock.exceeds_history
                    ? `The ${data.stores.dead_stock.threshold_days}-day threshold reaches further back than the ${data.stores.dead_stock.history_days} days of issuance history, so this really means "never issued in the data we hold".`
                    : `No issuance in ${data.stores.dead_stock.threshold_days} days, against ${data.stores.dead_stock.history_days} days of history.`)} />
              <KpiCard label="Stores" value={data.stores.value_by_store.length.toLocaleString()}
                sub="holding stock" icon={Boxes}
                help={OVERVIEW_HELP.stores} />
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
