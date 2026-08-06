import { apiFetch } from './client'
import type { Permission } from '@/lib/roleAccess'

/**
 * User management against the real backend (`/users`, admin-only).
 *
 * The accounts module answers with `{ status, message, data }` — note the
 * envelope keys differ from the data modules' `{ status_code, detail, data }`.
 * apiFetch returns the whole envelope, so each call here unwraps `.data`.
 *
 * The backend has no `name` column: an account is username + password +
 * is_admin + permissions + is_active. Username and password are both
 * min-length 8 (app/accounts/schemas.py) — enforced here too so the user gets
 * a useful message instead of a raw 422.
 */

export interface BackendUser {
  id: number
  username: string
  password: string
  is_admin: boolean
  permissions: Permission[]
  is_active: boolean
}

/** The shape the User Management screen works in (camelCase). */
export interface UserAccount {
  id: number
  username: string
  password: string
  isAdmin: boolean
  permissions: Permission[]
  isActive: boolean
}

interface Envelope<T> {
  status: number
  message: string
  data: T
}

export const MIN_CREDENTIAL_LENGTH = 8

const toAccount = (u: BackendUser): UserAccount => ({
  id: u.id,
  username: u.username,
  password: u.password,
  isAdmin: u.is_admin,
  permissions: u.permissions ?? [],
  isActive: u.is_active,
})

export interface UserPayload {
  username: string
  password: string
  isAdmin: boolean
  permissions: Permission[]
  isActive?: boolean
}

/** An admin holds no permissions — is_admin passes every check on its own, and
 *  the backend clears the list anyway, so don't send a stale checklist. */
function toBody(input: UserPayload) {
  return JSON.stringify({
    username: input.username.trim(),
    password: input.password,
    is_admin: input.isAdmin,
    permissions: input.isAdmin ? [] : input.permissions,
    is_active: input.isActive ?? true,
  })
}

/** Mirrors the backend's min-length rule so the form can fail fast. */
export function credentialError(username: string, password: string): string | null {
  if (username.trim().length < MIN_CREDENTIAL_LENGTH) {
    return `Username must be at least ${MIN_CREDENTIAL_LENGTH} characters`
  }
  if (password.length < MIN_CREDENTIAL_LENGTH) {
    return `Password must be at least ${MIN_CREDENTIAL_LENGTH} characters`
  }
  return null
}

export async function listUsers(): Promise<UserAccount[]> {
  const res = await apiFetch<Envelope<BackendUser[]>>('/users/')
  return (res.data ?? []).map(toAccount)
}

export async function createUser(input: UserPayload): Promise<UserAccount> {
  const res = await apiFetch<Envelope<BackendUser>>('/users/', {
    method: 'POST',
    body: toBody(input),
  })
  return toAccount(res.data)
}

/** PUT /users/{id} takes the WHOLE account (username + password included), so
 *  the caller must pass the existing values it isn't changing. */
export async function updateUser(id: number, input: UserPayload): Promise<UserAccount> {
  const res = await apiFetch<Envelope<BackendUser>>(`/users/${id}`, {
    method: 'PUT',
    body: toBody(input),
  })
  return toAccount(res.data)
}

/** Activate / deactivate. `is_active` is a QUERY param on this route, not a body. */
export async function setUserActive(id: number, isActive: boolean): Promise<UserAccount> {
  const res = await apiFetch<Envelope<BackendUser>>(
    `/users/${id}/status?is_active=${isActive}`,
    { method: 'PUT' },
  )
  return toAccount(res.data)
}
