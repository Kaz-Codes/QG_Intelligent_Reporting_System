import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND_LIGHT, BRAND_DEEP } from '@/theme/tokens'
import { lerpColor, tooltipStyle, compactNumber, axisLabel } from './utils'
import { compactMoney, count } from '@/lib/format'

interface Props {
  data: Record<string, unknown>[]
  category: string
  value: string
  height?: number
  /** What the value axis counts — "PKR", "Orders", "Items". Without it a bare
   * number says nothing about what's being measured. */
  unit?: string
  /** A money field to reveal on hover — the axis stays a count. See RankedBar. */
  valueKey?: string
  /** What one bar counts — "order", "consignment", "line". Pluralised. */
  countNoun?: string
}

/** Vertical bar for category comparison, brand-gradient by magnitude. */
export function CategoryBar({
  data, category, value, height = 300, unit, valueKey, countNoun,
}: Props) {
  const { colors } = useTheme()
  const values = data.map((d) => d[value] as number)
  const max = Math.max(...values)
  const min = Math.min(...values)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 10, right: 10, left: unit ? 12 : 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={colors.line} />
        <XAxis dataKey={category} tick={{ fill: colors.muted, fontSize: 12 }} axisLine={{ stroke: colors.line }} tickLine={false} />
        <YAxis
          tick={{ fill: colors.muted, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={compactNumber}
          label={axisLabel(unit, 'y', colors.muted)}
        />
        <Tooltip
          {...tooltipStyle}
          formatter={(raw: unknown, _name: unknown, entry: unknown) => {
            const n = Number(raw)
            const row = (entry as { payload?: Record<string, unknown> })?.payload
            const amount = valueKey ? Number(row?.[valueKey]) : NaN

            const shown = countNoun ? count(n, countNoun) : n.toLocaleString()
            return Number.isFinite(amount)
              ? [`${shown} · ${compactMoney(amount)}`, '']
              : [shown, '']
          }}
        />
        <Bar dataKey={value} radius={[4, 4, 0, 0]} maxBarSize={72} isAnimationActive={false}>
          {data.map((d, i) => {
            const v = d[value] as number
            const t = max === min ? 1 : (v - min) / (max - min)
            return <Cell key={i} fill={lerpColor(BRAND_LIGHT, BRAND_DEEP, t)} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
