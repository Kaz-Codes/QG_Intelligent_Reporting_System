import { Label } from '@/components/ui/label'

interface Props {
  label: string
  options: string[]
  value: string
  onChange: (value: string) => void
}

/** Single-value dropdown — the sibling of MultiSelectFilter for filters a
 * backend endpoint only accepts one value of at a time (a plain `?work=`
 * style query param, not an array). Empty string means "no filter", shown
 * as the "All" option. */
export function SingleSelectFilter({ label, options, value, onChange }: Props) {
  return (
    <div className="flex w-full min-w-[160px] flex-col gap-1.5 sm:w-48">
      <Label>{label}</Label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 w-full rounded-lg border border-line bg-surface px-2.5 text-sm text-ink transition-colors duration-150 hover:border-brand-light focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20"
      >
        <option value="">All</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  )
}
