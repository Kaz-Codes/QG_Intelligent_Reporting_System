import type { ReactNode } from 'react'
import { ArrowUpRight, ArrowDownRight, Sparkles, type LucideIcon } from 'lucide-react'
import { Card, CardContent } from './ui/card'
import { TrendLine } from './charts/TrendLine'
import { useTheme } from '@/theme/ThemeContext'

interface Props {
  label: string
  value: string
  delta?: string
  direction?: 'up' | 'down' | null
  icon?: LucideIcon
  trendData: Record<string, unknown>[]
  trendX: string
  trendY: string
  caption?: string
  trendHeight?: number
  /** Optional content (greeting, status pill, view controls, ...) rendered
   * above the stat itself, inside the same panel, separated by a hairline
   * divider — for folding a page's whole header into its hero instead of
   * stacking a plain bar on top of it. */
  header?: ReactNode
}

/** The page's headline KPI merged with its own trend chart into one glass
 * panel instead of two separate cards — same treatment as every other
 * card (see ui/card.tsx), so it sits quietly over a module's photo
 * backdrop instead of competing with it as its own solid gradient block. */
export function HeroStat({
  label, value, delta, direction = 'up', icon: Icon = Sparkles, trendData, trendX, trendY, caption,
  trendHeight = 200, header,
}: Props) {
  const { colors } = useTheme()
  const DeltaIcon = direction === 'down' ? ArrowDownRight : ArrowUpRight
  const deltaColor = direction === 'down' ? colors.risk : colors.healthy
  const deltaBg = direction === 'down' ? colors.riskBg : colors.healthyBg

  return (
    <Card className="relative overflow-hidden">
      <CardContent className="relative p-6 lg:p-8">
        {header && (
          <>
            {header}
            <div className="my-6 h-px bg-line" />
          </>
        )}
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-muted">{label}</p>
            <p className="font-display mt-1 text-4xl font-extrabold tracking-tight text-navy">{value}</p>
            {delta && (
              <span
                className="mt-3 inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold"
                style={{ backgroundColor: deltaBg, color: deltaColor }}
              >
                <DeltaIcon size={12} />
                {delta}
              </span>
            )}
          </div>
          {!header && (
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
              <Icon size={20} />
            </span>
          )}
        </div>
        <div className="mt-2">
          <TrendLine data={trendData} x={trendX} y={trendY} height={trendHeight} />
        </div>
        {caption && <p className="mt-1 text-xs text-muted">{caption}</p>}
      </CardContent>
    </Card>
  )
}
