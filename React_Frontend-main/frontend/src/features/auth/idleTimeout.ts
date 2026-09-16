// Idle-timeout auto-logout: 30 minutes of no REAL user interaction logs the
// user out, silently - no countdown/warning modal, per the locked decision.
//
// WHAT COUNTS AS ACTIVITY, AND WHAT DOESN'T - read this before adding
// anything that might touch this file's assumptions. Only the five DOM
// events listened for below (mousemove, keydown, click, scroll, touchstart)
// count. A background data refetch, a WebSocket message arriving, a
// passively-open screen (the admin log feed included, by deliberate
// decision) do NOT count - if they did, an unattended tab could stay "active"
// forever. A future auto-refreshing widget or polling channel must not call
// sendHeartbeat() itself or attach its own activity listener; if it does,
// idle-logout silently stops working for any screen using it. See the
// matching note on the backend: only POST /auth/heartbeat (app/auth/heartbeat.py)
// is allowed to call session_activity.touch() - authenticate() deliberately
// only CHECKS idleness, so no ordinary API call (including a background
// refetch) can ever extend a session either.
//
// TWO CONSUMERS OF ONE SHARED "LAST REAL INTERACTION" CLOCK:
//   1. The heartbeat sender - throttled to once a minute, tells the backend
//      the session is still in use.
//   2. The local idle watcher - checks every ~10s whether 30 minutes have
//      passed since the last interaction, and if so, force-logs-out.
//
// CROSS-TAB SHARING, for two different reasons:
//   - The JWT cookie is shared across every tab already (a normal cookie,
//     not per-tab), so the SERVER already sees the whole session as active
//     the moment any one tab sends a heartbeat - no extra work needed there.
//   - The client-side "last interaction" timestamp is NOT automatically
//     shared, so without BroadcastChannel, a tab merely open in the
//     background (while another tab is actively used) would locally expire
//     and redirect on its own - a confusing "this tab logged out, that one
//     didn't" UX even though the account's session is still alive
//     server-side. BroadcastChannel fixes this: every tab's watcher checks
//     the most recent timestamp heard from ANY tab, not just its own.

import { sendHeartbeat } from '@/lib/api/auth'

export const IDLE_TIMEOUT_MS = 30 * 60 * 1000
const HEARTBEAT_THROTTLE_MS = 60 * 1000
const WATCH_INTERVAL_MS = 10 * 1000
// Guards the event listeners themselves, not the heartbeat call - mousemove
// fires far more often than is worth doing any work for.
const LISTENER_THROTTLE_MS = 1000

/** Starts the shared activity listener + local idle watcher. Returns a
 * teardown function. `onIdle` is expected to be forceLogout (or something
 * equivalent) - this module doesn't call it itself, so it stays decoupled
 * from how "log out" is actually performed.
 *
 * The channel and clock are created FRESH on every call (not module-level
 * singletons) and torn down in the returned cleanup - so a logout followed
 * by a new login in the same tab (no full page reload in between) gets a
 * brand new BroadcastChannel rather than trying to use one this same module
 * already closed on the previous logout, and the idle clock correctly
 * starts fresh for the new session instead of carrying over how recently
 * the PREVIOUS session's user last moved the mouse.
 */
export function startIdleTimeoutWatcher(onIdle: () => void): () => void {
  const channel = new BroadcastChannel('qgirs-activity')
  let lastActivity = Date.now()
  let lastHeartbeatSent = 0

  channel.onmessage = (event) => {
    if (typeof event.data === 'number' && event.data > lastActivity) {
      lastActivity = event.data
    }
  }

  function recordActivity() {
    const now = Date.now()
    if (now - lastActivity < LISTENER_THROTTLE_MS) return

    lastActivity = now
    channel.postMessage(now)

    if (now - lastHeartbeatSent > HEARTBEAT_THROTTLE_MS) {
      lastHeartbeatSent = now
      sendHeartbeat().catch(() => {
        // A failed heartbeat is not itself a reason to log out locally - the
        // NEXT real API call will surface a 401 if the session is genuinely
        // gone (see the global 401 handler in main.tsx). Don't compound a
        // transient network blip into an unnecessary forced logout.
      })
    }
  }

  const events: (keyof WindowEventMap)[] = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']
  events.forEach((event) => window.addEventListener(event, recordActivity, { passive: true }))

  const interval = window.setInterval(() => {
    if (Date.now() - lastActivity > IDLE_TIMEOUT_MS) {
      onIdle()
    }
  }, WATCH_INTERVAL_MS)

  return () => {
    events.forEach((event) => window.removeEventListener(event, recordActivity))
    window.clearInterval(interval)
    channel.close()
  }
}
