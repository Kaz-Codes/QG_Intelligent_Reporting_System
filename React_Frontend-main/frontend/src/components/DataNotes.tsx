import { AlertTriangle, Info, OctagonAlert } from 'lucide-react'
import { useTheme } from '@/theme/ThemeContext'

/**
 * What the data cannot support, said beside the figures that depend on it.
 *
 * Several numbers on these screens rest on partly-filled columns — only 13.8%
 * of logistics orders carry an ETD. A figure derived from a seventh of the rows
 * looks identical to one derived from all of them, so each section states its
 * own coverage rather than leaving the reader to assume.
 *
 * Full coverage produces no note at all: a warning on every figure is noise,
 * and noise is what stops people reading the warnings that matter.
 */

export interface DataNote {
  severity: 'info' | 'warning' | 'severe'
  message: string
  covered: number | null
  total: number | null
  pct: number | null
}

export function DataNotes({ notes, className = '' }: { notes: DataNote[]; className?: string }) {
  const { colors } = useTheme()
  if (!notes?.length) return null

  const style = (severity: DataNote['severity']) =>
    severity === 'severe'
      ? { fg: colors.risk, bg: colors.riskBg, Icon: OctagonAlert }
      : severity === 'warning'
        ? { fg: colors.watch, bg: colors.watchBg, Icon: AlertTriangle }
        : { fg: colors.muted, bg: colors.canvasAlt, Icon: Info }

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      {notes.map((n, i) => {
        const { fg, bg, Icon } = style(n.severity)
        return (
          <div
            key={i}
            className="flex items-start gap-2 rounded-lg px-2.5 py-1.5 text-xs leading-relaxed"
            style={{ backgroundColor: bg, color: fg }}
          >
            <Icon size={13} className="mt-0.5 shrink-0" />
            <span>{n.message}</span>
          </div>
        )
      })}
    </div>
  )
}

/** The worst severity in a set — for a compact indicator on a KPI tile. */
export function worstSeverity(notes?: DataNote[]): DataNote['severity'] | null {
  if (!notes?.length) return null
  if (notes.some((n) => n.severity === 'severe')) return 'severe'
  if (notes.some((n) => n.severity === 'warning')) return 'warning'
  return 'info'
}
