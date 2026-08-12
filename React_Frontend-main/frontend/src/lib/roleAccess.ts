import type { PageKey } from '@/theme/tokens'

/**
 * No more roles — every account is either an Admin (sees and can do
 * everything, including managing other accounts) or a regular account whose
 * visibility is whatever's checked in its permission list. Admin status is a
 * separate flag, not one of the checkboxes, so a permission edit can never
 * accidentally grant/revoke User Management access.
 *
 * The permission NAMES below are the backend catalogue verbatim
 * (app/accounts/permissions.py). They are what `POST/PUT /users` accepts and
 * what the session reports back, so the two sides must match exactly — do not
 * rename one without the other. The UI-friendly labels live in
 * PERMISSION_GROUPS; the wire values are always these snake_case names.
 */

// --- imports consignments ---
export const CAN_VIEW_IMPORTS = 'can_view_imports_consignments'
export const CAN_ADD_IMPORTS = 'can_add_imports_consignments'
export const CAN_EDIT_IMPORTS = 'can_edit_imports_consignments'

// --- logistics consignments ---
export const CAN_VIEW_LOGISTICS = 'can_view_logistics_consignments'
export const CAN_ADD_LOGISTICS = 'can_add_logistics_consignments'
export const CAN_EDIT_LOGISTICS = 'can_edit_logistics_consignments'

// --- trucking consignments ---
export const CAN_VIEW_TRUCKING = 'can_view_trucking_consignments'
export const CAN_ADD_TRUCKING = 'can_add_trucking_consignments'
export const CAN_EDIT_TRUCKING = 'can_edit_trucking_consignments'

// --- dashboards (view-only) ---
export const CAN_VIEW_OVERVIEW_DASHBOARD = 'can_view_overview_dashboard'
export const CAN_VIEW_IMPORTS_DASHBOARD = 'can_view_imports_dashboard'
export const CAN_VIEW_LOGISTICS_DASHBOARD = 'can_view_logistics_dashboard'
export const CAN_VIEW_PURCHASES_DASHBOARD = 'can_view_purchases_dashboard'
export const CAN_VIEW_INVENTORY_DASHBOARD = 'can_view_inventory_dashboard'

// --- masters ---
export const CAN_VIEW_MASTER = 'can_view_master'
export const CAN_ADD_MASTER = 'can_add_master'
export const CAN_EDIT_MASTER = 'can_edit_master'

// --- misc features ---
export const CAN_USE_ASSISTANT = 'can_use_assistant'
export const CAN_MAKE_REPORTS = 'can_make_reports'

/** Grouped for the User Management checklist — the grouping is presentation
 *  only; the wire format is the flat list of names. */
export const PERMISSION_GROUPS: { group: string; permissions: { value: Permission; label: string }[] }[] = [
  {
    group: 'Imports — Data Entry',
    permissions: [
      { value: CAN_VIEW_IMPORTS, label: 'View' },
      { value: CAN_ADD_IMPORTS, label: 'Add' },
      { value: CAN_EDIT_IMPORTS, label: 'Edit' },
    ],
  },
  {
    group: 'Logistics — Data Entry',
    permissions: [
      { value: CAN_VIEW_LOGISTICS, label: 'View' },
      { value: CAN_ADD_LOGISTICS, label: 'Add' },
      { value: CAN_EDIT_LOGISTICS, label: 'Edit' },
    ],
  },
  {
    group: 'Trucking — Data Entry',
    permissions: [
      { value: CAN_VIEW_TRUCKING, label: 'View' },
      { value: CAN_ADD_TRUCKING, label: 'Add' },
      { value: CAN_EDIT_TRUCKING, label: 'Edit' },
    ],
  },
  {
    group: 'Dashboards',
    permissions: [
      { value: CAN_VIEW_OVERVIEW_DASHBOARD, label: 'Overview' },
      { value: CAN_VIEW_IMPORTS_DASHBOARD, label: 'Imports' },
      { value: CAN_VIEW_LOGISTICS_DASHBOARD, label: 'Logistics' },
      { value: CAN_VIEW_PURCHASES_DASHBOARD, label: 'Purchases' },
      { value: CAN_VIEW_INVENTORY_DASHBOARD, label: 'Inventory' },
    ],
  },
  {
    group: 'Master Data',
    permissions: [
      { value: CAN_VIEW_MASTER, label: 'View masters' },
      { value: CAN_ADD_MASTER, label: 'Add inline' },
      { value: CAN_EDIT_MASTER, label: 'Manage masters' },
    ],
  },
  {
    group: 'Other',
    permissions: [
      { value: CAN_MAKE_REPORTS, label: 'Customize Reports' },
      { value: CAN_USE_ASSISTANT, label: 'Assistant' },
    ],
  },
]

/** Every permission name, in catalogue order. */
export const PERMISSIONS = PERMISSION_GROUPS.flatMap((g) => g.permissions)

export const PERMISSION_NAMES = [
  CAN_VIEW_IMPORTS, CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS,
  CAN_VIEW_LOGISTICS, CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS,
  CAN_VIEW_TRUCKING, CAN_ADD_TRUCKING, CAN_EDIT_TRUCKING,
  CAN_VIEW_OVERVIEW_DASHBOARD, CAN_VIEW_IMPORTS_DASHBOARD, CAN_VIEW_LOGISTICS_DASHBOARD,
  CAN_VIEW_PURCHASES_DASHBOARD, CAN_VIEW_INVENTORY_DASHBOARD,
  CAN_VIEW_MASTER, CAN_ADD_MASTER, CAN_EDIT_MASTER,
  CAN_USE_ASSISTANT, CAN_MAKE_REPORTS,
] as const

export type Permission = (typeof PERMISSION_NAMES)[number]

/** Label for a permission name, for the account summary chips. */
export function permissionLabel(name: Permission): string {
  for (const g of PERMISSION_GROUPS) {
    const hit = g.permissions.find((p) => p.value === name)
    if (hit) return `${g.group.split(' — ')[0]}: ${hit.label}`
  }
  return name
}

/** The minimal shape every access check needs. Real `User` objects
 * (AuthContext) and in-progress edit-form state both satisfy this. */
export interface Access {
  isAdmin: boolean
  permissions: Permission[]
}

/** The three data-entry modules, for module-scoped checks. */
export type ModuleKey = 'imports' | 'logistics' | 'trucking'

const MODULE_PERMISSIONS: Record<ModuleKey, { view: Permission; add: Permission; edit: Permission }> = {
  imports: { view: CAN_VIEW_IMPORTS, add: CAN_ADD_IMPORTS, edit: CAN_EDIT_IMPORTS },
  logistics: { view: CAN_VIEW_LOGISTICS, add: CAN_ADD_LOGISTICS, edit: CAN_EDIT_LOGISTICS },
  trucking: { view: CAN_VIEW_TRUCKING, add: CAN_ADD_TRUCKING, edit: CAN_EDIT_TRUCKING },
}

const DASHBOARD_PERMISSIONS: Permission[] = [
  CAN_VIEW_OVERVIEW_DASHBOARD, CAN_VIEW_IMPORTS_DASHBOARD, CAN_VIEW_LOGISTICS_DASHBOARD,
  CAN_VIEW_PURCHASES_DASHBOARD, CAN_VIEW_INVENTORY_DASHBOARD,
]

const DATA_ENTRY_PERMISSIONS: Permission[] = [
  CAN_VIEW_IMPORTS, CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS,
  CAN_VIEW_LOGISTICS, CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS,
  CAN_VIEW_TRUCKING, CAN_ADD_TRUCKING, CAN_EDIT_TRUCKING,
]

const ALL_PAGES: PageKey[] = ['assistant', 'dashboard', 'reports', 'dataEntry', 'masters', 'userManagement']

const has = (access: Access, ...names: Permission[]) =>
  names.some((n) => access.permissions.includes(n))

/**
 * Pages this account can see. This is a UI-only gate (hide/redirect away
 * from pages an account shouldn't see, including direct URL access) — the
 * backend owns real authorization on every route.
 */
export function pagesForUser(access: Access | null | undefined): PageKey[] {
  if (!access) return []
  if (access.isAdmin) return ALL_PAGES

  const pages: PageKey[] = []
  if (has(access, CAN_USE_ASSISTANT)) pages.push('assistant')
  if (has(access, ...DASHBOARD_PERMISSIONS)) pages.push('dashboard')
  if (has(access, CAN_MAKE_REPORTS)) pages.push('reports')
  if (has(access, ...DATA_ENTRY_PERMISSIONS)) pages.push('dataEntry')
  if (has(access, CAN_VIEW_MASTER)) pages.push('masters')
  return pages
}

/**
 * Actions from the permission matrix — components ask `can(user, action)`
 * instead of branching on permission strings directly:
 *  - enter: create a brand-new record (e.g. start the Imports Status wizard)
 *  - editAny: edit an existing record
 *  - editOwnDraft: edit only your own records. The BACKEND enforces this
 *    (verify_entry_ownership restricts a non-admin to rows they created), so
 *    the UI treats it the same as editAny and lets the server say no.
 *  - viewReports: view the Reports page
 *  - manageUsers: create/edit user accounts (admin only)
 *  - manageMastersFull: full CRUD on master data (suppliers, items, etc.)
 *  - manageMastersInlineCreate: create master-data entries inline (e.g. a
 *    dropdown's "+ add new") without full masters management access
 *
 * `module` scopes the data-entry actions to one module; omitted, it means
 * "any module", which is what a shared screen (or an older call site) wants.
 */
export type Action =
  | 'enter'
  | 'editAny'
  | 'editOwnDraft'
  | 'viewReports'
  | 'manageUsers'
  | 'manageMastersFull'
  | 'manageMastersInlineCreate'

export function can(
  access: Access | null | undefined,
  action: Action,
  module?: ModuleKey,
): boolean {
  if (!access) return false
  if (access.isAdmin) return true

  const modules: ModuleKey[] = module ? [module] : ['imports', 'logistics', 'trucking']
  const forEach = (key: 'view' | 'add' | 'edit') =>
    modules.some((m) => access.permissions.includes(MODULE_PERMISSIONS[m][key]))

  switch (action) {
    case 'enter':
      return forEach('add')
    // Ownership is a server-side rule, so both edit actions ask the same
    // question here; the backend rejects someone else's record.
    case 'editAny':
    case 'editOwnDraft':
      return forEach('edit')
    case 'viewReports':
      return has(access, CAN_MAKE_REPORTS)
    case 'manageMastersFull':
      return has(access, CAN_EDIT_MASTER)
    case 'manageMastersInlineCreate':
      return has(access, CAN_ADD_MASTER)
    case 'manageUsers':
      // Account management is admin-only; no permission grants it.
      return false
  }
}
