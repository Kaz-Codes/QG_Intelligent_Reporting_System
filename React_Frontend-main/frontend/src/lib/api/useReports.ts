import { useQuery } from '@tanstack/react-query'
import { getReportOptions, getReportData, getSavedReports, type ReportFilters, type ReportType } from './reports'
import { DASHBOARD_QUERY_OPTIONS } from './queryOptions'

export function useReportOptions(types: ReportType[], enabled = true) {
  return useQuery({
    queryKey: ['report-options', types],
    queryFn: () => getReportOptions(types),
    enabled,
    ...DASHBOARD_QUERY_OPTIONS,
  })
}

// `types` empty means "nothing picked yet" on the front end, but an empty/
// absent `types` list means "all four" to the backend — enabled must be false
// here (not just an empty `types` filter) or an empty selection would
// silently fetch everything instead of showing the "pick a type" empty state.
export function useReportData(filters: ReportFilters, page: number, pageSize: number, enabled = true) {
  return useQuery({
    queryKey: ['report-data', filters, page, pageSize],
    queryFn: () => getReportData(filters, page, pageSize),
    enabled,
    ...DASHBOARD_QUERY_OPTIONS,
  })
}

export function useSavedReports() {
  return useQuery({
    queryKey: ['saved-reports'],
    queryFn: () => getSavedReports(),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}
