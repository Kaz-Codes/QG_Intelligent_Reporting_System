import { mulberry32, randInt, SUPPLIERS } from './shared'

const rng = mulberry32(7)

function weekLabel(i: number, totalWeeks: number): string {
  const d = new Date()
  d.setDate(d.getDate() - (totalWeeks - 1 - i) * 7)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const WEEKS = 12
export const weeklyTrend = Array.from({ length: WEEKS }, (_, i) => ({
  week: weekLabel(i, WEEKS),
  purchase_value: Number((11 + i * 0.9 + (rng() - 0.5) * 2).toFixed(2)),
  avg_cycle_days: Number((8.4 - i * 0.18 + (rng() - 0.5) * 0.8).toFixed(1)),
  delayed: randInt(rng, 3, 9),
  on_time_pct: Number((79 + i * 1.1 + (rng() - 0.5) * 3).toFixed(0)),
}))

export function getWeeklyTrend() {
  return weeklyTrend
}

export function getHealth(): { level: 'healthy' | 'watch' | 'risk'; message: string } {
  return { level: 'watch', message: 'Supply chain stable — 3 issues need attention' }
}

export function getDashboardKpisRich() {
  return {
    purchaseValue: {
      value: 84_500_000, delta: '8% vs last month', direction: 'up' as const, goodWhen: 'up' as const,
    },
    avgCycleTime: {
      value: '6.4 days', delta: '12% faster than last month', direction: 'down' as const, goodWhen: 'down' as const,
    },
    delayedOrders: {
      value: 42, delta: '12% vs last month', direction: 'up' as const, goodWhen: 'down' as const,
    },
    onTimeRate: {
      value: '86%', delta: '3% vs last month', direction: 'up' as const, goodWhen: 'up' as const,
    },
    itemsAtRisk: {
      value: 37, delta: '9 more than last month', direction: 'up' as const, goodWhen: 'down' as const,
    },
    openImports: {
      value: 14, delta: 'steady', direction: null, goodWhen: 'down' as const,
    },
  }
}

export function getAlerts() {
  return [
    { level: 'high' as const, message: '3 suppliers chronically late this quarter' },
    { level: 'high' as const, message: '5 items below reorder point' },
    { level: 'medium' as const, message: '12 purchase orders pending over 30 days' },
    { level: 'low' as const, message: '2 shipments awaiting customs clearance' },
  ]
}

export function getSupplierPerformance() {
  const onTimePct = [92, 78, 64, 88, 71]
  return SUPPLIERS.map((supplier, i) => ({ supplier, on_time_pct: onTimePct[i] }))
}

export function getStatusSplit(kind: 'purchases' | 'imports' | 'inventory' = 'purchases') {
  if (kind === 'purchases') return { labels: ['Completed', 'Pending', 'Delayed'], values: [62, 26, 12] }
  if (kind === 'imports') return { labels: ['Cleared', 'In Transit', 'Pending Clearance'], values: [9, 11, 5] }
  return { labels: ['OK', 'Below Reorder'], values: [63, 37] }
}

export function getAging() {
  return [
    { bucket: '0-30 days', orders: 98 },
    { bucket: '31-60 days', orders: 44 },
    { bucket: '61-90 days', orders: 21 },
    { bucket: '90+ days', orders: 13 },
  ]
}
