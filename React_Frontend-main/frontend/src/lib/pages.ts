import {
  Gauge, ShoppingCart, PackageOpen, Plane, ClipboardList, Truck, BarChart3, MessageSquare,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'

export interface PageDef {
  key: PageKey
  label: string
  path: string
  icon: LucideIcon
}

// Single source of truth for the sidebar/routes — mirrors the old
// Streamlit `PAGES` dict in app.py: to reorder/rename a tab, edit here only.
export const PAGE_DEFS: PageDef[] = [
  { key: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: Gauge },
  { key: 'purchases', label: 'Purchases', path: '/purchases', icon: ShoppingCart },
  { key: 'inventory', label: 'Inventory', path: '/inventory', icon: PackageOpen },
  { key: 'imports', label: 'Imports', path: '/imports', icon: Plane },
  { key: 'importsStatus', label: 'Imports Status', path: '/imports-status', icon: ClipboardList },
  { key: 'logisticsStatus', label: 'Logistics Status', path: '/logistics-status', icon: Truck },
  { key: 'logistics', label: 'Logistics', path: '/logistics', icon: Truck },
  { key: 'reports', label: 'Reports', path: '/reports', icon: BarChart3 },
  { key: 'assistant', label: 'Assistant', path: '/assistant', icon: MessageSquare },
]
