import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND, VIOLET } from '@/theme/tokens'
import { tooltipStyle } from './utils'

interface Props {
  data: Record<string, unknown>[]
  x: string
  y: string
  height?: number
  /** For embedding inside a colored/gradient card instead of a plain
   * surface — swaps the line/axis palette for a light-on-dark one. */
  onDark?: boolean
}

/** Smooth trend line with a brand-gradient fill — for values over time. */
export function TrendLine({ data, x, y, height = 300, onDark = false }: Props) {
  const { colors } = useTheme()
  const gradientId = `trend-${x}-${y}${onDark ? '-dark' : ''}`
  const lineColor = onDark ? '#FFFFFF' : BRAND
  const dotColor = onDark ? '#FFFFFF' : VIOLET
  const gridColor = onDark ? 'rgba(255,255,255,0.18)' : colors.line
  const tickColor = onDark ? 'rgba(255,255,255,0.75)' : colors.muted

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity={onDark ? 0.35 : 0.28} />
            <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={gridColor} />
        <XAxis
          dataKey={x}
          tick={{ fill: tickColor, fontSize: 12 }}
          axisLine={{ stroke: gridColor }}
          tickLine={false}
          interval={Math.max(0, Math.ceil(data.length / 8) - 1)}
        />
        <YAxis tick={{ fill: tickColor, fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip {...(onDark ? { ...tooltipStyle, contentStyle: { ...tooltipStyle.contentStyle, background: '#1F1B4D' } } : tooltipStyle)} />
        <Area
          type="monotone"
          dataKey={y}
          stroke={lineColor}
          strokeWidth={3}
          fill={`url(#${gradientId})`}
          dot={{ r: 4, fill: dotColor, strokeWidth: 0 }}
          activeDot={{ r: 6 }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
