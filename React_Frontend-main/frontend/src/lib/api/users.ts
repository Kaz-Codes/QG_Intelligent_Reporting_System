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

/** app/enums.py NotificationTier. */
export type NotificationTier = 'operational' | 'managerial' | 'executive'

export interface BackendUser {
  id: number
  username: string
  password: string
  is_admin: boolean
  permissions: Permission[]
  is_active: boolean
  notification_tier: NotificationTier
  phone_number: string | null
  whatsapp_opted_in: boolean
  /** Server-set evidence of when consent was given. Read-only — it is never
   *  sent back, so it cannot be backdated. See app/accounts/helpers.py. */
  whatsapp_opted_in_at: string | null
}

/** The shape the User Management screen works in (camelCase). */
export interface UserAccount {
  id: number
  username: string
  password: string
  isAdmin: boolean
  permissions: Permission[]
  isActive: boolean
  notificationTier: NotificationTier
  phoneNumber: string
  whatsappOptedIn: boolean
  whatsappOptedInAt: string | null
}

//-----------------------------------------------------
// NOTIFICATION SETTINGS
//
// The tier is a CEILING and it works the opposite way round to how a list of
// seniority reads: a user receives an event when their tier is at or below the
// event's, so operational receives EVERYTHING and executive receives only what
// is pitched at executive. The descriptions say so out loud, because a
// dropdown reading Operational / Managerial / Executive invites exactly the
// wrong assumption — that executive sees more.
//-----------------------------------------------------

export const NOTIFICATION_TIERS: {
  value: NotificationTier
  label: string
  hint: string
}[] = [
  {
    value: 'operational',
    label: 'Operational',
    hint: 'Receives every notification. The default.',
  },
  {
    value: 'managerial',
    label: 'Managerial',
    hint: 'Receives managerial and executive notifications.',
  },
  {
    value: 'executive',
    label: 'Executive',
    hint: 'Receives only material business events.',
  },
]

/** Mirrors app/accounts/schemas.py's E164 pattern so the form can fail before
 *  the request, with the same rule rather than a looser one. */
const E164 = /^\+[1-9]\d{6,14}$/

export function phoneError(phone: string): string | null {
  const value = phone.trim()
  if (!value) return null
  if (!E164.test(value)) {
    return "Phone must start with '+' and contain digits only, e.g. +923001234567"
  }
  return null
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
  // Defaulted the same way the column is, so a response from an older backend
  // that does not send the field reads as operational rather than undefined
  // and blanking the dropdown.
  notificationTier: u.notification_tier ?? 'operational',
  // NULL becomes '' because this feeds a controlled text input, and React
  // treats a null value as uncontrolled.
  phoneNumber: u.phone_number ?? '',
  whatsappOptedIn: u.whatsapp_opted_in ?? false,
  whatsappOptedInAt: u.whatsapp_opted_in_at ?? null,
})

export interface UserPayload {
  username: string
  password: string
  isAdmin: boolean
  permissions: Permission[]
  isActive?: boolean
  notificationTier?: NotificationTier
  phoneNumber?: string
  whatsappOptedIn?: boolean
}

/** An admin holds no permissions — is_admin passes every check on its own, and
 *  the backend clears the list anyway, so don't send a stale checklist. */
function toBody(input: UserPayload) {
  const phone = input.phoneNumber?.trim() ?? ''

  return JSON.stringify({
    username: input.username.trim(),
    password: input.password,
    is_admin: input.isAdmin,
    permissions: input.isAdmin ? [] : input.permissions,
    is_active: input.isActive ?? true,
    notification_tier: input.notificationTier ?? 'operational',
    // An empty box means "no number", so it goes as null rather than "" — the
    // backend normalises either way, but sending null keeps the column's
    // meaning ("absent") out of the realm of empty strings.
    phone_number: phone || null,
    // Consent cannot survive its own phone number being cleared. Sent as
    // false rather than relying on the backend's 400, so clearing the number
    // and saving does the obvious thing instead of failing the form.
    whatsapp_opted_in: phone ? (input.whatsappOptedIn ?? false) : false,
    // whatsapp_opted_in_at is deliberately NOT sent — it is server-set
    // evidence of consent and must not be backdatable from here.
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
