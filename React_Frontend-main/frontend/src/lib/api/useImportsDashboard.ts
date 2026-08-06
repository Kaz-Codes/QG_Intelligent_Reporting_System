import { useQuery } from '@tanstack/react-query'
import { getImportsDashboard, type ImportsDashboardFilters } from './importsDashboard'

export function useImportsDashboard(filters: ImportsDashboardFilters = {}) {
  return useQuery({
    queryKey: ['imports-dashboard', filters],
    queryFn: () => getImportsDashboard(filters),
    retry: false,
  })
}
