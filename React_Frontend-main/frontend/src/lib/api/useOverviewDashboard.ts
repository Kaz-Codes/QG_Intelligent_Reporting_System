import { useQuery } from '@tanstack/react-query'
import { getOverviewDashboard, type OverviewDashboardFilters } from './overviewDashboard'
import { DASHBOARD_QUERY_OPTIONS } from './queryOptions'

export function useOverviewDashboard(filters: OverviewDashboardFilters = {}) {
  return useQuery({
    queryKey: ['overview-dashboard', filters],
    queryFn: () => getOverviewDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}
