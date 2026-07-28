import {
  Gauge, ShoppingCart, PackageOpen, Plane, ClipboardList, Truck, BarChart3, MessageSquare, Users,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { pagesForRole } from './roleAccess'

export interface PageDef {
  key: PageKey
  label: string
  path: string
  icon: LucideIcon
  /** Sub-links rendered under this item instead of it being a direct link
   * itself — used for Operations, which groups two independent route trees
   * (Imports Status, Logistics Status) behind one sidebar entry. */
  children?: { label: string; path: string }[]
}

// Single source of truth for the sidebar/routes — mirrors the old
// Streamlit `PAGES` dict in app.py: to reorder/rename a tab, edit here only.
export const PAGE_DEFS: PageDef[] = [
  { key: 'dashboard', label: 'Dashboard', path: '/dashboard', icon: Gauge },
  { key: 'purchases', label: 'Purchases', path: '/purchases', icon: ShoppingCart },
  { key: 'inventory', label: 'Inventory', path: '/inventory', icon: PackageOpen },
  { key: 'imports', label: 'Imports', path: '/imports', icon: Plane },
  { key: 'logistics', label: 'Logistics', path: '/logistics', icon: Truck },
  { key: 'reports', label: 'Reports', path: '/reports', icon: BarChart3 },
  { key: 'assistant', label: 'Assistant', path: '/assistant', icon: MessageSquare },
  // Kept separate from the reporting pages above (its own section in the
  // sidebar, not interleaved between them) — a different kind of work.
  {
    key: 'dataEntry', label: 'Operations', path: '/imports-status', icon: ClipboardList,
    children: [
      { label: 'Imports Status', path: '/imports-status' },
      { label: 'Logistics Status', path: '/logistics-status' },
    ],
  },
  { key: 'userManagement', label: 'User Management', path: '/user-management', icon: Users },
]

/** Where to land a given role right after login (or when they're bounced
 * off a page they can't access) — the first page in PAGE_DEFS order that
 * their role is allowed to see. */
export function defaultPathForRole(role: string | undefined): string {
  const allowed = pagesForRole(role)
  const first = PAGE_DEFS.find((p) => allowed.includes(p.key))
  return first?.path ?? '/login'
}
