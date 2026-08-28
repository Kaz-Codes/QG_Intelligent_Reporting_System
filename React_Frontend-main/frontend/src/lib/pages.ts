import {
  Gauge, ClipboardList, BarChart3, MessageSquare, Users, Boxes,
  type LucideIcon,
} from 'lucide-react'
import type { PageKey } from '@/theme/tokens'
import { can, pagesForUser, type Access, type ModuleKey } from './roleAccess'

export interface PageDef {
  key: PageKey
  label: string
  path: string
  icon: LucideIcon
  /** Sub-links rendered under this item instead of it being a direct link
   * itself — used for Operations, which groups three independent route trees
   * (Imports Status, Logistics Status, Trucking Status) behind one sidebar
   * entry.
   *
   * `module` is which data-entry module the link leads to, so the nav can ask
   * can(user, 'view', module) and drop entries the account cannot open. It is
   * on the definition rather than inferred from the path because a path is a
   * string that can be edited without anyone thinking about permissions. */
  children?: { label: string; path: string; module: ModuleKey }[]
}

// Single source of truth for the sidebar/routes — mirrors the old
// Streamlit `PAGES` dict in app.py: to reorder/rename a tab, edit here only.
// Purchases/Inventory/Imports/Logistics aren't separate entries — they live
// as tabs inside Dashboard (see Dashboard.tsx's own tab bar).
export const PAGE_DEFS: PageDef[] = [
  { key: 'assistant', label: 'AI-Assistant', path: '/assistant', icon: MessageSquare },
  { key: 'dashboard', label: 'Dashboards', path: '/dashboard', icon: Gauge },
  { key: 'reports', label: 'Customize Reports', path: '/reports', icon: BarChart3 },
  // Kept separate from the reporting pages above (its own section in the
  // sidebar, not interleaved between them) — a different kind of work.
  {
    key: 'dataEntry', label: 'Operations', path: '/imports-status', icon: ClipboardList,
    children: [
      { label: 'Imports Status', path: '/imports-status', module: 'imports' },
      { label: 'Logistics Status', path: '/logistics-status', module: 'logistics' },
      { label: 'Trucking Status', path: '/trucking-status', module: 'trucking' },
    ],
  },
  { key: 'masters', label: 'Masters', path: '/masters', icon: Boxes },
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
  if (!first) return '/login'

  // A GROUP'S OWN `path` IS ONLY ITS FIRST CHILD, and the account may not be
  // able to see that one. Operations points at /imports-status, so a
  // trucking-only account was landed on the imports list — allowed through by
  // the route guard, since it gates on the `dataEntry` group rather than the
  // module, and then met with 403s from every request the page made.
  //
  // Same cause as the nav filtering in TopNav: a group is not one destination.
  // Land on the first child the account can actually view.
  if (first.children) {
    const child = first.children.find((c) => can(access, 'view', c.module))
    if (child) return child.path
  }

  return first.path
}
