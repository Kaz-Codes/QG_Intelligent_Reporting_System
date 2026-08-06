import type { ReactNode } from 'react'
import { Card, CardContent } from './ui/card'
import { SegmentedControl } from './SegmentedControl'

interface Props<T extends string> {
  title: string
  tabs: readonly { value: T; label: string }[]
  active: T
  onChange: (value: T) => void
  children: ReactNode
  className?: string
}

/** A card with a tab switcher in its header — the reusable "one card, many
 * charts" pattern (Dashboard's Insights card was the first use). Swapping
 * tabs is instant client-side state, not a page rerun. */
export function InsightsCard<T extends string>({ title, tabs, active, onChange, children, className }: Props<T>) {
  return (
    <Card className={className}>
      <CardContent className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <p className="text-sm font-semibold text-ink">{title}</p>
          <SegmentedControl options={tabs} value={active} onChange={onChange} variant="ghost" />
        </div>
        <div key={active} className="animate-fade-in-up">
          {children}
        </div>
      </CardContent>
    </Card>
  )
}
