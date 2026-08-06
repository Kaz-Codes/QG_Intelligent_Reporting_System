import type { ReactNode } from 'react'
import { Card, CardContent } from './ui/card'

/** Plain titled card for a single chart — the non-tabbed sibling of
 * InsightsCard, for when a page has just one view of the data. */
export function ChartCard({ title, children, className }: { title: string; children: ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <CardContent className="p-5">
        <p className="mb-4 text-sm font-semibold text-ink">{title}</p>
        {children}
      </CardContent>
    </Card>
  )
}
