import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND, BRAND_LIGHT, BRAND_DEEP, GOLD } from '@/theme/tokens'
import { lerpColor, tooltipStyle, compactNumber, axisLabel } from './utils'

interface Props {
  data: Record<string, unknown>[]
  category: string
  value: string
  height?: number
  benchmark?: number
  /** Highlight only the worst (highest) bar in risk-red instead of a
   * magnitude gradient — for "flag the one outlier" charts. */
  invertColor?: boolean
  /** What the value axis measures — "PKR", "Days", "Jobs". Without it a bare
   * number says nothing about what's being compared. */
  unit?: string
}

// The category axis used to be a flat 130px, which was fine for mock labels
// ("Alpha Traders") but silently cut real ones in half — live supplier names
// run to 50 characters and stock item names to 106. The axis now grows with
// the longest label it actually has to draw, and anything still too long is
// ellipsed rather than clipped mid-glyph. Short-label charts stay at exactly
// the old 130px, so nothing that already looked right moves.
const MIN_AXIS_WIDTH = 130
const MAX_AXIS_WIDTH = 240
const CHAR_PX = 6.2

/** Horizontal ranked bar — supplier performance, top items, etc. */
export function RankedBar({ data, category, value, height = 320, benchmark, invertColor = false, unit }: Props) {
  const { colors } = useTheme()
  const sorted = [...data].sort((a, b) => (a[value] as number) - (b[value] as number))
  const values = sorted.map((d) => d[value] as number)
  const max = Math.max(...values)
  const min = Math.min(...values)

  const longestLabel = sorted.reduce((n, d) => Math.max(n, String(d[category] ?? '').length), 0)
  const axisWidth = Math.min(MAX_AXIS_WIDTH, Math.max(MIN_AXIS_WIDTH, Math.ceil(longestLabel * CHAR_PX)))
  const maxChars = Math.floor(axisWidth / CHAR_PX)
  // Only the tick is shortened — the tooltip still gets the raw value, so the
  // full name is always one hover away.
  const formatTick = (tick: unknown) => {
    const label = String(tick ?? '')
    return label.length > maxChars ? `${label.slice(0, maxChars - 1)}…` : label
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 5, right: 24, left: 8, bottom: unit ? 18 : 5 }}>
        <CartesianGrid horizontal={false} stroke={colors.line} />
        <XAxis
          type="number"
          tick={{ fill: colors.muted, fontSize: 12 }}
          axisLine={{ stroke: colors.line }}
          tickLine={false}
          tickFormatter={compactNumber}
          label={axisLabel(unit, 'x', colors.muted)}
        />
        <YAxis
          type="category"
          dataKey={category}
          width={axisWidth}
          tickFormatter={formatTick}
          tick={{ fill: colors.ink, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip {...tooltipStyle} />
        {benchmark !== undefined && (
          <ReferenceLine x={benchmark} stroke={GOLD} strokeDasharray="4 4" label={{ value: 'target', fill: GOLD, fontSize: 11, position: 'insideTopRight' }} />
        )}
        <Bar dataKey={value} radius={[0, 4, 4, 0]} maxBarSize={40} isAnimationActive={false}>
          {sorted.map((d, i) => {
            const v = d[value] as number
            const fill = invertColor
              ? v === max ? colors.risk : BRAND
              : lerpColor(BRAND_LIGHT, BRAND_DEEP, max === min ? 1 : (v - min) / (max - min))
            return <Cell key={i} fill={fill} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
