import { apiFetch, BASE_URL } from './client'

/**
 * The activity log from the real backend (`GET /logs/`, admin-only).
 *
 * Nothing here writes a log. An HTTP middleware on the backend records every
 * data-changing request (POST/PUT/PATCH/DELETE) against the acting user, and
 * login/logout write their own rows — so the log is a true server-side audit
 * trail rather than something the UI has to remember to append to.
 *
 * Rows come back newest-first. `detail` on the row is just "POST /users/", so
 * `describeLog()` builds the human sentence the screen shows.
 */

interface BackendLog {
  id: number
  user_id: number | null
  username: string | null
  action: string
  method: string | null
  path: string | null
  entity_type: string | null
  entity_id: number | null
  status_code: number | null
  created_at: string | null
}

export interface ActivityLogEntry {
  id: number
  userId: number | null
  username: string | null
  action: string
  method: string | null
  path: string | null
  entityType: string | null
  entityId: number | null
  statusCode: number | null
  createdAt: string | null
  /** The request failed — still logged, but shouldn't read as if it worked. */
  failed: boolean
}

interface Envelope<T> {
  status: number
  message: string
  data: T
}

const toEntry = (l: BackendLog): ActivityLogEntry => ({
  id: l.id,
  userId: l.user_id,
  username: l.username,
  action: l.action,
  method: l.method,
  path: l.path,
  entityType: l.entity_type,
  entityId: l.entity_id,
  statusCode: l.status_code,
  createdAt: l.created_at,
  failed: l.status_code != null && l.status_code >= 400,
})

/** Newest first. `userId` narrows to one account; `limit` is capped at 500 by
 *  the backend (anything outside 1–500 falls back to 100). */
export async function listLogs(params: { userId?: number; limit?: number } = {}): Promise<ActivityLogEntry[]> {
  const query = new URLSearchParams()
  if (params.userId != null) query.set('user_id', String(params.userId))
  if (params.limit != null) query.set('limit', String(params.limit))
  const qs = query.toString()

  const res = await apiFetch<Envelope<BackendLog[]>>(`/logs/${qs ? `?${qs}` : ''}`)
  return (res.data ?? []).map(toEntry)
}

//-----------------------------------------------------
// THE LIVE FEED (admin only)
//
// `/logs/ws` streams EVERY logged action as it happens; `/logs/ws/{id}` streams
// just one user's. Both authenticate from the same session cookie the REST
// calls use — the browser attaches it to the handshake automatically, which is
// why there is no token to pass here. A non-admin is closed before the
// handshake completes.
//-----------------------------------------------------

function socketUrl(path: string): string {
  // The API base is http(s); the socket has to be ws(s) on the same origin.
  const base = BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '')
  return `${base}${path}`
}

/**
 * Subscribe to live activity. Pass a `userId` to follow one account, or omit it
 * for everything. Returns an unsubscribe function — call it on unmount, or the
 * socket keeps the connection (and the server-side watcher) alive.
 *
 * Reconnects with a small backoff, so a server restart or a dropped Wi-Fi
 * connection recovers on its own instead of silently going stale.
 */
export function subscribeToLogs(
  onEntry: (entry: ActivityLogEntry) => void,
  options: { userId?: number; onStatus?: (connected: boolean) => void } = {},
): () => void {
  const path = options.userId != null ? `/logs/ws/${options.userId}` : '/logs/ws'

  let socket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let attempts = 0
  let closed = false

  const open = () => {
    if (closed) return

    socket = new WebSocket(socketUrl(path))

    socket.onopen = () => {
      attempts = 0
      options.onStatus?.(true)
    }

    socket.onmessage = (event) => {
      try {
        onEntry(toEntry(JSON.parse(event.data) as BackendLog))
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

// The action words the backend records (app/enums.py LogAction), as something
// that reads like a sentence.
const ACTION_VERB: Record<string, string> = {
  Login: 'logged in',
  Logout: 'logged out',
  Create: 'created',
  Update: 'updated',
  Delete: 'deleted',
  Revert: 'reverted',
  Restore: 'restored',
  Verify: 'verified',
  'Status change': 'changed the status of',
  'ETA revision': 'revised the ETA of',
}

// entity_type is the first path segment, so it reads like a URL. Name the ones
// we know; anything else falls through as-is.
const ENTITY_NOUN: Record<string, string> = {
  users: 'account',
  consignments: 'import consignment',
  logistics: 'logistics order',
  trucking: 'trucking job',
  masters: 'master record',
  reports: 'report',
  auth: 'session',
}

/** A readable sentence for one log row — "created account #5". */
export function describeLog(entry: ActivityLogEntry): string {
  const verb = ACTION_VERB[entry.action] ?? entry.action.toLowerCase()

  // Login/logout have no entity of their own.
  if (entry.action === 'Login' || entry.action === 'Logout') return verb

  const noun = entry.entityType ? (ENTITY_NOUN[entry.entityType] ?? entry.entityType) : null
  if (!noun) return verb

  return `${verb} ${noun}${entry.entityId != null ? ` #${entry.entityId}` : ''}`
}
