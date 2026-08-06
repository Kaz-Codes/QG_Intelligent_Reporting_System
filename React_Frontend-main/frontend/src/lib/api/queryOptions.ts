import { keepPreviousData } from '@tanstack/react-query'

/**
 * Shared react-query settings for the live dashboard endpoints.
 *
 * These endpoints are expensive — /dashboard/purchases still measures 2-4s
 * regardless of the filter applied, because it loads the whole table on every
 * request to build its dropdown lists. That cost is server-side and can't be
 * fixed here, so the frontend's job is to stop paying it more often than
 * necessary:
 *
 *  - staleTime keeps a loaded dashboard fresh for a minute, so moving between
 *    the Purchases / Inventory / Imports tabs replays the cache instead of
 *    refiring a multi-second request per switch. This is what made tab
 *    switching feel like it hung.
 *  - gcTime keeps that cache alive well past the stale window, so a tab you
 *    come back to later is still warm rather than starting from nothing.
 *  - keepPreviousData leaves the previous result on screen while a new filter
 *    loads, so changing a filter updates the numbers in place instead of
 *    blanking every KPI and chart to a loading card for a second and a half.
 */
export const DASHBOARD_QUERY_OPTIONS = {
  staleTime: 60_000,
  gcTime: 5 * 60_000,
  placeholderData: keepPreviousData,
  retry: false,
} as const
