import { createContext, useContext, useState, type ReactNode } from 'react'
import { backendLogin, backendLogout } from '@/lib/api/auth'
import { mockLogin } from '@/lib/mockAuth'
import type { Permission } from '@/lib/roleAccess'

export interface User {
  id: number
  username: string
  name: string
  isAdmin: boolean
  permissions: Permission[]
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

// Versioned: older sessions (roles, then the 5 coarse permissions, then the
// mock directory) aren't compatible with the backend's permission names, so
// this starts fresh (logged out) instead of gating the UI on stale values.
//
// What's cached here is only WHO the session belongs to and what the UI may
// show — the actual credential is the backend's httpOnly cookie, which
// JavaScript can't read. Clearing this key logs you out of the UI; the cookie
// is cleared by /auth/logout.
const STORAGE_KEY = 'qgirs-user-v4'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    try {
      return JSON.parse(raw) as User
    } catch {
      window.localStorage.removeItem(STORAGE_KEY)
      return null
    }
  })

  /** Logs into the real backend. It sets the httpOnly session cookie every
   *  protected endpoint needs and returns the authoritative is_admin +
   *  permissions. A bad credential throws ApiError, which the login form
   *  shows — there is no local fallback any more. */
  async function login(username: string, password: string) {
    const res = await backendLogin(username, password)
    const loggedIn: User = {
      id: res.data.id,
      username: res.data.username,
      name: res.data.username,
      isAdmin: res.data.is_admin,
      permissions: res.data.permissions ?? [],
    }
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedIn))
    setUser(loggedIn)
  }

  async function logout() {
    try {
      await backendLogout()
    } catch {
      // Already expired or unreachable — clear the local session regardless,
      // so the user is never stuck "logged in" against a dead cookie.
    }
    window.localStorage.removeItem(STORAGE_KEY)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading: false, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
