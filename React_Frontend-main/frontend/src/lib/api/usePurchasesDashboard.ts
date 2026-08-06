import { useQuery } from '@tanstack/react-query'
import { getPurchasesDashboard, type PurchasesDashboardFilters } from './purchasesDashboard'
import { DASHBOARD_QUERY_OPTIONS } from './queryOptions'

export function usePurchasesDashboard(filters: PurchasesDashboardFilters = {}) {
  return useQuery({
    queryKey: ['purchases-dashboard', filters],
    queryFn: () => getPurchasesDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}
