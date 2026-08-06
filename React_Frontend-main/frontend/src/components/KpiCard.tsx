import { Check, TriangleAlert, Circle, type LucideIcon } from 'lucide-react'
import { Card, CardContent } from './ui/card'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND } from '@/theme/tokens'

export interface KpiData {
  label: string
  value: string
  delta?: string
  direction?: 'up' | 'down' | null
  goodWhen?: 'up' | 'down'
  sub?: string
  /** Real historical values (e.g. weekly totals) for a tiny trend line —
   * omit entirely when there's no real series behind a number. */
  spark?: number[]
  /** What this metric IS (a clock for cycle time, a ship for imports, ...).
   * Falls back to a generic status glyph (check/alert) when omitted. */
  icon?: LucideIcon
}

function Sparkline({ values, color, gradientId }: { values: number[]; color: string; gradientId: string }) {
  const clean = values.filter((v) => v !== null && v !== undefined)
  if (clean.length < 2) return null
  const width = 160
  const height = 32
  const lo = Math.min(...clean)
  const hi = Math.max(...clean)
  const span = hi - lo || 1
  const points = clean.map((v, i) => {
    const x = (i / (clean.length - 1)) * width
    const y = height - 2 - ((v - lo) / span) * (height - 4)
    return [x, y] as const
  })
  const line = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `0,${height} ${line} ${width},${height}`

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="mt-2.5 w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.35} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#${gradientId})`} />
      <polyline points={line} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function KpiCard({ label, value, delta, direction, goodWhen = 'down', sub, spark, icon }: KpiData) {
  const { colors } = useTheme()
  const hasDirection = direction === 'up' || direction === 'down'
  const isGood = hasDirection && direction === goodWhen
  const ink = hasDirection ? (isGood ? colors.healthy : colors.risk) : BRAND
  const Icon = icon ?? (hasDirection ? (isGood ? Check : TriangleAlert) : Circle)
  const gradientId = `spark-${label.replace(/\s+/g, '-').toLowerCase()}`

  return (
    <Card className="relative overflow-hidden border-l-4" style={{ borderLeftColor: ink }}>
      {/* Large faint glyph — gives each card a distinct identity at a glance,
          purely decorative (aria-hidden), clipped so it never crowds text. */}
      <Icon
        aria-hidden
        size={96}
        strokeWidth={1.25}
        className="pointer-events-none absolute -bottom-4 -right-4 opacity-[0.06]"
        style={{ color: ink }}
      />
      <CardContent className="relative p-5">
        <div className="flex items-center justify-between">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg"
            style={{ backgroundColor: `${ink}1A`, color: ink }}
          >
            <Icon size={16} fill={Icon === Circle ? ink : 'none'} />
          </div>
          {hasDirection && delta && (
            <span
              className="rounded-full px-2 py-0.5 text-xs font-semibold"
              style={{ backgroundColor: colors.canvasAlt, color: ink }}
            >
              {direction === 'up' ? '▲' : '▼'} {delta}
            </span>
          )}
        </div>
        <p className="font-display mt-3 text-3xl font-extrabold text-navy">{value}</p>
        <p className="text-sm font-medium text-muted">{label}</p>
        {!hasDirection && delta && <p className="mt-1 text-xs text-muted">{delta}</p>}
        {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
        {spark && <Sparkline values={spark} color={ink} gradientId={gradientId} />}
      </CardContent>
    </Card>
  )
}
