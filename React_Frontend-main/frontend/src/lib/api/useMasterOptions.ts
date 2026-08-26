import { useEffect, useState } from 'react'
import type { SearchableOption } from '@/components/ui/SearchableSelect'

/**
 * Load one master list once, for a SearchableSelect to filter in memory.
 *
 * These lists are small and change about as often as the business opens a new
 * branch, so they are fetched whole rather than searched per keystroke — the
 * underlying fetchers in masters.ts cache per tab, so several fields backed by
 * the same master cost one request between them. The item CATALOGUE is the
 * exception and is far too large for this; it has its own search endpoint and
 * uses SearchableSelect's async `loadOptions` instead.
 *
 * Fetched once on mount, matching the pattern the trucking wizard already
 * used for its transporter list.
 */
export function useMasterOptions<T>(fetcher: () => Promise<T[]>) {
  const [rows, setRows] = useState<T[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetcher()
      .then((res) => { if (!cancelled) setRows(res) })
      .catch(() => { if (!cancelled) setRows([]) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
    // Module-level fetchers, called once per mount on purpose.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { rows, loading }
}

/** Master rows -> options. `hint` is the muted second column in the list. */
export function toOptions<T extends { id: number; name: string }>(
  rows: T[],
  hint?: (row: T) => string | undefined,
): SearchableOption<T>[] {
  return rows.map((row) => ({
    value: row.name,
    label: row.name,
    hint: hint?.(row),
    data: row,
  }))
}

/**
 * Is this value one the master actually knows?
 *
 * Empty counts as known — there is nothing to flag about a field nobody has
 * filled in yet, and marking it would put a warning on every blank form.
 * Compared case-insensitively on the trimmed name, the same test
 * `helpers.resolve_customer_id` / `resolve_transporter_id` apply server-side,
 * so the marker and the backend's own linking cannot disagree.
 */
export function isKnownMasterValue(
  rows: { name: string }[],
  value: string | undefined | null,
): boolean {
  const needle = value?.trim().toLowerCase()
  if (!needle) return true
  return rows.some((row) => row.name?.trim().toLowerCase() === needle)
}
