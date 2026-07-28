import { createContext, useContext, useState, type ReactNode } from 'react'
import { mockLogin } from '@/lib/mockAuth'
import type { Role } from '@/lib/roleAccess'

export interface User {
  username: string
  name: string
  role: Role
}

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

const STORAGE_KEY = 'qgirs-user'

export function AuthProvider({ children }: { children: ReactNode }) {
  // Frontend-only stub: session lives in localStorage until a real backend
  // exists (see src/lib/mockAuth.ts). This is what makes the login survive
  // a browser/app restart for now, in place of the httpOnly cookie a real
  // API would set.
  const [user, setUser] = useState<User | null>(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as User) : null
  })

  async function login(username: string, password: string) {
    const loggedInUser = mockLogin(username, password)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(loggedInUser))
    setUser(loggedInUser)
  }

  async function logout() {
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
