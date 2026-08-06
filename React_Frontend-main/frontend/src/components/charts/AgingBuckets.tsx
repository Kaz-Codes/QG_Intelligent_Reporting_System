import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { BRAND } from '@/theme/tokens'
import { tooltipStyle, compactNumber, axisLabel } from './utils'

const ORDER = ['0-30 days', '31-60 days', '61-90 days', '90+ days']

interface Props {
  data: { bucket: string; orders: number }[]
  height?: number
  /** What the bars count — defaults to "Orders", which is what every current
   * caller is bucketing. */
  unit?: string
}

/** Aging analysis — buckets colored by severity (green -> red). */
export function AgingBuckets({ data, height = 300, unit = 'Orders' }: Props) {
  const { colors } = useTheme()
  const severity: Record<string, string> = {
    '0-30 days': colors.healthy,
    '31-60 days': colors.watch,
    '61-90 days': '#D98800',
    '90+ days': colors.risk,
  }
  const ordered = ORDER.map((bucket) => data.find((d) => d.bucket === bucket) ?? { bucket, orders: 0 })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={ordered} margin={{ top: 10, right: 10, left: unit ? 12 : 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={colors.line} />
        <XAxis dataKey="bucket" tick={{ fill: colors.muted, fontSize: 11 }} axisLine={{ stroke: colors.line }} tickLine={false} />
        <YAxis
          tick={{ fill: colors.muted, fontSize: 12 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={compactNumber}
          label={axisLabel(unit, 'y', colors.muted)}
        />
        <Tooltip {...tooltipStyle} />
        <Bar dataKey="orders" radius={[4, 4, 0, 0]} isAnimationActive={false}>
          {ordered.map((d, i) => (
            <Cell key={i} fill={severity[d.bucket] ?? BRAND} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
