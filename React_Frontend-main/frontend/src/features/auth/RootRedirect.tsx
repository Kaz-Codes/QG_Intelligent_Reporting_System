import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { defaultPathForUser } from '@/lib/pages'

/** Sends "/" and any unknown path to the right place: the login screen if
 * signed out, otherwise the first page this account is allowed to see
 * (Assistant by default, or Operations if that's all a limited account
 * can see). */
export function RootRedirect() {
  const { user } = useAuth()
  return <Navigate to={user ? defaultPathForUser(user) : '/login'} replace />
}
