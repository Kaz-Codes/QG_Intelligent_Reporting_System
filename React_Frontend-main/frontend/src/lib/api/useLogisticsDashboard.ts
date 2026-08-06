import { useQuery } from '@tanstack/react-query'
import { DASHBOARD_QUERY_OPTIONS } from './queryOptions'
import {
  getShipmentsDashboard, getPackingDashboard, getTransportDashboard,
  type ShipmentsFilters, type PackingFilters, type TransportFilters,
} from './logisticsDashboard'

export function useShipmentsDashboard(filters: ShipmentsFilters = {}) {
  return useQuery({
    queryKey: ['logistics-shipments', filters],
    queryFn: () => getShipmentsDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}

export function usePackingDashboard(filters: PackingFilters = {}) {
  return useQuery({
    queryKey: ['logistics-packing', filters],
    queryFn: () => getPackingDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}

export function useTransportDashboard(filters: TransportFilters = {}) {
  return useQuery({
    queryKey: ['logistics-transport', filters],
    queryFn: () => getTransportDashboard(filters),
    ...DASHBOARD_QUERY_OPTIONS,
  })
}
