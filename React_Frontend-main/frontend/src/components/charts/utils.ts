function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** Linear-interpolate between two hex colors — used for the "magnitude"
 * gradient bars (light -> deep brand), same effect as Plotly's colorscale. */
export function lerpColor(hexA: string, hexB: string, t: number): string {
  const [ar, ag, ab] = hexToRgb(hexA)
  const [br, bg, bb] = hexToRgb(hexB)
  const r = Math.round(ar + (br - ar) * t)
  const g = Math.round(ag + (bg - ag) * t)
  const b = Math.round(ab + (bb - ab) * t)
  return `rgb(${r}, ${g}, ${b})`
}

/**
 * Compact tick label for a numeric axis — 118287551 becomes "118M".
 *
 * Mock data topped out in the thousands, so raw ticks fit. Real PKR figures
 * run to nine digits, which overflow the axis gutter and get clipped down to
 * their trailing zeros — a column of "0000000" where the scale should be.
 * The tooltip still shows the exact value.
 */
export function compactNumber(value: number): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}${trim(abs / 1e9)}B`
  if (abs >= 1e6) return `${sign}${trim(abs / 1e6)}M`
  if (abs >= 1e3) return `${sign}${trim(abs / 1e3)}K`
  return `${sign}${trim(abs)}`
}

/** One decimal only when it adds information: 1.5M stays, 118.0M becomes 118M. */
function trim(n: number): string {
  return (Math.round(n * 10) / 10).toString()
}

/** Axis unit caption ("PKR", "Orders", "Days"…). Recharts needs the label as
 * an object; this keeps every chart's styling identical in one place. */
export function axisLabel(unit: string | undefined, axis: 'x' | 'y', color: string) {
  if (!unit) return undefined
  return {
    value: unit,
    position: axis === 'y' ? ('insideLeft' as const) : ('insideBottom' as const),
    angle: axis === 'y' ? -90 : 0,
    offset: axis === 'y' ? 0 : -4,
    style: { fill: color, fontSize: 11, fontWeight: 600, textAnchor: 'middle' as const },
  }
}

export const tooltipStyle = {
  contentStyle: {
    background: '#3730A3',
    border: 'none',
    borderRadius: 8,
    color: '#fff',
    fontSize: 12,
  },
  labelStyle: { color: '#fff', fontWeight: 600 },
  itemStyle: { color: '#fff' },
}
