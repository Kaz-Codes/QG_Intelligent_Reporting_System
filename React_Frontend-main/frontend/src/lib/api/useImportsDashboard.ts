import { useQuery } from '@tanstack/react-query'
import { getImportsDashboard, type ImportsDashboardFilters } from './importsDashboard'
import { DASHBOARD_QUERY_OPTIONS } from './queryOptions'

export function useImportsDashboard(filters: ImportsDashboardFilters = {}) {
  return useQuery({
    queryKey: ['imports-dashboard', filters],
    queryFn: () => getImportsDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}
