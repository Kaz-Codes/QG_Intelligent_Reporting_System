import { useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, BellOff, CheckCheck, Loader2, X } from 'lucide-react'

import {
  type ApiNotification,
  type NotificationSeverity,
  dayGroupLabel,
  entityPath,
  moduleLabel,
  relativeTime,
  toSeverity,
} from '@/lib/api/notifications'
import {
  useMarkAllRead,
  useMarkRead,
  useNotificationList,
} from '@/lib/api/useNotifications'
import { cn } from '@/lib/utils'

//-----------------------------------------------------
// SEVERITY STYLING
//
// The existing semantic tokens, unchanged: risk (red) / watch (amber) / info
// (blue) are already what every status badge, KPI and chart in the app uses
// for late / approaching / neutral. A notification saying "critical" in a
// colour nothing else in the app uses would be a fourth vocabulary for the
// same idea.
//
// WRITTEN OUT AS WHOLE LITERAL CLASS NAMES, NEVER INTERPOLATED. Tailwind
// scans source text for complete class names, so `bg-${tone}-bg` is never
// generated and the colour silently vanishes at build time while looking
// perfectly correct here.
//-----------------------------------------------------

const SEVERITY: Record<
  NotificationSeverity,
  { label: string; bar: string; chip: string }
> = {
  critical: {
    label: 'Critical',
    bar: 'bg-risk',
    chip: 'bg-risk-bg text-risk',
  },
  important: {
    label: 'Important',
    bar: 'bg-watch',
    chip: 'bg-watch-bg text-watch',
  },
  info: {
    label: 'Info',
    bar: 'bg-info',
    chip: 'bg-info-bg text-info',
  },
}

//-----------------------------------------------------
// GROUPING
//
// Unread first, then read; within each, by calendar day. Two passes rather
// than one sort with a compound comparator, because "unread first" is a
// different KIND of ordering from "newest first" and folding them together is
// what makes such a list hard to change later.
//
// The backend already returns newest-first, so day order falls out of the
// input and is not re-sorted here.
//-----------------------------------------------------

interface DayGroup {
  label: string
  rows: ApiNotification[]
}

interface Section {
  key: 'unread' | 'read'
  label: string
  groups: DayGroup[]
}

function groupByDay(rows: ApiNotification[]): DayGroup[] {
  const groups: DayGroup[] = []

  for (const row of rows) {
    const label = dayGroupLabel(row.created_at)
    const last = groups[groups.length - 1]

    if (last && last.label === label) last.rows.push(row)
    else groups.push({ label, rows: [row] })
  }

  return groups
}

function buildSections(rows: ApiNotification[]): Section[] {
  const unread = rows.filter((r) => !r.is_read)
  const read = rows.filter((r) => r.is_read)

  const sections: Section[] = []

  if (unread.length) {
    sections.push({ key: 'unread', label: 'Unread', groups: groupByDay(unread) })
  }
  if (read.length) {
    sections.push({ key: 'read', label: 'Earlier', groups: groupByDay(read) })
  }

  return sections
}

//-----------------------------------------------------
// ONE ROW
//-----------------------------------------------------

function NotificationRow({
  row,
  onSelect,
}: {
  row: ApiNotification
  onSelect: (row: ApiNotification) => void
}) {
  const severity = SEVERITY[toSeverity(row.event.severity)]
  const navigable = entityPath(row.event) !== null

  return (
    <button
      type="button"
      onClick={() => onSelect(row)}
      className={cn(
        'relative flex w-full gap-3 border-b border-line/60 px-4 py-3 text-left transition-colors',
        'hover:bg-canvas-alt focus:bg-canvas-alt focus:outline-none',
        !row.is_read && 'bg-brand-soft/25',
      )}
    >
      {/* The severity indicator: a full-height bar rather than a dot, so the
          three levels are distinguishable at a glance down the list instead of
          needing to be read one row at a time. */}
      <span
        aria-hidden
        className={cn('mt-0.5 w-1 shrink-0 self-stretch rounded-full', severity.bar)}
      />

      <span className="min-w-0 flex-1">
        <span className="mb-1 flex flex-wrap items-center gap-1.5">
          <span
            className={cn(
              'rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide',
              severity.chip,
            )}
          >
            {severity.label}
          </span>
          <span className="text-[11px] font-semibold text-muted">
            {moduleLabel(row.event.module)}
          </span>
          <span className="text-[11px] text-muted">·</span>
          <span className="text-[11px] text-muted">{relativeTime(row.created_at)}</span>
          {!row.is_read && (
            <span className="ml-auto h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-label="Unread" />
          )}
        </span>

        <span
          className={cn(
            'block text-sm leading-snug text-ink',
            !row.is_read ? 'font-semibold' : 'font-medium',
          )}
        >
          {row.event.title}
        </span>

        <span className="mt-0.5 block text-xs leading-relaxed text-muted">
          {row.event.body}
        </span>

        {/* Stated only when it is true. An inventory notification names an item
            at a branch and has no screen to open — see entityPath — so it must
            not look like a dead link. */}
        {navigable && (
          <span className="mt-1 block text-[11px] font-semibold text-brand">
            Open record →
          </span>
        )}
      </span>
    </button>
  )
}

//-----------------------------------------------------
// STATES
//-----------------------------------------------------

function Skeleton() {
  return (
    <div className="space-y-3 p-4" aria-hidden>
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className="flex gap-3">
          <div className="h-12 w-1 shrink-0 animate-pulse rounded-full bg-line" />
          <div className="flex-1 space-y-2">
            <div className="h-3 w-24 animate-pulse rounded bg-line" />
            <div className="h-3.5 w-3/4 animate-pulse rounded bg-line" />
            <div className="h-3 w-full animate-pulse rounded bg-line" />
          </div>
        </div>
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center">
      <BellOff size={28} className="text-muted" />
      <p className="text-sm font-semibold text-ink">Nothing to catch up on</p>
      <p className="max-w-[15rem] text-xs text-muted">
        Alerts about delayed consignments, stock running low and payments coming
        due will appear here.
      </p>
    </div>
  )
}

//-----------------------------------------------------
// THE DRAWER
//-----------------------------------------------------

export function NotificationPanel({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const navigate = useNavigate()
  const list = useNotificationList(open)
  const markRead = useMarkRead()
  const markAllRead = useMarkAllRead()

  const sections = useMemo(() => buildSections(list.rows), [list.rows])
  const hasUnread = list.rows.some((r) => !r.is_read)

  // Escape closes, matching the nav dropdown in TopNav.
  useEffect(() => {
    if (!open) return
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null

  const handleSelect = (row: ApiNotification) => {
    // Marked read first and unconditionally — a click IS the user seeing it,
    // whether or not it has anywhere to navigate. Fire-and-forget: the
    // mutation rolls its own count back on failure, and a failed mark-read
    // must not block the navigation the user actually asked for.
    if (!row.is_read) markRead.mutate(row.id)

    const path = entityPath(row.event)
    if (path) {
      onClose()
      navigate(path)
    }
  }

  //-----------------------------------------------------
  // THE ERROR RULE: AN ERROR NEVER BLANKS THE PANEL.
  //
  // If a page failed but earlier pages loaded, the rows STAY on screen and the
  // failure shows as a strip above them. Replacing a working list with an
  // error card would throw away readable notifications to report that the next
  // twenty could not be fetched.
  //-----------------------------------------------------
  const showError = list.isError
  const showSkeleton = list.isLoading && !list.rows.length
  const showEmpty = !list.isLoading && !list.isError && !list.rows.length

  return (
    <>
      {/* Click-away. A real element rather than a document listener so the
          bell's own toggle isn't fighting it for the same click. */}
      <div
        className="animate-fade-in fixed inset-0 z-30 bg-navy-deep/20"
        onClick={onClose}
        aria-hidden
      />

      <aside
        role="dialog"
        aria-label="Notifications"
        className={cn(
          'animate-scale-in fixed right-3 top-16 z-40 flex max-h-[min(34rem,calc(100vh-5rem))] w-[min(26rem,calc(100vw-1.5rem))]',
          'flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-lg',
        )}
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-line px-4 py-3">
          <h2 className="font-display text-sm font-bold text-ink">Notifications</h2>
          {list.total > 0 && (
            <span className="text-xs text-muted">({list.total})</span>
          )}

          <div className="ml-auto flex items-center gap-1">
            {hasUnread && (
              <button
                type="button"
                onClick={() => markAllRead.mutate()}
                disabled={markAllRead.isPending}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-brand hover:bg-canvas-alt disabled:opacity-50"
              >
                <CheckCheck size={13} />
                Mark all read
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              title="Close"
              className="rounded-lg p-1.5 text-muted hover:bg-canvas-alt hover:text-ink"
            >
              <X size={15} />
            </button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {showError && (
            <div className="flex items-start gap-2 border-b border-line bg-risk-bg px-4 py-2.5 text-risk">
              <AlertCircle size={14} className="mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold">Could not load notifications</p>
                <button
                  type="button"
                  onClick={() => list.refetch()}
                  className="mt-0.5 text-[11px] font-semibold underline underline-offset-2"
                >
                  Try again
                </button>
              </div>
            </div>
          )}

          {showSkeleton && <Skeleton />}
          {showEmpty && <EmptyState />}

          {sections.map((section) => (
            <section key={section.key}>
              <h3 className="sticky top-0 z-10 bg-canvas-alt/95 px-4 py-1.5 text-[10px] font-bold uppercase tracking-wider text-muted backdrop-blur">
                {section.label}
              </h3>
              {section.groups.map((group) => (
                <div key={`${section.key}-${group.label}`}>
                  <h4 className="px-4 pb-1 pt-2.5 text-[11px] font-semibold text-muted">
                    {group.label}
                  </h4>
                  {group.rows.map((row) => (
                    <NotificationRow key={row.id} row={row} onSelect={handleSelect} />
                  ))}
                </div>
              ))}
            </section>
          ))}

          {/* A button rather than scroll-position detection: explicit, works
              with a keyboard, and cannot fire a request because a trackpad
              overscrolled. */}
          {list.hasNextPage && (
            <div className="p-3">
              <button
                type="button"
                onClick={() => list.fetchNextPage()}
                disabled={list.isFetchingNextPage}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs font-semibold text-ink hover:bg-canvas-alt disabled:opacity-60"
              >
                {list.isFetchingNextPage && <Loader2 size={13} className="animate-spin" />}
                {list.isFetchingNextPage ? 'Loading…' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  )
}
