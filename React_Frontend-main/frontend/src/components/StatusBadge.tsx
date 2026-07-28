import { useTheme } from '@/theme/ThemeContext'
import { statusColors } from '@/theme/tokens'

export function StatusBadge({ label }: { label: string }) {
  const { colors } = useTheme()
  const [fg, bg] = statusColors(label, colors)
  return (
    <span
      className="rounded-full px-2.5 py-1 text-xs font-semibold"
      style={{ color: fg, backgroundColor: bg }}
    >
      {label}
    </span>
  )
}
