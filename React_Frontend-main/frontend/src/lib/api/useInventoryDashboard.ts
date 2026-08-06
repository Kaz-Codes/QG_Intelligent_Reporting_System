import { useQuery } from '@tanstack/react-query'
import { getInventoryDashboard, type InventoryDashboardFilters } from './inventoryDashboard'
import { DASHBOARD_QUERY_OPTIONS } from './queryOptions'

export function useInventoryDashboard(filters: InventoryDashboardFilters = {}) {
  return useQuery({
    queryKey: ['inventory-dashboard', filters],
    queryFn: () => getInventoryDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}
