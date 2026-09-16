import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { backendLogin, backendLogout } from '@/lib/api/auth'
import { startIdleTimeoutWatcher } from './idleTimeout'
import { forceLogout, STORAGE_KEY } from './forceLogout'
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

// STORAGE_KEY now lives in ./forceLogout, since that module needs it too and
// has no dependency on this one (see its own comment for why).

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

  // Idle-timeout auto-logout - only while actually signed in, so no watching
  // machinery runs on the login screen itself. forceLogout (a hard redirect,
  // not this component's own setUser/navigate) is what runs on the 30-minute
  // mark - see forceLogout.ts for why a hard redirect is used here rather
  // than the SPA-style clear-and-navigate this component's own logout()
  // above uses for an explicit "Log out" click.
  useEffect(() => {
    if (!user) return
    return startIdleTimeoutWatcher(forceLogout)
  }, [user])

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
