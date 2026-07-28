import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { pagesForRole } from '@/lib/roleAccess'
import { defaultPathForRole } from '@/lib/pages'
import type { PageKey } from '@/theme/tokens'

/**
 * UI-level page gate — hides pages a role isn't meant to see, including
 * direct URL access. This is NOT a security boundary (the backend owns real
 * authorization); it just keeps the nav and routes consistent with it.
 */
export function RequirePage({ pageKey, children }: { pageKey: PageKey; children: ReactNode }) {
  const { user } = useAuth()
  const allowed = pagesForRole(user?.role)

  if (!allowed.includes(pageKey)) {
    return <Navigate to={defaultPathForRole(user?.role)} replace />
  }

  return <>{children}</>
}
