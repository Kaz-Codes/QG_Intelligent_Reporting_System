import { ShieldAlert } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ApiError } from '@/lib/api/auth'

/** The loading and error cards every live-data dashboard shows, in one place
 * instead of a copy per page — same markup they each had inline. */
export function LiveDataState({ isLoading, isError, error }: {
  isLoading: boolean
  isError: boolean
  error: unknown
}) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-muted">Loading live data…</CardContent>
      </Card>
    )
  }
  if (!isError) return null
  return (
    <Card>
      <CardContent className="flex items-start gap-2 p-5 text-sm text-risk">
        <ShieldAlert size={16} className="mt-0.5 shrink-0" />
        <span>
          {error instanceof ApiError && error.status === 401
            ? 'Signed in, but not with an account the backend recognizes yet — only the seeded admin account has live access right now.'
            : error instanceof ApiError && error.status === 403
              ? "Signed in, but this account doesn't have permission to use this feature."
              : 'Could not reach the backend — is it running?'}
        </span>
      </CardContent>
    </Card>
  )
}
