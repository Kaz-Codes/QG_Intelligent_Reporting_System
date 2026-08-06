import { Check } from 'lucide-react'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

interface Option {
  key: string
  label: string
}

interface Props {
  label: string
  options: Option[]
  value: string[]
  onChange: (value: string[]) => void
}

/** Header/column checklist for the Reports builder — shown as chips you
 * toggle directly (not tucked behind a dropdown like MultiSelectFilter),
 * since the whole point is to let the user see every available header from
 * the data types they picked before deciding which ones to keep. */
export function ColumnPicker({ label, options, value, onChange }: Props) {
  function toggle(key: string) {
    onChange(value.includes(key) ? value.filter((v) => v !== key) : [...value, key])
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <Label>{label}</Label>
        <div className="flex gap-3 text-xs font-medium">
          <button type="button" onClick={() => onChange(options.map((o) => o.key))} className="text-brand hover:underline">
            Select all
          </button>
          <button type="button" onClick={() => onChange([])} className="text-muted hover:underline">
            Clear
          </button>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const active = value.includes(opt.key)
          return (
            <button
              key={opt.key}
              type="button"
              onClick={() => toggle(opt.key)}
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors duration-150',
                active
                  ? 'border-brand/30 bg-brand-soft text-brand'
                  : 'border-line text-muted hover:border-brand-light hover:text-ink',
              )}
            >
              {active && <Check size={12} />}
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
