import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { statusColors, CHART_SEQUENCE } from '@/theme/tokens'
import { tooltipStyle } from './utils'

interface Props {
  labels: string[]
  values: number[]
  height?: number
  /** For narrow containers (e.g. a spotlight card's side panel) — smaller
   * ring and no outside labels/legend, which would clip against the container
   * edge. The percentage still shows, drawn INSIDE each slice. */
  compact?: boolean
}

/**
 * Donut for composition (status split, stock health, stock movement).
 *
 * Colour: status-like labels ("Delayed", "Out of Stock") keep their semantic
 * risk/watch/healthy colour so they read the same as everywhere else. Anything
 * NOT a recognised status falls back to the categorical palette BY INDEX —
 * previously they all collapsed onto one brand colour, which made a
 * three-slice donut (fast / slow / dead) a single flat ring you could not read
 * without the tooltip.
 *
 * Percentage: always shown. Outside the ring with the label when there is
 * room, inside the slice when compact. A composition chart whose whole job is
 * showing proportion should not make you hover to learn the proportion.
 */
export function Donut({ labels, values, height = 300, compact = false }: Props) {
  const { colors } = useTheme()
  const data = labels.map((label, i) => ({ label, value: values[i] }))
  const total = values.reduce((a, b) => a + b, 0)

  const pct = (value: number) => (total ? Math.round((value / total) * 100) : 0)

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
          // Compact draws the bare percentage inside the slice, so nothing can
          // clip; the full chart puts the name beside it outside the ring.
          label={
            compact
              ? ({ value }) => (pct(Number(value)) >= 6 ? `${pct(Number(value))}%` : '')
              : ({ name, value }) => `${name} ${pct(Number(value))}%`
          }
          labelLine={!compact}
          isAnimationActive={false}
        >
          {data.map((d, i) => {
            const [fg] = statusColors(d.label, colors)
            // statusColors returns `info` for anything it does not recognise;
            // those get a distinct categorical hue instead of all sharing one.
            const fill = fg === colors.info ? CHART_SEQUENCE[i % CHART_SEQUENCE.length] : fg
            return <Cell key={i} fill={fill} stroke={colors.surface} strokeWidth={2} />
          })}
        </Pie>
        <Tooltip
          {...tooltipStyle}
          formatter={(value) => `${Number(value).toLocaleString()} (${pct(Number(value))}%)`}
        />
        {!compact && <Legend wrapperStyle={{ fontSize: 12, color: colors.muted }} />}
      </PieChart>
    </ResponsiveContainer>
  )
}
