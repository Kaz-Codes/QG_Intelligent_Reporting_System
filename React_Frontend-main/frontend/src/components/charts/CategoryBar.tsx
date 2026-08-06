import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND_LIGHT, BRAND_DEEP } from '@/theme/tokens'
import { lerpColor, tooltipStyle, compactNumber, axisLabel } from './utils'

interface Props {
  data: Record<string, unknown>[]
  category: string
  value: string
  height?: number
  /** What the value axis counts — "PKR", "Orders", "Items". Without it a bare
   * number says nothing about what's being measured. */
  unit?: string
}

/** Vertical bar for category comparison, brand-gradient by magnitude. */
export function CategoryBar({ data, category, value, height = 300, unit }: Props) {
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
        <Tooltip {...tooltipStyle} />
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
