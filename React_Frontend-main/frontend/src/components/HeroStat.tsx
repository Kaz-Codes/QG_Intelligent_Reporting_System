import type { ReactNode } from 'react'
import { ArrowUpRight, ArrowDownRight, type LucideIcon } from 'lucide-react'
import { Card, CardContent } from './ui/card'
import { TrendLine } from './charts/TrendLine'
import { ReferenceList, type ReferenceSet, type ReferencePager } from './ReferenceList'
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
  /** Unit for the trend chart's value axis — "PKR (millions)", "Orders". */
  trendUnit?: string
  /** The records this headline totals, listed on demand. The hero is a KPI
   * like any other, so it drills the same way the tiles under it do. */
  refs?: ReferenceSet
  /** Fetches further pages of `refs`. */
  fetchRefs?: ReferencePager
}

/** The page's headline KPI merged with its own trend chart into one glass
 * panel instead of two separate cards — same treatment as every other
 * card (see ui/card.tsx), so it sits quietly over a module's photo
 * backdrop instead of competing with it as its own solid gradient block. */
export function HeroStat({
  label, value, delta, direction = 'up', trendData, trendX, trendY, caption,
  trendHeight = 200, header, trendUnit, refs, fetchRefs,
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
            <div className="flex items-center gap-1">
              <p className="text-sm font-medium text-muted">{label}</p>
              <ReferenceList label={label} refs={refs} fetchPage={fetchRefs} />
            </div>
            <p className="font-display mt-1 text-5xl font-extrabold tracking-tight text-navy">{value}</p>
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
          {/* The decorative glyph that used to sit here is gone. It was pure
              ornament in the top-right of a chart card — it carried no
              information, and on a screen whose whole point is that every mark
              means something, a symbol that means nothing is noise. */}
        </div>
        <div className="mt-2">
          <TrendLine data={trendData} x={trendX} y={trendY} height={trendHeight} unit={trendUnit} />
        </div>
        {caption && <p className="mt-1 text-xs text-muted">{caption}</p>}
      </CardContent>
    </Card>
  )
}
