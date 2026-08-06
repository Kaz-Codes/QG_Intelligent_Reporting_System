export function money(value: number): string {
  if (value >= 1_000_000) return `PKR ${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `PKR ${Math.round(value / 1_000)}K`
  return `PKR ${Math.round(value).toLocaleString()}`
}

export function shortDate(input: string | Date): string {
  const d = typeof input === 'string' ? new Date(input) : input
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export interface WeeklyPoint {
  week: string
  value: number
}

const AGING_ORDER = ['0-30 days', '31-60 days', '61-90 days', '90+ days'] as const

/** Bucket a list of day counts into the standard 4 aging tiers used across
 * the app (0-30 / 31-60 / 61-90 / 90+ days). */
export function agingBuckets(days: number[]): { bucket: string; orders: number }[] {
  const counts = { '0-30 days': 0, '31-60 days': 0, '61-90 days': 0, '90+ days': 0 }
  for (const d of days) {
    if (d <= 30) counts['0-30 days']++
    else if (d <= 60) counts['31-60 days']++
    else if (d <= 90) counts['61-90 days']++
    else counts['90+ days']++
  }
  return AGING_ORDER.map((bucket) => ({ bucket, orders: counts[bucket] }))
}

/** Whether `date` falls within a "YYYY-MM-DD" from/to range (either bound
 * may be '' for unbounded) — backs every DateRangeFilter across the app. */
export function dateInRange(date: Date, from: string, to: string): boolean {
  const ymd = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
  if (from && ymd < from) return false
  if (to && ymd > to) return false
  return true
}

function startOfWeek(d: Date): Date {
  const date = new Date(d)
  const day = date.getDay()
  const diff = (day + 6) % 7 // Monday start
  date.setDate(date.getDate() - diff)
  date.setHours(0, 0, 0, 0)
  return date
}

/** Group rows into real weekly sums — same granularity as the old
 * ui.weekly_trend_points(), which chose weekly over monthly because a
 * short real date range gives too few monthly points to read as a trend. */
export function weeklyTrendPoints(rows: { date: Date; value: number }[]): WeeklyPoint[] {
  const buckets = new Map<string, number>()
  for (const { date, value } of rows) {
    const key = startOfWeek(date).toISOString().slice(0, 10)
    buckets.set(key, (buckets.get(key) ?? 0) + value)
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([week, value]) => ({ week, value }))
}
