import { ShieldAlert } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ApiError } from '@/lib/api/auth'

/** The loading and error cards every live-data dashboard shows, in one place
 * instead of a copy per page — same markup they each had inline. */

/** One shimmering placeholder block. `motion-reduce:animate-none` because a
 *  perpetual pulse is exactly the kind of motion someone with
 *  prefers-reduced-motion set has asked not to see. */
function Bar({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-line/70 motion-reduce:animate-none ${className}`} />
}

/**
 * A skeleton in the shape of the dashboard that is about to arrive — hero
 * stat, the five-across KPI row, then the 2/3 + 1/3 chart pair.
 *
 * The point is to RESERVE THE SPACE, not to look busy: a one-line "Loading…"
 * card is ~60px tall and the real content is ~900px, so every dashboard used
 * to jump the moment data landed. Matching the real layout keeps cumulative
 * layout shift near zero.
 */
function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-hidden>
      <Card>
        <CardContent className="p-6">
          <Bar className="h-3.5 w-24" />
          <Bar className="mt-3 h-9 w-56" />
          <Bar className="mt-5 h-[180px] w-full" />
        </CardContent>
      </Card>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(11rem,1fr))] gap-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Card key={i}>
            <CardContent className="p-5">
              <Bar className="h-3 w-20" />
              <Bar className="mt-3 h-7 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <Bar className="h-3.5 w-28" />
            <Bar className="mt-4 h-[300px] w-full" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <Bar className="h-3.5 w-28" />
            <Bar className="mt-4 h-[300px] w-full" />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export function LiveDataState({ isLoading, isFetching = false, isError, error, skeleton = 'panel' }: {
  isLoading: boolean
  /** True while a background refetch is in flight — a filter or period change,
   *  with the PREVIOUS result still cached (`keepPreviousData`) and technically
   *  renderable. Treated the same as isLoading: the point of changing a filter
   *  is that the old numbers are now describing the wrong set, so leaving them
   *  on screen unmarked while new ones load is worse than a skeleton. The page
   *  itself must also stop rendering its own `{data && (...)}` block while this
   *  is true, or the stale content renders underneath the skeleton at the same
   *  time — this component only owns the loading/error state, not the content. */
  isFetching?: boolean
  isError: boolean
  error: unknown
  /** 'dashboard' reserves a full dashboard's worth of layout so nothing jumps
   *  when the data lands; 'panel' is the single small card, for pages whose
   *  real content isn't dashboard-shaped (e.g. the Reports table). */
  skeleton?: 'dashboard' | 'panel'
}) {
  if (isLoading || isFetching) {
    if (skeleton === 'dashboard') return <DashboardSkeleton />
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
