import { createContext, useContext, useState, type ReactNode } from 'react'
import { backendLogin, backendLogout } from '@/lib/api/auth'
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

// Versioned: older sessions (roles, then the 5 coarse permissions) aren't
// compatible with the backend's permission names, so this starts fresh
// (logged out) instead of gating the UI on stale values.
const STORAGE_KEY = 'qgirs-user-v3'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  })

  async function login(username: string, password: string) {
    // Real backend first — it sets the httpOnly session cookie every protected
    // endpoint needs, and returns the authoritative is_admin + permissions.
    try {
      const res = await backendLogin(username, password)
      const loggedIn: User = {
        id: res.data.id,
        username: res.data.username,
        name: res.data.username,
        isAdmin: res.data.is_admin,
        permissions: res.data.permissions ?? [],
        isBackend: true,
      }
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedIn))
      setUser(loggedIn)
      return
    } catch (backendError) {
      // Fall through to the mock directory below. Accounts that exist only in
      // the mock seed (the demo users) keep working for the screens still on
      // mock data; anything hitting the real API will 401, which is correct.
      const loggedIn = { ...mockLogin(username, password), isBackend: false }
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedIn))
      setUser(loggedIn)
      // A mock account can't reach the real API — surface nothing here, but if
      // the mock login ALSO failed, mockLogin has already thrown the
      // "Invalid username or password" the form shows.
      void backendError
    }
  }

  async function logout() {
    try {
      await backendLogout()
    } catch {
      // no real session to clear (mock account) — fine
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
