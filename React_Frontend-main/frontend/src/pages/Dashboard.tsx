import { useState } from 'react'
import {
  TriangleAlert, CircleAlert, Info, Timer, PackageX, CheckCircle2, Plane,
  Sparkles, Wallet, ArrowUpRight, ArrowDownRight, type LucideIcon,
} from 'lucide-react'
import { SegmentedControl } from '@/components/SegmentedControl'
import { RankedBar } from '@/components/charts/RankedBar'
import { Donut } from '@/components/charts/Donut'
import { AgingBuckets } from '@/components/charts/AgingBuckets'
import { TrendLine } from '@/components/charts/TrendLine'
import { money } from '@/lib/format'
import { cn } from '@/lib/utils'
import { BRAND } from '@/theme/tokens'
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
  { value: 'aging', label: 'Aging' },
] as const

const ALERT_ICON = { high: TriangleAlert, medium: CircleAlert, low: Info }

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

/** Semi-transparent card — no backdrop-blur (that's what caused the earlier
 * lag: blur is recomputed every frame, and this page has continuous aurora
 * animation + hover transforms behind/on every card, which would make it
 * worse, not better). Plain alpha over the page's photo backdrop is
 * essentially free, and the backdrop's own scrim (see ThemedBackground's
 * DashboardPhoto) keeps text readable underneath it.
 *
 * Opacity is lower in light mode than dark (bg-surface/65 vs /75): the
 * light scrim in DashboardPhoto is itself a near-opaque white
 * (rgba(255,255,255,0.5)), so a light-mode card on top of it was stacking
 * two white layers and reading as almost fully opaque — hiding the photo
 * entirely. Dark mode doesn't have that stacking problem, so it keeps the
 * original /75.
 *
 * The inset top highlight (a 1px bright line, near-invisible bottom line)
 * is what actually reads as "glass" here instead of blur — it's a plain
 * box-shadow, not backdrop-filter, so it costs nothing on scroll/repaint. */
function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-2xl border-2 border-line/80 bg-surface/28 shadow-sm dark:border-line/45 dark:bg-surface/42',
        'shadow-[inset_0_1px_0_rgba(255,255,255,0.55),0_1px_2px_rgba(16,24,40,0.04)]',
        'dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_1px_2px_rgba(0,0,0,0.25)]',
        'transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-0.5 hover:shadow-md',
        className,
      )}
    >
      {children}
    </div>
  )
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const clean = values.filter((v) => v !== null && v !== undefined)
  if (clean.length < 2) return null
  const width = 160
  const height = 30
  const lo = Math.min(...clean)
  const hi = Math.max(...clean)
  const span = hi - lo || 1
  const pts = clean.map((v, i) => {
    const x = (i / (clean.length - 1)) * width
    const y = height - 2 - ((v - lo) / span) * (height - 4)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-2.5 w-full" preserveAspectRatio="none">
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

interface TileProps {
  label: string
  value: string
  delta?: string
  direction?: 'up' | 'down' | null
  goodWhen?: 'up' | 'down'
  spark?: number[]
  icon: LucideIcon
}

function StatTile({ label, value, delta, direction, goodWhen = 'down', spark, icon: Icon }: TileProps) {
  const { colors } = useTheme()
  const hasDir = direction === 'up' || direction === 'down'
  const isGood = hasDir && direction === goodWhen
  const ink = hasDir ? (isGood ? colors.healthy : colors.risk) : BRAND

  return (
    <Panel className="relative overflow-hidden p-4">
      <span className="absolute left-0 top-0 h-full w-1 rounded-l-2xl" style={{ backgroundColor: ink }} />
      <div className="flex items-center justify-between">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ backgroundColor: `${ink}1A`, color: ink }}>
          <Icon size={16} />
        </span>
        {hasDir && delta && (
          <span className="rounded-full px-2 py-0.5 text-xs font-semibold" style={{ backgroundColor: colors.canvasAlt, color: ink }}>
            {direction === 'up' ? '▲' : '▼'} {delta}
          </span>
        )}
      </div>
      <p className="font-display mt-3 text-2xl font-extrabold text-navy">{value}</p>
      <p className="text-sm font-medium text-muted">{label}</p>
      {!hasDir && delta && <p className="mt-1 text-xs text-muted">{delta}</p>}
      {spark && <Sparkline values={spark} color={ink} />}
    </Panel>
  )
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

  const pv = kpis.purchaseValue
  const DeltaIcon = pv.direction === 'up' ? ArrowUpRight : ArrowDownRight

  return (
    <div className="flex flex-col gap-5">
      {/* Hero band — sits over the page-wide photo (ThemedBackground) like
          every other panel, just with more breathing room for the greeting
          and a few live stats. Even more transparent than the (already
          lowered) Panel default in light mode: this band has the least
          text/texture over it of any card on the page and covers the
          widest, most "photo-forward" strip, so it can afford to show more
          of the image through it than a chart-heavy card can. Dark mode
          keeps the Panel default /75. */}
      <Panel className="bg-surface/15 dark:bg-surface/28 p-6 lg:p-8">
        <div className="flex min-h-[200px] flex-col justify-between gap-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <span className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-brand/25 bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">
                <Sparkles size={12} />
                Executive Dashboard
              </span>
              <h1 className="font-display text-2xl font-extrabold leading-tight tracking-tight text-navy lg:text-3xl">
                {greeting()}{firstName ? `, ${firstName}` : ''} 👋
              </h1>
              <p className="mt-1 max-w-md text-sm text-muted">Here's how the supply chain is performing today.</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/80 px-3 py-1.5 text-xs font-semibold text-ink">
                <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: healthColor }} />
                {health.message}
              </span>
              <SegmentedControl options={RANGE_OPTIONS} value={rangeWeeks} onChange={setRangeWeeks} variant="solid" />
            </div>
          </div>

          <div className="flex flex-wrap gap-x-8 gap-y-3">
            {[
              { k: 'On-Time Delivery', v: kpis.onTimeRate.value },
              { k: 'Open Imports', v: `${kpis.openImports.value}` },
              { k: 'Avg Cycle Time', v: kpis.avgCycleTime.value },
            ].map((s) => (
              <div key={s.k}>
                <p className="font-display text-xl font-extrabold text-navy">{s.v}</p>
                <p className="text-xs font-medium text-muted">{s.k}</p>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      {/* Hero metric + Attention, side by side */}
      <div className="grid gap-5 lg:grid-cols-3">
        <Panel className="relative overflow-hidden p-6 lg:col-span-2 lg:p-7">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-muted">Purchase Value</p>
              <p className="font-display mt-1 text-4xl font-extrabold tracking-tight text-navy">{money(pv.value)}</p>
              {pv.delta && (
                <span className="mt-3 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold"
                  style={{ backgroundColor: colors.healthyBg, color: colors.healthy }}>
                  <DeltaIcon size={12} />
                  {pv.delta}
                </span>
              )}
            </div>
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
              <Wallet size={20} />
            </span>
          </div>
          <div className="mt-2">
            <TrendLine data={trend} x="week" y="purchase_value" height={210} />
          </div>
          <p className="mt-1 text-xs text-muted">PKR millions per week · last {rangeWeeks} weeks</p>
        </Panel>

        <Panel className="p-5 lg:col-span-1">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm font-semibold text-ink">Attention Required</p>
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold"
              style={{ backgroundColor: colors.riskBg, color: colors.risk }}>
              {alerts.length}
            </span>
          </div>
          <div className="flex flex-col">
            {alerts.map((a, i) => {
              const Icon = ALERT_ICON[a.level]
              const fg = alertColor[a.level]
              return (
                <div key={i} className={`flex items-start gap-3 rounded-lg px-1.5 py-2.5 transition-colors hover:bg-canvas-alt ${i !== 0 ? 'border-t border-line' : ''}`}>
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full"
                    style={{ backgroundColor: `${fg}1A`, color: fg }}>
                    <Icon size={14} />
                  </span>
                  <p className="text-sm leading-snug text-ink">{a.message}</p>
                </div>
              )
            })}
          </div>
        </Panel>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatTile label="Avg Cycle Time" value={kpis.avgCycleTime.value} delta={kpis.avgCycleTime.delta}
          direction={kpis.avgCycleTime.direction} goodWhen={kpis.avgCycleTime.goodWhen} icon={Timer}
          spark={weeklyTrend.map((w) => w.avg_cycle_days)} />
        <StatTile label="Delayed Orders" value={`${kpis.delayedOrders.value}`} delta={kpis.delayedOrders.delta}
          direction={kpis.delayedOrders.direction} goodWhen={kpis.delayedOrders.goodWhen} icon={TriangleAlert}
          spark={weeklyTrend.map((w) => w.delayed)} />
        <StatTile label="On-Time Delivery" value={kpis.onTimeRate.value} delta={kpis.onTimeRate.delta}
          direction={kpis.onTimeRate.direction} goodWhen={kpis.onTimeRate.goodWhen} icon={CheckCircle2}
          spark={weeklyTrend.map((w) => w.on_time_pct)} />
        <StatTile label="Items at Risk" value={`${kpis.itemsAtRisk.value}`} delta={kpis.itemsAtRisk.delta}
          direction={kpis.itemsAtRisk.direction} goodWhen={kpis.itemsAtRisk.goodWhen} icon={PackageX} />
        <StatTile label="Open Imports" value={`${kpis.openImports.value}`} delta={kpis.openImports.delta}
          direction={kpis.openImports.direction} goodWhen={kpis.openImports.goodWhen} icon={Plane} />
      </div>

      {/* Insights + Status split */}
      <div className="grid gap-5 lg:grid-cols-3">
        <Panel className="p-5 lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <p className="text-sm font-semibold text-ink">Insights</p>
            <SegmentedControl options={INSIGHT_TABS} value={insightTab} onChange={setInsightTab} variant="ghost" />
          </div>
          <div key={insightTab} className="animate-fade-in-up">
            {insightTab === 'suppliers' && (
              <RankedBar data={supplierPerf} category="supplier" value="on_time_pct" height={300} benchmark={85} />
            )}
            {insightTab === 'aging' && <AgingBuckets data={aging} height={300} />}
          </div>
        </Panel>

        <Panel className="p-5 lg:col-span-1">
          <p className="mb-4 text-sm font-semibold text-ink">Status Split</p>
          <Donut labels={statusSplit.labels} values={statusSplit.values} height={300} />
        </Panel>
      </div>
    </div>
  )
}
