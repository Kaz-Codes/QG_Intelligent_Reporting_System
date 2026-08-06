/**
 * Formatting for the Imports Status sheet.
 *
 * The shared money() in lib/format.ts abbreviates to "PKR 5.2M", which is right
 * for a dashboard headline but wrong here — a status sheet is reconciled against
 * invoices, so figures must be exact. These live in the feature so they don't
 * change the dashboard's behaviour.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Exact, grouped, no decimals — "PKR 5,191,830". */
export const pkr = (v: number) => `PKR ${Math.round(v).toLocaleString('en-US')}`

/** Foreign currency with its code — "USD 18,450.00". Falls back to no code
 *  if currency hasn't been picked yet, rather than forcing every call site
 *  to coerce — currency is optional until Step 1 is filled in. */
export const fx = (v: number, code: string | undefined) =>
  `${code ?? ''} ${v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`.trim()

/** Plain grouped number — quantities, day counts. */
export const num = (v: number) => v.toLocaleString('en-US')

/** "24 Jul 26" — compact, unambiguous, sortable-looking. */
export function dateShort(input?: string | null): string {
  if (!input) return '—'
  const d = new Date(input)
  if (Number.isNaN(+d)) return '—'
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`
}

/** "+12 d" / "on time" for slippage-style deltas. */
export const days = (n: number | null) =>
  n === null ? '—' : n <= 0 ? 'on time' : `+${n} d`

/** Ordinal for ETA history strings — 1st, 2nd, 3rd. */
export function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

/** "1st ETA 12 Jul 26 → 2nd ETA 19 Jul 26 → 3rd ETA 24 Jul 26" */
export function etaChain(history: string[], current: string | null | undefined): string {
  const all = [...history, ...(current ? [current] : [])]
  return all.map((d, i) => `${ordinal(i + 1)} ETA ${dateShort(d)}`).join(' → ')
}
