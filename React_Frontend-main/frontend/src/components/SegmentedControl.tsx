import { cn } from '@/lib/utils'

interface Option<T extends string> {
  value: T
  label: string
}

interface Props<T extends string> {
  options: readonly Option<T>[]
  value: T
  onChange: (value: T) => void
  /** 'solid' for standalone controls (brand-filled active state), 'ghost'
   * for nesting inside a card that already has its own surface, 'onBrand'
   * for sitting directly on a colored/gradient surface (e.g. HeroStat). */
  variant?: 'solid' | 'ghost' | 'onBrand'
}

const CONTAINER = {
  solid: 'border border-line bg-surface',
  ghost: 'bg-canvas-alt',
  onBrand: 'border border-white/20 bg-white/10',
}

const ACTIVE = {
  solid: 'bg-brand text-on-brand',
  ghost: 'bg-surface text-ink shadow-sm',
  onBrand: 'bg-white text-brand shadow-sm',
}

const INACTIVE = {
  solid: 'text-muted hover:text-ink',
  ghost: 'text-muted hover:text-ink',
  onBrand: 'text-white/70 hover:text-white',
}

/** Small pill-group toggle — reused for range pickers, insight tabs, and
 * anywhere else a page needs an instant, no-reload view switch. */
export function SegmentedControl<T extends string>({ options, value, onChange, variant = 'solid' }: Props<T>) {
  return (
    <div className={cn('inline-flex rounded-lg p-0.5', CONTAINER[variant])}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
            value === opt.value ? ACTIVE[variant] : INACTIVE[variant],
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
