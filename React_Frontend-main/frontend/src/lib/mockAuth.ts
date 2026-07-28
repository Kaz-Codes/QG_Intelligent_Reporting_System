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

const USERS: MockUser[] = [
  { username: 'admin', password: 'admin123', name: 'Admin User', role: 'admin' },
  { username: 'manager', password: 'admin123', name: 'Manager User', role: 'manager' },
  { username: 'entry', password: 'admin123', name: 'Entry User', role: 'entry' },
  { username: 'viewer', password: 'admin123', name: 'Viewer User', role: 'viewer' },
]

export function mockLogin(username: string, password: string) {
  const user = USERS.find((u) => u.username === username && u.password === password)
  if (!user) throw new Error('Invalid username or password')
  return { username: user.username, name: user.name, role: user.role }
}
