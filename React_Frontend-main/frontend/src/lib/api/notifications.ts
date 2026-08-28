import { ApiError, apiFetch, BASE_URL } from './client'
import { getConsignment } from './imports'
import { getLogisticsOrder } from './logistics'
import { getTruckingJob } from './trucking'

/**
 * Notifications against the real backend — `/notifications`.
 *
 * Transport only, the same split imports.ts follows: query building, the
 * response envelope, and the websocket subscription. Grouping, relative time
 * and severity styling belong to the panel, not here.
 *
 * The notifications module answers with `{ status_code, detail, data,
 * pagination }` — the data-module envelope, not the accounts/logs
 * `{ status, message, data }` one.
 */

export type NotificationSeverity = 'critical' | 'important' | 'info'

/** app/enums.py NotificationModule. */
export type NotificationModule =
  | 'imports'
  | 'logistics'
  | 'trucking'
  | 'inventory'
  | 'system'

export interface ApiNotificationEvent {
  id: number
  event_type: string
  severity: string
  tier: string
  module: string
  title: string
  body: string
  /** Polymorphic and deliberately not a foreign key on the backend — see
   *  app/notifications/models.py. Present only for events that concern one
   *  record; `stock_item` has no detail screen, so it does not navigate. */
  entity_type: string | null
  entity_id: number | null
  branch: string | null
  payload: Record<string, unknown>
  created_at: string | null
}

/** One row of the panel: the recipient's own read state, plus its event. */
export interface ApiNotification {
  id: number
  channel: string
  status: string
  read_at: string | null
  is_read: boolean
  created_at: string | null
  event: ApiNotificationEvent
}

interface ListEnvelope {
  status_code: number
  detail: string
  data: ApiNotification[]
  pagination: {
    page: number
    page_size: number
    total: number
    total_pages: number
  }
}

interface UnreadEnvelope {
  status_code: number
  detail: string
  data: { unread: number }
}

export interface NotificationQuery {
  page?: number
  pageSize?: number
  unreadOnly?: boolean
  module?: string
}

export const NOTIFICATION_PAGE_SIZE = 20

export async function listNotifications(query: NotificationQuery = {}) {
  const params = new URLSearchParams()

  if (query.page != null) params.set('page', String(query.page))
  if (query.pageSize != null) params.set('page_size', String(query.pageSize))
  if (query.unreadOnly) params.set('unread_only', 'true')
  if (query.module) params.set('module', query.module)

  const res = await apiFetch<ListEnvelope>(`/notifications/?${params.toString()}`)
  return { rows: res.data ?? [], pagination: res.pagination }
}

/** The badge. One indexed COUNT on the backend — the hottest call in the
 *  feature, so it is deliberately separate from the list and fetches no rows. */
export async function fetchUnreadCount(): Promise<number> {
  const res = await apiFetch<UnreadEnvelope>('/notifications/unread-count')
  return res.data?.unread ?? 0
}

/** Idempotent: marking an already-read notification succeeds and leaves the
 *  original read_at alone, so a double-click is not an error. A delivery that
 *  is not the caller's answers 404 — identically to one that does not exist. */
export async function markNotificationRead(id: number): Promise<void> {
  await apiFetch(`/notifications/${id}/read`, { method: 'POST' })
}

export async function markAllNotificationsRead(): Promise<number> {
  const res = await apiFetch<{ data: { updated: number } }>(
    '/notifications/read-all',
    { method: 'POST' },
  )
  return res.data?.updated ?? 0
}

//-----------------------------------------------------
// THE LIVE FEED
//
// Same shape as subscribeToLogs in logs.ts — the cookie rides the handshake
// automatically, so there is no token to pass, and a caller that fails auth is
// closed before the handshake completes.
//
// ONE DIFFERENCE FROM THE LOG SOCKET: there is no id in the path. The server
// binds the socket to the id in the caller's own token, so a user can only
// ever receive their own notifications — see app/notifications/manager.py.
//
// THE SOCKET IS AN OPTIMISATION, NEVER THE SOURCE OF TRUTH. If it never
// connects, the badge still refetches on window focus and the panel still
// loads over HTTP; the only thing lost is promptness. Nothing here throws
// into React — a frame that will not parse is dropped and the feed carries on.
//-----------------------------------------------------

function socketUrl(path: string): string {
  // The API base is http(s); the socket has to be ws(s) on the same origin.
  const base = BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '')
  return `${base}${path}`
}

export function subscribeToNotifications(
  onEvent: (event: ApiNotificationEvent) => void,
  options: { onStatus?: (connected: boolean) => void } = {},
): () => void {
  let socket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let attempts = 0
  let closed = false

  const open = () => {
    if (closed) return

    try {
      socket = new WebSocket(socketUrl('/notifications/ws'))
    } catch {
      // Constructing the socket can throw outright on a malformed URL or a
      // blocked mixed-content upgrade. Retry on the same backoff rather than
      // letting it escape into the component that called subscribe.
      const delay = Math.min(1000 * 2 ** attempts, 15000)
      attempts += 1
      retryTimer = setTimeout(open, delay)
      return
    }

    socket.onopen = () => {
      attempts = 0
      options.onStatus?.(true)
    }

    socket.onmessage = (event) => {
      try {
        onEvent(JSON.parse(event.data) as ApiNotificationEvent)
      } catch {
        // A frame we can't parse shouldn't kill the feed.
      }
    }

    socket.onclose = () => {
      options.onStatus?.(false)
      if (closed) return
      // 1s, 2s, 4s … capped at 15s.
      const delay = Math.min(1000 * 2 ** attempts, 15000)
      attempts += 1
      retryTimer = setTimeout(open, delay)
    }

    // onerror is always followed by onclose, which already schedules the retry.
    socket.onerror = () => socket?.close()
  }

  open()

  return () => {
    closed = true
    if (retryTimer) clearTimeout(retryTimer)
    socket?.close()
  }
}

//-----------------------------------------------------
// PRESENTATION HELPERS
//
// Here rather than in the panel because the bell's tooltip and the panel rows
// both need them, and because the entity mapping has to agree with App.tsx's
// routes in exactly one place.
//-----------------------------------------------------

/** Gates an unknown severity to a known one. The backend stores severity as a
 *  free String column (enums.py keeps them out of the DB type system on
 *  purpose), so an unrecognised value must render as something rather than
 *  crash a row — the same defensive read importsMap.ts applies to enums. */
export function toSeverity(value: string | null | undefined): NotificationSeverity {
  if (value === 'critical' || value === 'important' || value === 'info') return value
  return 'info'
}

const MODULE_LABELS: Record<string, string> = {
  imports: 'Imports',
  logistics: 'Logistics',
  trucking: 'Trucking',
  inventory: 'Inventory',
  system: 'System',
}

export function moduleLabel(value: string | null | undefined): string {
  if (!value) return 'General'
  return MODULE_LABELS[value] ?? value
}

/** Where clicking "Open record" goes, or null if the notification has no
 *  record to open.
 *
 *  `stock_item` deliberately returns null. CHECKED: App.tsx has no per-item
 *  inventory route at all — Inventory is a tab inside /dashboard, and an
 *  inventory notification identifies its subject by item code AND branch
 *  (rank is per branch, see the catalogue), which no route takes. So those
 *  rows mark themselves read and show no action, rather than offering a
 *  control that goes nowhere. Keep this in step with App.tsx.
 *
 *  Null here is what the panel uses to decide whether to render the action at
 *  all, so the difference is visible BEFORE the click. */
export function entityPath(event: ApiNotificationEvent): string | null {
  if (event.entity_id == null) return null

  switch (event.entity_type) {
    case 'consignment':
      return `/imports-status/${event.entity_id}`
    case 'logistics_order':
      return `/logistics-status/${event.entity_id}`
    case 'trucking_job':
      return `/trucking-status/${event.entity_id}`
    default:
      return null
  }
}

//-----------------------------------------------------
// IS THE RECORD STILL THERE?
//
// A notification outlives the thing it is about. The event keeps its rendered
// title and body for ever (that is the point — see models.py), but the
// consignment it names can be gone by the time somebody clicks.
//
// So "Open record" CHECKS BEFORE IT NAVIGATES, and on failure the panel says
// so in the row and stays put. The alternative — navigate and let the detail
// page work it out — does land on a "not found" screen rather than a blank
// error, because all three detail views handle a 404 properly. But it throws
// the user out of the panel to tell them there is nothing to see, losing the
// rest of the list they were working through.
//
// NOTE ON SOFT DELETES: a deleted record still resolves 'ok' here, and that
// is correct. Nothing in this system is hard-deleted (every table has
// is_deleted) and the detail routes deliberately still serve those rows, so
// the record genuinely does still exist and is still worth opening — an
// admin can undo the delete from it. 'missing' therefore means an id that
// resolves to nothing at all.
//-----------------------------------------------------

export type EntityAvailability = 'ok' | 'missing' | 'forbidden' | 'error'

export async function checkEntityAvailable(
  event: ApiNotificationEvent,
): Promise<EntityAvailability> {
  const id = event.entity_id
  if (id == null) return 'missing'

  // The module's own getter, not a re-spelled URL — one definition of where
  // each record lives.
  const fetchers: Record<string, (id: number) => Promise<unknown>> = {
    consignment: getConsignment,
    logistics_order: getLogisticsOrder,
    trucking_job: getTruckingJob,
  }

  const fetcher = event.entity_type ? fetchers[event.entity_type] : undefined
  if (!fetcher) return 'missing'

  try {
    await fetcher(id)
    return 'ok'
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.status === 404) return 'missing'
      // Permissions are evaluated when the delivery row is WRITTEN, so a
      // permission revoked afterwards leaves a readable notification pointing
      // at a record the user may no longer open. Worth telling apart from a
      // deleted record — they need different things from whoever they ask.
      if (err.status === 403) return 'forbidden'
    }
    return 'error'
  }
}

/** "just now" / "5m ago" / "2h ago" / "3d ago", then an absolute date.
 *
 *  Past a week a relative time stops being useful — "23d ago" makes the reader
 *  do arithmetic — so it switches to the date itself. */
export function relativeTime(iso: string | null): string {
  if (!iso) return ''

  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''

  const seconds = Math.floor((Date.now() - then) / 1000)

  // A clock skew between server and browser can make a fresh notification
  // look like it arrives from the future; show it as new rather than negative.
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`

  return new Date(iso).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** "Today" / "Yesterday" / "12 Aug 2026" — the day-group heading. */
export function dayGroupLabel(iso: string | null): string {
  if (!iso) return 'Earlier'

  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'Earlier'

  // Compared on local calendar days, not on elapsed hours: something sent at
  // 23:50 must read "Yesterday" at 00:10, not "Today".
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const days = Math.round((startOfDay(new Date()) - startOfDay(date)) / 86400000)

  if (days <= 0) return 'Today'
  if (days === 1) return 'Yesterday'

  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}
