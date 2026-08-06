import {
  Gauge, ClipboardList, BarChart3, MessageSquare, Users,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { pagesForUser, type Access } from './roleAccess'

export interface PageDef {
  key: PageKey
  label: string
  path: string
  icon: LucideIcon
  /** Sub-links rendered under this item instead of it being a direct link
   * itself — used for Operations, which groups three independent route trees
   * (Imports Status, Logistics Status, Trucking Status) behind one sidebar
   * entry. */
  children?: { label: string; path: string }[]
}

// Single source of truth for the sidebar/routes — mirrors the old
// Streamlit `PAGES` dict in app.py: to reorder/rename a tab, edit here only.
// Purchases/Inventory/Imports/Logistics aren't separate entries — they live
// as tabs inside Dashboard (see Dashboard.tsx's own tab bar).
export const PAGE_DEFS: PageDef[] = [
  { key: 'assistant', label: 'Assistant', path: '/assistant', icon: MessageSquare },
  { key: 'dashboard', label: 'Dashboards', path: '/dashboard', icon: Gauge },
  { key: 'reports', label: 'Customize Reports', path: '/reports', icon: BarChart3 },
  // Kept separate from the reporting pages above (its own section in the
  // sidebar, not interleaved between them) — a different kind of work.
  {
    key: 'dataEntry', label: 'Operations', path: '/imports-status', icon: ClipboardList,
    children: [
      { label: 'Imports Status', path: '/imports-status' },
      { label: 'Logistics Status', path: '/logistics-status' },
      { label: 'Trucking Status', path: '/trucking-status' },
    ],
  },
  { key: 'userManagement', label: 'User Management', path: '/user-management', icon: Users },
]

/** Where to land an account right after login (or when they're bounced off
 * a page they can't access). Assistant is the intended default landing
 * page for everyone, so it wins whenever the account can see it. Otherwise
 * falls back to the first page in PAGE_DEFS order the account can see. */
export function defaultPathForUser(access: Access | null | undefined): string {
  const allowed = pagesForUser(access)
  if (allowed.includes('assistant')) {
    const assistantDef = PAGE_DEFS.find((p) => p.key === 'assistant')
    if (assistantDef) return assistantDef.path
  }
  const first = PAGE_DEFS.find((p) => allowed.includes(p.key))
  return first?.path ?? '/login'
}
