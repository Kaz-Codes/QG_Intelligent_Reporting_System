import type { PageKey } from '@/theme/tokens'
import { MODULE_ACCENTS } from '@/theme/tokens'

export function PageHeader({
  title,
  subtitle,
  module,
}: {
  title: string
  subtitle?: string
  module: PageKey
}) {
  const accent = MODULE_ACCENTS[module]
  return (
    <div className="mb-6 flex items-center gap-3">
      <span className="h-8 w-1.5 rounded-full" style={{ backgroundColor: accent }} />
      <div>
        <h1
          className="font-display text-3xl font-extrabold text-navy"
          style={{ textShadow: '0 1px 3px rgba(0,0,0,0.18)' }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            className="text-sm font-semibold text-muted"
            style={{ textShadow: '0 1px 2px rgba(0,0,0,0.14)' }}
          >
            {subtitle}
          </p>
        )}
      </div>
    </div>
  )
}
