import { Label } from '@/components/ui/label'

interface Props {
  label: string
  from: string
  to: string
  onFromChange: (value: string) => void
  onToChange: (value: string) => void
}

/** Month/year range picker — the date-based sibling of MultiSelectFilter,
 * used for the "PO Date", "ETA", "Execution Date" style primary filters.
 * Empty string on either end means "unbounded" on that side. */
export function DateRangeFilter({ label, from, to, onFromChange, onToChange }: Props) {
  return (
    <div className="flex w-full min-w-[160px] flex-col gap-1.5 sm:w-auto">
      <Label>{label}</Label>
      <div className="flex h-10 items-center gap-1.5">
        <input
          type="month"
          value={from}
          onChange={(e) => onFromChange(e.target.value)}
          className="h-10 w-[132px] rounded-lg border border-line bg-surface px-2.5 text-sm text-ink transition-colors duration-150 hover:border-brand-light focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
        />
        <span className="shrink-0 text-xs text-muted">to</span>
        <input
          type="month"
          value={to}
          onChange={(e) => onToChange(e.target.value)}
          className="h-10 w-[132px] rounded-lg border border-line bg-surface px-2.5 text-sm text-ink transition-colors duration-150 hover:border-brand-light focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
        />
      </div>
    </div>
  )
}
