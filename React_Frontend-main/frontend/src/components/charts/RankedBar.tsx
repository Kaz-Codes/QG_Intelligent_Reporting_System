import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ReferenceLine, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND, BRAND_LIGHT, BRAND_DEEP, GOLD } from '@/theme/tokens'
import { lerpColor, tooltipStyle } from './utils'

interface Props {
  data: Record<string, unknown>[]
  category: string
  value: string
  height?: number
  benchmark?: number
  /** Highlight only the worst (highest) bar in risk-red instead of a
   * magnitude gradient — for "flag the one outlier" charts. */
  invertColor?: boolean
}

/** Horizontal ranked bar — supplier performance, top items, etc. */
export function RankedBar({ data, category, value, height = 320, benchmark, invertColor = false }: Props) {
  const { colors } = useTheme()
  const sorted = [...data].sort((a, b) => (a[value] as number) - (b[value] as number))
  const values = sorted.map((d) => d[value] as number)
  const max = Math.max(...values)
  const min = Math.min(...values)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 5, right: 24, left: 8, bottom: 5 }}>
        <CartesianGrid horizontal={false} stroke={colors.line} />
        <XAxis type="number" tick={{ fill: colors.muted, fontSize: 12 }} axisLine={{ stroke: colors.line }} tickLine={false} />
        <YAxis
          type="category"
          dataKey={category}
          width={130}
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
