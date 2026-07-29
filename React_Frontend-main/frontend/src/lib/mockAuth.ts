/**
 * TEMPORARY frontend-only auth stub. There's no backend yet (a teammate
 * owns that separately) — this just gates the UI so pages/roles can be
 * built and reviewed now. Plaintext passwords are fine here since this
 * isn't real security, only a UI demo gate; it'll be replaced wholesale
 * once a real login API exists (delete this file, not edit it — real
 * sessions need an httpOnly cookie, not a localStorage user object).
 */

import type { Role } from './roleAccess'

export interface MockUser {
  username: string
  password: string
  name: string
  role: Role
}

const DEFAULT_USERS: MockUser[] = [
  { username: 'admin', password: 'admin123', name: 'Admin User', role: 'admin' },
  { username: 'manager', password: 'admin123', name: 'Manager User', role: 'manager' },
  { username: 'entry', password: 'admin123', name: 'Entry User', role: 'entry' },
  { username: 'viewer', password: 'admin123', name: 'Viewer User', role: 'viewer' },
]

// Accounts an admin creates need to survive a reload, same as the session
// itself — stored alongside it in localStorage until a real backend/DB
// owns the user directory.
const DIRECTORY_KEY = 'qgirs-user-directory'

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
  return { username: user.username, name: user.name, role: user.role }
}

/** Admin-only: every account except its password, for the User Management list. */
export function listUsers(): Omit<MockUser, 'password'>[] {
  return loadUsers().map(({ password: _password, ...rest }) => rest)
}

/** Admin-only: create a new account — name, username, password, role. */
export function createUser(input: { name: string; username: string; password: string; role: Role }): void {
  const username = input.username.trim()
  const name = input.name.trim()
  if (!name) throw new Error('Name is required')
  if (!username) throw new Error('Username is required')
  if (!input.password) throw new Error('Password is required')

  const users = loadUsers()
  if (users.some((u) => u.username.toLowerCase() === username.toLowerCase())) {
    throw new Error('That username is already taken')
  }

  users.push({ username, password: input.password, name, role: input.role })
  saveUsers(users)
}
