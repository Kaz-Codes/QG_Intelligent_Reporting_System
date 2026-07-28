import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'

/** Collapsible section — same role as Streamlit's st.expander(). */
export function Disclosure({ title, children, defaultOpen = false }: {
  title: string
  children: ReactNode
  defaultOpen?: boolean
}) {
  return (
    <details className="group rounded-xl border border-line bg-surface open:pb-4" open={defaultOpen}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-ink">
        <ChevronRight size={16} className="text-muted transition-transform group-open:rotate-90" />
        {title}
      </summary>
      <div className="px-4">{children}</div>
    </details>
  )
}
