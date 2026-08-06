/**
 * TEMPORARY frontend-only auth stub. There's no backend yet (a teammate
 * owns that separately) — this just gates the UI so pages/permissions can
 * be built and reviewed now. Plaintext passwords are fine here since this
 * isn't real security, only a UI demo gate; it'll be replaced wholesale
 * once a real login API exists (delete this file, not edit it — real
 * sessions need an httpOnly cookie, not a localStorage user object).
 */

import {
  type Permission,
  CAN_VIEW_IMPORTS, CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS,
  CAN_VIEW_LOGISTICS, CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS,
  CAN_VIEW_TRUCKING, CAN_ADD_TRUCKING, CAN_EDIT_TRUCKING,
  CAN_VIEW_OVERVIEW_DASHBOARD, CAN_VIEW_IMPORTS_DASHBOARD, CAN_VIEW_LOGISTICS_DASHBOARD,
  CAN_VIEW_PURCHASES_DASHBOARD, CAN_VIEW_INVENTORY_DASHBOARD,
  CAN_VIEW_MASTER, CAN_ADD_MASTER,
  CAN_USE_ASSISTANT, CAN_MAKE_REPORTS,
} from './roleAccess'

export interface MockUser {
  username: string
  password: string
  name: string
  isAdmin: boolean
  permissions: Permission[]
}

const ALL_DASHBOARDS: Permission[] = [
  CAN_VIEW_OVERVIEW_DASHBOARD, CAN_VIEW_IMPORTS_DASHBOARD, CAN_VIEW_LOGISTICS_DASHBOARD,
  CAN_VIEW_PURCHASES_DASHBOARD, CAN_VIEW_INVENTORY_DASHBOARD,
]

const ALL_OPERATIONS_EDIT: Permission[] = [
  CAN_VIEW_IMPORTS, CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS,
  CAN_VIEW_LOGISTICS, CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS,
  CAN_VIEW_TRUCKING, CAN_ADD_TRUCKING, CAN_EDIT_TRUCKING,
  CAN_VIEW_MASTER, CAN_ADD_MASTER,
]

const ALL_OPERATIONS_VIEW: Permission[] = [
  CAN_VIEW_IMPORTS, CAN_VIEW_LOGISTICS, CAN_VIEW_TRUCKING, CAN_VIEW_MASTER,
]

const DEFAULT_USERS: MockUser[] = [
  { username: 'admin', password: 'admin123', name: 'Admin User', isAdmin: true, permissions: [] },
  {
    username: 'manager', password: 'admin123', name: 'Manager User', isAdmin: false,
    permissions: [CAN_USE_ASSISTANT, CAN_MAKE_REPORTS, ...ALL_DASHBOARDS, ...ALL_OPERATIONS_EDIT],
  },
  {
    username: 'entry', password: 'admin123', name: 'Entry User', isAdmin: false,
    permissions: [CAN_USE_ASSISTANT, ...ALL_OPERATIONS_EDIT],
  },
  {
    username: 'viewer', password: 'admin123', name: 'Viewer User', isAdmin: false,
    permissions: [CAN_USE_ASSISTANT, CAN_MAKE_REPORTS, ...ALL_DASHBOARDS, ...ALL_OPERATIONS_VIEW],
  },
]

// Accounts an admin creates need to survive a reload, same as the session
// itself — stored alongside it in localStorage until a real backend/DB
// owns the user directory. Versioned key: the old role-shaped directory
// (username/password/name/role) isn't compatible with the isAdmin +
// permissions shape, so this reseeds fresh instead of crashing on stale data.
const DIRECTORY_KEY = 'qgirs-user-directory-v2'

function loadUsers(): MockUser[] {
  const raw = window.localStorage.getItem(DIRECTORY_KEY)
  if (raw) return JSON.parse(raw) as MockUser[]
  window.localStorage.setItem(DIRECTORY_KEY, JSON.stringify(DEFAULT_USERS))
  return DEFAULT_USERS
}

function saveUsers(users: MockUser[]) {
  window.localStorage.setItem(DIRECTORY_KEY, JSON.stringify(users))
}

export function mockLogin(username: string, password: string) {
  const user = loadUsers().find((u) => u.username === username && u.password === password)
  if (!user) throw new Error('Invalid username or password')
  return { username: user.username, name: user.name, isAdmin: user.isAdmin, permissions: user.permissions }
}

/** Every account except its password, for the User Management list. */
export function listUsers(): Omit<MockUser, 'password'>[] {
  return loadUsers().map(({ password: _password, ...rest }) => rest)
}

/** Admin-only: create a new account — name, username, password, admin flag, permissions. */
export function createUser(input: { name: string; username: string; password: string; isAdmin: boolean; permissions: Permission[] }): void {
  const username = input.username.trim()
  const name = input.name.trim()
  if (!name) throw new Error('Name is required')
  if (!username) throw new Error('Username is required')
  if (!input.password) throw new Error('Password is required')

  const users = loadUsers()
  if (users.some((u) => u.username.toLowerCase() === username.toLowerCase())) {
    throw new Error('That username is already taken')
  }

  users.push({ username, password: input.password, name, isAdmin: input.isAdmin, permissions: input.permissions })
  saveUsers(users)
}

/** Admin-only: change an existing account's admin flag and/or permission
 * checklist — the ongoing edit path, as opposed to createUser's one-time
 * initial grant. Username/password/name aren't touched here. */
export function updateUserAccess(username: string, updates: { isAdmin: boolean; permissions: Permission[] }): void {
  const users = loadUsers()
  const target = users.find((u) => u.username === username)
  if (!target) throw new Error('Account not found')
  target.isAdmin = updates.isAdmin
  target.permissions = updates.permissions
  saveUsers(users)
}
