import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { defaultPathForRole } from '@/lib/pages'

/** Sends "/" and any unknown path to the right place: the login screen if
 * signed out, otherwise the first page this role is allowed to see (e.g.
 * Operations for an entry-role user, not the analytics Dashboard). */
export function RootRedirect() {
  const { user } = useAuth()
  return <Navigate to={user ? defaultPathForRole(user.role) : '/login'} replace />
}
