/**
 * Admin-action log for User Management (accounts created, permissions
 * changed, admin rights granted/revoked) — localStorage-persisted like the
 * rest of the mock auth layer, until a real backend exists.
 *
 * Scoped to what this frontend actually controls: it can't see inside
 * Operations' wizards (Imports/Logistics/Trucking Status are
 * teammate-owned and not wired to any shared persistence yet), so this is
 * an admin-action log, not a full data-entry audit trail — that needs the
 * real database.
 */

export interface LogEntry {
  id: string
  timestamp: number
  actor: string
  message: string
}

const LOG_KEY = 'qgirs-activity-log'
const MAX_ENTRIES = 200

function loadLog(): LogEntry[] {
  const raw = window.localStorage.getItem(LOG_KEY)
  return raw ? (JSON.parse(raw) as LogEntry[]) : []
}

export function logActivity(actor: string, message: string): void {
  const entries = [{ id: crypto.randomUUID(), timestamp: Date.now(), actor, message }, ...loadLog()].slice(0, MAX_ENTRIES)
  window.localStorage.setItem(LOG_KEY, JSON.stringify(entries))
}

/** Newest first. */
export function getActivityLog(): LogEntry[] {
  return loadLog()
}
