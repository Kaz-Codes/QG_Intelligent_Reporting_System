import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { statusColors, BRAND } from '@/theme/tokens'
import { tooltipStyle } from './utils'

interface Props {
  labels: string[]
  values: number[]
  height?: number
  /** For narrow containers (e.g. a spotlight card's side panel) — smaller
   * ring, no legend, no outside labels (rely on the tooltip instead) so
   * nothing clips against the container edge. */
  compact?: boolean
}

/** Donut for composition (status split, stock health) — status-like
 * labels get their semantic risk/watch/healthy color where recognized. */
export function Donut({ labels, values, height = 300, compact = false }: Props) {
  const { colors } = useTheme()
  const data = labels.map((label, i) => ({ label, value: values[i] }))
  const total = values.reduce((a, b) => a + b, 0)

  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart margin={compact ? { top: 4, right: 4, bottom: 4, left: 4 } : { top: 20, right: 40, bottom: 20, left: 40 }}>
        <Pie
          data={data}
          dataKey="value"
          nameKey="label"
          innerRadius={compact ? '55%' : '50%'}
          outerRadius={compact ? '90%' : '72%'}
          paddingAngle={2}
          label={compact ? undefined : ({ name, value }) => `${name} ${total ? Math.round((Number(value) / total) * 100) : 0}%`}
          labelLine={!compact}
          isAnimationActive={false}
        >
          {data.map((d, i) => {
            const [fg] = statusColors(d.label, colors)
            return <Cell key={i} fill={fg === colors.info ? BRAND : fg} stroke={colors.surface} strokeWidth={2} />
          })}
        </Pie>
        <Tooltip {...tooltipStyle} formatter={(value) => Number(value).toLocaleString()} />
        {!compact && <Legend wrapperStyle={{ fontSize: 12, color: colors.muted }} />}
      </PieChart>
    </ResponsiveContainer>
  )
}
