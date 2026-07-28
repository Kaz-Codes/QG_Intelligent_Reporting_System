import type { ReactNode } from 'react'
import { Search } from 'lucide-react'
import { Card, CardContent } from './ui/card'

interface Props {
  children: ReactNode
  search?: {
    value: string
    onChange: (value: string) => void
    placeholder?: string
  }
}

/** Card-wrapped row of filter controls (MultiSelectFilter children) with an
 * optional search box pinned to the right — the reusable filter header for
 * any data page (Purchases, Inventory, Imports, Logistics...). */
export function FilterBar({ children, search }: Props) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-end gap-4 p-4">
        {children}
        {search && (
          <div className="ml-auto min-w-[220px] flex-1">
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                value={search.value}
                onChange={(e) => search.onChange(e.target.value)}
                placeholder={search.placeholder ?? 'Search…'}
                className="h-10 w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-sm text-ink placeholder:text-muted"
              />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
