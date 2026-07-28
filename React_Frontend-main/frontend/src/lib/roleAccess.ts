import type { PageKey } from '@/theme/tokens'

export type Role = 'admin' | 'manager' | 'entry' | 'viewer'

export const ALL_PAGES: PageKey[] = [
  'dashboard', 'purchases', 'inventory', 'imports', 'dataEntry', 'logistics', 'reports', 'assistant', 'userManagement',
]

/** The reporting/BI side of the app — everything except data entry and
 * account administration. */
const REPORTING_PAGES: PageKey[] = ['dashboard', 'purchases', 'inventory', 'imports', 'logistics', 'reports', 'assistant']

/**
 * Role -> allowed page keys. This is a UI-only gate (hide/redirect away from
 * pages a role shouldn't see) — the backend team owns real authorization;
 * nothing here should be treated as a security boundary. Within a page a
 * role CAN see, `can()` below still governs which actions are available
 * (values/prices are never hidden, only entry/edit/admin capabilities are).
 */
const PAGE_ACCESS: Record<Role, PageKey[]> = {
  admin: [...REPORTING_PAGES, 'dataEntry', 'userManagement'],
  manager: [...REPORTING_PAGES, 'dataEntry'],
  entry: ['dataEntry'],
  viewer: REPORTING_PAGES,
}

export function pagesForRole(role: string | undefined): PageKey[] {
  if (!role || !(role in PAGE_ACCESS)) return ALL_PAGES
  return PAGE_ACCESS[role as Role]
}

/**
 * Actions from the permission matrix (README) — components ask `can(user,
 * action)` instead of branching on `user.role` strings directly:
 *  - enter: create a brand-new record (e.g. start the Imports Status wizard)
 *  - editAny: edit any existing record, unrestricted
 *  - editOwnDraft: edit existing records, but only your own drafts. `can()`
 *    only answers whether the role has this scoped capability at all — the
 *    caller still has to check that the specific record is a draft owned by
 *    this user
 *  - viewReports: view the Reports page (read-only is fine for this role —
 *    nothing financial is hidden)
 *  - manageUsers: create/edit user accounts
 *  - manageMastersFull: full CRUD on master data (suppliers, items, etc.)
 *  - manageMastersInlineCreate: create master-data entries inline (e.g. a
 *    dropdown's "+ add new") without full masters management access
 */
export type Action =
  | 'enter'
  | 'editAny'
  | 'editOwnDraft'
  | 'viewReports'
  | 'manageUsers'
  | 'manageMastersFull'
  | 'manageMastersInlineCreate'

const ROLE_ACTIONS: Record<Role, Action[]> = {
  admin: ['enter', 'editAny', 'viewReports', 'manageUsers', 'manageMastersFull'],
  manager: ['enter', 'editAny', 'viewReports', 'manageMastersFull'],
  entry: ['enter', 'editOwnDraft', 'viewReports', 'manageMastersInlineCreate'],
  viewer: ['viewReports'],
}

export function can(user: { role: string } | null | undefined, action: Action): boolean {
  if (!user) return false
  const actions = ROLE_ACTIONS[user.role as Role] as Action[] | undefined
  return actions ? actions.includes(action) : false
}
