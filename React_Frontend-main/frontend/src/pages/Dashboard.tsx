import { useState } from 'react'
import { TriangleAlert, CircleAlert, Info, Timer, PackageX, CheckCircle2, Plane, Sparkles } from 'lucide-react'
import { KpiCard } from '@/components/KpiCard'
import { HeroStat } from '@/components/HeroStat'
import { InsightsCard } from '@/components/InsightsCard'
import { SegmentedControl } from '@/components/SegmentedControl'
import { Card, CardContent } from '@/components/ui/card'
import { RankedBar } from '@/components/charts/RankedBar'
import { Donut } from '@/components/charts/Donut'
import { AgingBuckets } from '@/components/charts/AgingBuckets'
import { money } from '@/lib/format'
import { useTheme } from '@/theme/ThemeContext'
import { useAuth } from '@/features/auth/AuthContext'
import {
  getHealth, getDashboardKpisRich, weeklyTrend, getAlerts,
  getSupplierPerformance, getStatusSplit, getAging,
} from '@/lib/mockData/dashboard'

const RANGE_OPTIONS = [
  { value: '4', label: '4W' }, { value: '8', label: '8W' }, { value: '12', label: '12W' },
] as const
const INSIGHT_TABS = [
  { value: 'suppliers', label: 'Suppliers' },
  { value: 'status', label: 'Status' },
  { value: 'aging', label: 'Aging' },
] as const

const ALERT_ICON = { high: TriangleAlert, medium: CircleAlert, low: Info }

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export function Dashboard() {
  const { colors } = useTheme()
  const { user } = useAuth()
  const [rangeWeeks, setRangeWeeks] = useState<'4' | '8' | '12'>('8')
  const [insightTab, setInsightTab] = useState<(typeof INSIGHT_TABS)[number]['value']>('suppliers')

  const health = getHealth()
  const kpis = getDashboardKpisRich()
  const trend = weeklyTrend.slice(-Number(rangeWeeks))
  const alerts = getAlerts()
  const supplierPerf = getSupplierPerformance()
  const statusSplit = getStatusSplit('purchases')
  const aging = getAging()

  const healthColor =
    health.level === 'healthy' ? colors.healthy : health.level === 'risk' ? colors.risk : colors.watch
  const alertColor = { high: colors.risk, medium: colors.watch, low: colors.info }
  const firstName = user?.name?.split(' ')[0]

  const heroHeader = (
    <div className="flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-xl">
        <span className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold">
          <Sparkles size={12} />
          Executive Dashboard
        </span>
        <h1 className="font-display text-3xl font-extrabold leading-tight tracking-tight lg:text-4xl">
          {greeting()}{firstName ? `, ${firstName}` : ''} 👋
        </h1>
        <p className="mt-2 max-w-md text-sm text-white/70">
          Here's how the supply chain is performing today.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold">
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: healthColor }} />
          {health.message}
        </span>
        <SegmentedControl options={RANGE_OPTIONS} value={rangeWeeks} onChange={setRangeWeeks} variant="onBrand" />
      </div>
    </div>
  )

  return (
    <div className="flex flex-col gap-6">
      <HeroStat
        header={heroHeader}
        label="Purchase Value"
        value={money(kpis.purchaseValue.value)}
        delta={kpis.purchaseValue.delta}
        direction={kpis.purchaseValue.direction}
        trendData={trend}
        trendX="week"
        trendY="purchase_value"
        trendHeight={220}
        caption={`PKR millions per week · last ${rangeWeeks} weeks`}
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <KpiCard label="Avg Cycle Time" value={kpis.avgCycleTime.value} delta={kpis.avgCycleTime.delta}
          direction={kpis.avgCycleTime.direction} goodWhen={kpis.avgCycleTime.goodWhen} icon={Timer}
          spark={weeklyTrend.map((w) => w.avg_cycle_days)} />
        <KpiCard label="Delayed Orders" value={`${kpis.delayedOrders.value}`} delta={kpis.delayedOrders.delta}
          direction={kpis.delayedOrders.direction} goodWhen={kpis.delayedOrders.goodWhen} icon={TriangleAlert}
          spark={weeklyTrend.map((w) => w.delayed)} />
        <KpiCard label="On-Time Delivery" value={kpis.onTimeRate.value} delta={kpis.onTimeRate.delta}
          direction={kpis.onTimeRate.direction} goodWhen={kpis.onTimeRate.goodWhen} icon={CheckCircle2}
          spark={weeklyTrend.map((w) => w.on_time_pct)} />
        <KpiCard label="Items at Risk" value={`${kpis.itemsAtRisk.value}`} delta={kpis.itemsAtRisk.delta}
          direction={kpis.itemsAtRisk.direction} goodWhen={kpis.itemsAtRisk.goodWhen} icon={PackageX} />
        <KpiCard label="Open Imports" value={`${kpis.openImports.value}`} delta={kpis.openImports.delta}
          direction={kpis.openImports.direction} goodWhen={kpis.openImports.goodWhen} icon={Plane} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={INSIGHT_TABS} active={insightTab} onChange={setInsightTab} className="lg:col-span-2">
          {insightTab === 'suppliers' && (
            <RankedBar data={supplierPerf} category="supplier" value="on_time_pct" height={300} benchmark={85} />
          )}
          {insightTab === 'status' && <Donut labels={statusSplit.labels} values={statusSplit.values} height={300} />}
          {insightTab === 'aging' && <AgingBuckets data={aging} height={300} />}
        </InsightsCard>

        <Card>
          <CardContent className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm font-semibold text-ink">Attention Required</p>
              <span
                className="flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold"
                style={{ backgroundColor: colors.riskBg, color: colors.risk }}
              >
                {alerts.length}
              </span>
            </div>
            <div className="flex flex-col">
              {alerts.map((a, i) => {
                const Icon = ALERT_ICON[a.level]
                const fg = alertColor[a.level]
                return (
                  <div
                    key={i}
                    className={`flex items-start gap-3 rounded-lg px-1.5 py-2.5 transition-colors hover:bg-canvas-alt ${i !== 0 ? 'border-t border-line' : ''}`}
                  >
                    <span
                      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                      style={{ backgroundColor: `${fg}1A`, color: fg }}
                    >
                      <Icon size={14} />
                    </span>
                    <p className="text-sm leading-snug text-ink">{a.message}</p>
                  </div>
                )
              })}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
