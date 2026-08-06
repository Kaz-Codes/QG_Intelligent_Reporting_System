import { apiFetch, ApiError } from './client'
import type { Permission } from '@/lib/roleAccess'

interface BackendLoginResponse {
  status: number
  message: string
  data: {
    id: number
    username: string
    /** Admin passes every check, including User Management. */
    is_admin: boolean
    /** Catalogue names (empty for an admin — the flag covers everything). */
    permissions: Permission[]
  }
}

/** Logs into the real backend so its httpOnly session cookie is set. The
 * response carries is_admin + the permission names, which is what the UI gates
 * on — the backend still authorizes every request on its own. */
export async function backendLogin(username: string, password: string) {
  return apiFetch<BackendLoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export async function backendLogout() {
  return apiFetch<unknown>('/auth/logout', { method: 'POST' })
}

export { ApiError }
