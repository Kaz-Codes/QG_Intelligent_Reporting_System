import { apiFetch } from './client'
import type { ReferenceSet, ReferencePager } from '@/components/ReferenceList'

/**
 * Paging for the record lists behind a KPI.
 *
 * Each dashboard payload carries page one of every reference list plus the true
 * total; these fetch the rest from `/dashboard/<module>/references`. The filters
 * must be the SAME ones the dashboard was rendered with, or page 2 describes a
 * different set from page 1 — so every helper takes the query the screen
 * already holds and adds only `key` and `page`.
 *
 * `key` names which list. The backend matches it against a fixed registry, so a
 * typo is a 400 rather than a silently empty panel.
 */

type Query = Record<string, string | number | boolean | string[] | undefined | null>

function toParams(query: Query): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) {
      for (const v of value) params.append(key, v)
    } else {
      params.set(key, String(value))
    }
  }
  return params
}

function pagerFor(path: string) {
  /** Build a pager bound to one list and one set of filters. */
  return (key: string, query: Query = {}): ReferencePager => async (page: number) => {
    const params = toParams({ ...query, key, page })
    const { data } = await apiFetch<{ data: ReferenceSet }>(`${path}?${params.toString()}`)
    return data
  }
}

export const overviewRefPager = pagerFor('/dashboard/overview/references')
export const importsRefPager = pagerFor('/dashboard/imports/references')
export const purchasesRefPager = pagerFor('/dashboard/purchases/references')
export const inventoryRefPager = pagerFor('/dashboard/inventory/references')

/**
 * Logistics is three tabs against three different sources, so its pager takes
 * a `tab` in the query and the endpoint routes on it — one endpoint rather
 * than three near-identical ones, and one place where the tab's filters and
 * its reference keys have to agree.
 */
export const logisticsRefPager = pagerFor('/dashboard/logistics/references')
