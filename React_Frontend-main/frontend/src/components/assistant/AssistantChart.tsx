import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useTheme } from '@/theme/ThemeContext'
import { CHART_SEQUENCE, VIOLET } from '@/theme/tokens'
import { compactNumber } from '@/components/charts/utils'
import type { ChartSpec } from '@/lib/chatbot/types'

// Renders whatever chart spec the assistant asked for ({type, x, y[], title})
// against the same rows shown in the table below it. Unlike the app's
// dashboard charts (TrendLine, RankedBar, ...), which are each built for one
// fixed data shape, an assistant answer's shape is only known at reply time —
// so this stays a single generic renderer, same role as the original
// chatbot's ChartView.jsx, but drawing from this app's own theme tokens
// (CHART_SEQUENCE, useTheme) so it matches every other chart in light/dark.

const num = (v: unknown): number => {
  const n = typeof v === 'number' ? v : Number(v)
  return Number.isFinite(n) ? n : 0
}

interface Props {
  spec: ChartSpec
  rows: Record<string, unknown>[]
}

export function AssistantChart({ spec, rows }: Props) {
  const { colors } = useTheme()
  if (!spec?.type || spec.type === 'none') return null
  const { type, x, y = [], title } = spec
  const data = Array.isArray(spec.data) && spec.data.length ? spec.data : rows
  if (!x || !y.length || !data?.length) return null

  const showLegend = y.length > 1
  const tooltipStyle = {
    background: colors.surface,
    border: `1px solid ${colors.line}`,
    borderRadius: 8,
    fontSize: '0.8rem',
    color: colors.ink,
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      {title && <p className="mb-2 text-sm font-semibold text-ink">{title}</p>}
      <ResponsiveContainer width="100%" height={280}>
        {type === 'pie' ? (
          (() => {
            const pieData = data.map((r) => ({ name: String(r[x]), value: num(r[y[0]]) }))
            const pieTotal = pieData.reduce((sum, d) => sum + d.value, 0)
            // A slice's own name label only fits when the wedge is big enough
            // to draw it against without colliding with its neighbours - with
            // many small categories (an 11-way status breakdown, say) inline
            // labels overlap into an unreadable knot. The legend below (always
            // shown for pie, not just multi-series) plus the tooltip on hover
            // covers every slice regardless of size.
            const labelMinShare = 0.08
            return (
              <PieChart>
                <Tooltip contentStyle={tooltipStyle} formatter={(v: unknown) => compactNumber(Number(v))} />
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="46%"
                  outerRadius={85}
                  label={(d: { name?: string; value?: number }) =>
                    pieTotal > 0 && (d.value ?? 0) / pieTotal >= labelMinShare ? (d.name ?? '') : ''
                  }
                  labelLine={false}
                  stroke={colors.surface}
                  strokeWidth={2}
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={CHART_SEQUENCE[i % CHART_SEQUENCE.length]} />
                  ))}
                </Pie>
                <Legend wrapperStyle={{ fontSize: 11, color: colors.muted }} />
              </PieChart>
            )
          })()
        ) : type === 'line' ? (
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={colors.line} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={x} tick={{ fill: colors.muted, fontSize: 11 }} stroke={colors.line} />
            <YAxis
              tickFormatter={compactNumber}
              tick={{ fill: colors.muted, fontSize: 11 }}
              stroke={colors.line}
              width={52}
            />
            <Tooltip contentStyle={tooltipStyle} formatter={(v: unknown) => compactNumber(Number(v))} />
            {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: colors.muted }} />}
            {y.map((key, i) => {
              // A 'forecast' series (projected points) reads as a dashed
              // continuation, visually distinct from actual history.
              const isForecast = key === 'forecast'
              return (
                <Line
                  key={key}
                  type="monotone"
                  dataKey={key}
                  stroke={isForecast ? VIOLET : CHART_SEQUENCE[i % CHART_SEQUENCE.length]}
                  strokeWidth={2}
                  strokeDasharray={isForecast ? '6 4' : undefined}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  connectNulls={false}
                />
              )
            })}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={colors.line} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey={x} tick={{ fill: colors.muted, fontSize: 11 }} stroke={colors.line} />
            <YAxis
              tickFormatter={compactNumber}
              tick={{ fill: colors.muted, fontSize: 11 }}
              stroke={colors.line}
              width={52}
            />
            <Tooltip
              contentStyle={tooltipStyle}
              formatter={(v: unknown) => compactNumber(Number(v))}
              cursor={{ fill: colors.canvasAlt }}
            />
            {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: colors.muted }} />}
            {y.map((key, i) => (
              <Bar
                key={key}
                dataKey={key}
                fill={CHART_SEQUENCE[i % CHART_SEQUENCE.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  )
}
