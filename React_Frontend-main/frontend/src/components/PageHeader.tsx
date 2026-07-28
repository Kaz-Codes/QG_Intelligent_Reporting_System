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
        <h1 className="font-display text-2xl font-bold text-navy">{title}</h1>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      </div>
    </div>
  )
}
