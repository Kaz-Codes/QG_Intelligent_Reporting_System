import { useState } from 'react'
import { Bell } from 'lucide-react'

import { useNotificationSocket, useUnreadCount } from '@/lib/api/useNotifications'
import { cn } from '@/lib/utils'
import { NotificationPanel } from './NotificationPanel'

/**
 * The header bell and its unread badge.
 *
 * THIS COMPONENT MUST NEVER TAKE THE HEADER DOWN WITH IT. It sits in TopNav,
 * above every route in the app, so anything that throws here blanks the whole
 * shell. It is written so there is nothing to throw:
 *
 *   * useUnreadCount returns a number, never an error — a failed fetch reads
 *     as 0, which renders as a bell with no badge. See useNotifications.ts.
 *   * useNotificationSocket swallows its own failures and only reports a
 *     boolean. A backend with no websocket support, a proxy that strips the
 *     upgrade, an offline laptop: all of them mean "not connected", not
 *     "crash".
 *   * The panel is only mounted while open, so its list query cannot fail on
 *     a page where nobody asked for it.
 *
 * The badge caps at "9+": past that the exact figure is noise, and a
 * three-digit count would resize the header.
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const { count } = useUnreadCount()

  // Live updates. Deliberately not awaited or gated on — if the socket never
  // connects, useUnreadCount's refetch-on-focus still keeps the badge honest,
  // and the panel still loads over HTTP when opened. The socket only makes it
  // prompt.
  const { connected } = useNotificationSocket()

  const label = count > 0 ? `Notifications (${count} unread)` : 'Notifications'

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={
          connected
            ? label
            : `${label} — live updates unavailable, refreshes when you return to this tab`
        }
        aria-label={label}
        className={cn(
          'relative shrink-0 rounded-lg p-2 transition-colors',
          open ? 'bg-canvas-alt text-ink' : 'text-muted hover:bg-canvas-alt hover:text-ink',
        )}
      >
        <Bell size={17} />

        {/* Hidden entirely at zero — a badge reading "0" is noise that trains
            people to stop looking at the bell. */}
        {count > 0 && (
          <span
            className={cn(
              'absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center',
              'rounded-full bg-risk px-1 text-[10px] font-bold leading-none text-white',
            )}
          >
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      <NotificationPanel open={open} onClose={() => setOpen(false)} />
    </>
  )
}
