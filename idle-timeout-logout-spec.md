# Idle-Timeout Auto-Logout — Implementation Spec

## Decisions locked in (do not re-litigate these mid-implementation)

- **Timeout: 30 minutes of no real user interaction.**
- **No warning/countdown modal.** At the 30-minute mark the user is logged out
  and redirected to login — no "you'll be signed out in 60 seconds" prompt.
- **In-memory, single-process session store is acceptable.** This app runs as
  one NSSM-managed uvicorn process (confirmed via `server-survey.ps1` /
  `start-all.bat` — no multi-worker/load-balanced deployment). If that ever
  changes, this store needs to move to something shared (Redis, a DB table) —
  **that migration is explicitly out of scope here**, but leave a comment
  saying so at the store's definition so it isn't forgotten silently later.
- **Sessions are keyed by `jti` (a per-login session id), not by `user_id`.**
  Logging in on a second device does not reset the idle clock on the first.
- **The admin log-watching WebSocket screen does NOT exempt a user from
  idle-logout.** A screen sitting open and passively receiving live log
  updates is not "the user doing something" — an admin who opens that screen
  and walks away for 30 minutes gets logged out exactly like anyone else.

---

## Part 0 — Frontend request-loop audit (DO THIS FIRST, before writing any backend or frontend logout code)

The whole mechanism hinges on one assumption: **an authenticated HTTP request
means a real person did something.** If anything on the frontend fires
authenticated requests on a timer, independent of actual user interaction,
that assumption breaks — the backend would see a steady drip of "activity"
from a tab nobody is touching, and the idle timeout would never fire no matter
how the mechanism is built. This has to be ruled out **before** any
implementation work, not discovered afterward when idle-logout mysteriously
doesn't work.

### What's already been checked (starting point, re-verify before trusting it)

- `grep -rn "refetchInterval|setInterval|new WebSocket" src` across the whole
  frontend turned up **no `refetchInterval` and no `setInterval`** anywhere.
- The one background-refresh candidate, the notification badge
  (`useUnreadCount` in `src/lib/api/useNotifications.ts`), is configured with
  `refetchOnWindowFocus: true` and **no interval** — it only refetches on
  mount or when the tab regains focus, not on a timer while idle. This is
  safe as-is.
- Two `WebSocket` usages exist: `src/lib/api/logs.ts` (the admin live
  log-feed) and `src/lib/api/notifications.ts` (a per-user notifications
  socket, used by everyone, with reconnect-with-backoff logic on `onclose`).

### What still needs to be verified before implementation starts

1. **Does the WebSocket handshake for either socket go through
   `authenticate()` (or an equivalent cookie check) on connect?** If so, a
   socket that reconnects (network blip, server restart, an idle-connection
   timeout on the server's WS layer) counts as one authenticated event at
   reconnect time. This is very different from a *periodic* request loop
   (it's not going to fire every N seconds under normal conditions), but
   confirm reconnect isn't happening on some hidden periodic cadence before
   ruling it out.
2. **Re-run the same `grep` for `setInterval` / `refetchInterval` /
   `setTimeout` used as a recurring poll (not just a one-shot retry) across
   the whole `src/` tree**, including anything added since this spec was
   written. Pay particular attention to any dashboard "auto-refresh" feature,
   any global data-prefetching, and React Query's `staleTime`/`refetchOnMount`
   defaults on any query used in a screen likely to be left open (dashboards
   especially — these are exactly the screens someone opens and walks away
   from).
3. **Confirm there is no global axios/fetch interceptor issuing a background
   "keep-alive" or "am I still logged in" ping.** None was found in
   `src/lib/api/client.ts` (`apiFetch`/`apiFetchBlob` are plain fetch wrappers
   with no interceptor), but re-check after any changes to that file.
4. **Write down, explicitly, in a comment near the heartbeat endpoint (Part 2
   below) and near the frontend interaction listener (Part 3 below), what
   counts as "activity" and what doesn't** — so a future feature (a new
   auto-refreshing widget, a new polling notification channel) has something
   to check itself against before it accidentally becomes a silent
   keep-alive that defeats this whole feature. This is the single most likely
   way this feature quietly breaks six months from now.

**Do not proceed to Part 1 until this audit is complete and any findings are
resolved or explicitly accepted as fine.**

---

## Part 1 — Why two layers, and what each one is actually responsible for

This is worth stating plainly before the code, because the two layers do
**different, non-overlapping jobs** and conflating them leads to a broken
design:

- **The backend cannot proactively do anything to a truly idle client.**
  There is no outstanding request to reject and no way to push a "you're
  logged out" message to a tab that isn't making any requests. So the
  backend's role is purely reactive: the **next** request after 30 idle
  minutes gets rejected with a 401. If the user never makes another request
  (they just closed the laptop, say), the backend never "notices" anything —
  and that's fine, because nobody is looking at that tab anyway.
- **Only the frontend can proactively redirect an idle tab to the login
  screen while no request is happening.** This is why a client-side timer is
  necessary, not just a nice-to-have — it's the only thing that can actually
  make an unattended, genuinely idle browser tab navigate to `/login` on its
  own, since by definition nothing else is happening on that tab to trigger
  the backend's reactive check.

So: **backend = the real security boundary** (the next request from a
resumed-but-actually-idle session gets rejected, regardless of what the
frontend does or doesn't do). **Frontend = the UX** (a genuinely idle tab
navigates itself to login without waiting for the user to click something
that would trigger the 401).

---

## Part 2 — Backend implementation

### Files touched

| File | Change |
|---|---|
| `app/auth/create_token.py` | Add a `jti` (random session id) into the JWT payload at token creation. |
| `app/auth/session_activity.py` | **New file.** The in-memory `{jti: last_seen}` store and its three operations (`touch`, `is_idle`, `forget`). |
| `app/auth/authenticate_user.py` | After the JWT itself verifies, check `is_idle(jti)`; raise 401 if so. **Does NOT call `touch()`** — see Part 1, only real interaction should extend a session. |
| `app/auth/login.py` | Generate the `jti`, seed `session_activity` with an initial timestamp on login. |
| `app/auth/logout.py` | Call `forget(jti)` so a clean logout removes the entry immediately rather than letting it expire naturally. |
| `app/auth/router.py` | Register the new heartbeat route. |
| `app/auth/heartbeat.py` | **New file.** `POST /auth/heartbeat` — the *only* place that calls `touch()`. |

### `app/auth/session_activity.py` (new)

```python
"""In-memory last-activity tracking, keyed by jti (one entry per login
session, not per user — see the spec's decision on jti vs user_id keying).

SINGLE-PROCESS ONLY. This is a plain dict, not shared across processes. That
is an accepted constraint (this app runs as one uvicorn process under NSSM,
confirmed at the time this was written) — if this app is ever deployed with
more than one worker process or more than one instance behind a load
balancer, this store must move to something shared (Redis, a DB table)
BEFORE idle-logout would work correctly across processes. Do not assume this
still holds without re-checking the deployment.

Only `touch()` counts as activity. Do not call this from `authenticate()` for
every request — see Part 1 of the idle-timeout spec for why: not every
authenticated request represents a real user action (a websocket handshake,
a background refetch, a passively-open log-watching screen should not reset
this clock). The ONLY caller of touch() is the /auth/heartbeat route, which
the frontend calls only in response to real interaction events.
"""

from datetime import datetime, timedelta, timezone

IDLE_TIMEOUT = timedelta(minutes=30)

_LAST_SEEN: dict[str, datetime] = {}


def touch(jti: str) -> None:
    """Record real activity for this session. Called ONLY by /auth/heartbeat."""
    _LAST_SEEN[jti] = datetime.now(timezone.utc)


def seed(jti: str) -> None:
    """Called once at login, so a freshly-issued session has a starting
    point and isn't treated as already-idle before its first heartbeat."""
    _LAST_SEEN[jti] = datetime.now(timezone.utc)


def is_idle(jti: str) -> bool:
    """True if this session has gone more than IDLE_TIMEOUT since its last
    recorded activity. A jti with NO entry (never seeded — shouldn't happen
    for a token this code issued, but treat defensively) is NOT treated as
    idle here; that's a caller bug elsewhere, not this session's fault."""
    last = _LAST_SEEN.get(jti)
    if last is None:
        return False
    return (datetime.now(timezone.utc) - last) > IDLE_TIMEOUT


def forget(jti: str) -> None:
    """Called on explicit logout, so the entry doesn't linger until the JWT's
    own 3-hour expiry would have cleaned it up implicitly anyway."""
    _LAST_SEEN.pop(jti, None)
```

### `app/auth/create_token.py` — add `jti`

```python
from uuid import uuid4

def create_token(data: dict):
    payload = data.copy()
    payload.setdefault("jti", uuid4().hex)   # setdefault: caller may pass one explicitly
    expire = datetime.now(timezone.utc) + timedelta(hours=3)
    payload["exp"] = expire
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM), payload["jti"]
```

**This changes `create_token`'s return type** from a bare string to a
`(token, jti)` tuple. Check every existing call site of `create_token`
(currently just `login.py`) and update it — do not leave a call site
unpacking a tuple it wasn't expecting, or destructuring a string as if it
were one.

### `app/auth/login.py` — seed the session

```python
token, jti = create_token({"id": user.id})
session_activity.seed(jti)

response.set_cookie(
    key="access_token", value=token, httponly=True,
    samesite="lax", max_age=TOKEN_HOURS * 60 * 60, path="/",
)
```

### `app/auth/authenticate_user.py` — check, don't touch

```python
def authenticate(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            token = auth_header.replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")

    payload = verify_token(token)

    jti = payload.get("jti")
    if jti and session_activity.is_idle(jti):
        session_activity.forget(jti)
        raise HTTPException(status_code=401, detail="Session expired due to inactivity")

    return payload
```

The `if jti` guard matters: a token issued *before* this feature shipped
(still valid for up to 3 hours after deploy) has no `jti` claim. Don't let
that crash `authenticate()` — treat "no jti" as "can't check idleness, fall
back to the existing 3-hour expiry only," which is exactly what happens today
for those in-flight tokens. They age out naturally within 3 hours of
deployment; no migration needed.

### `app/auth/heartbeat.py` (new)

```python
@router.post("/heartbeat")
async def heartbeat(request: Request):
    payload = authenticate(request)   # 401s here exactly like any other route
    jti = payload.get("jti")
    if jti:
        session_activity.touch(jti)
    return {"status": 200}
```

Deliberately tiny — no DB call, no logging, nothing but the touch. This gets
called frequently-ish from the frontend (throttled — see Part 3), so it needs
to stay cheap.

### `app/auth/logout.py` — clean up on explicit logout

```python
payload = verify_token(token) if token else None
if payload and payload.get("jti"):
    session_activity.forget(payload["jti"])
```
(placed wherever `logout.py` already extracts the user, alongside the
existing cookie-clearing logic)

---

## Part 3 — Frontend implementation

### The core idea: one shared "last real interaction" clock, two consumers of it

1. **A listener** attaches real interaction events (`mousemove`, `keydown`,
   `click`, `scroll`, `touchstart` — throttled, not on every pixel) and
   updates a shared timestamp whenever one fires.
2. **Consumer A — the heartbeat sender.** Whenever the shared timestamp
   updates, and at least 60 seconds have passed since the last heartbeat call
   (throttle — don't call `/auth/heartbeat` on every keystroke), `POST
   /auth/heartbeat`.
3. **Consumer B — the local idle watcher.** A `setInterval` (every ~10s)
   checks `now - sharedTimestamp`; if it exceeds 30 minutes, silently clears
   local session state and redirects to `/login` — no countdown, no modal,
   per the locked decision.

### Cross-tab sharing matters, and for two different reasons

- **The JWT cookie is shared across every tab of the same browser** (it's a
  regular cookie, not per-tab). So if tab A sends a heartbeat, the **server**
  already sees the whole session (all tabs) as active — that part is correct
  automatically, no extra work needed.
- **But the client-side "last interaction" timestamp (Consumer B, the local
  watcher) is NOT automatically shared across tabs** unless you explicitly
  sync it. Without syncing, a user actively working in tab A but with tab B
  merely open in the background would have tab B's own local timer expire
  and silently redirect *that tab* to login — even though the account's
  actual session is still alive server-side (tab A kept it alive via
  heartbeats). That's a confusing, wrong-looking UX: one tab logged out,
  another still working.

**Fix: use `BroadcastChannel`** (all target browsers for this LAN app support
it; no need for a `localStorage`-event fallback unless a target browser
genuinely lacks it) so every tab's interaction listener broadcasts "I saw
activity at time T" to every other tab of the same origin, and every tab's
local watcher checks the *most recent* timestamp it has heard from any tab,
not just its own.

```typescript
// src/features/auth/idleTimeout.ts (new)

const IDLE_TIMEOUT_MS = 30 * 60 * 1000
const HEARTBEAT_THROTTLE_MS = 60 * 1000
const WATCH_INTERVAL_MS = 10 * 1000

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
  lastActivity = now
  channel.postMessage(now)

  if (now - lastHeartbeatSent > HEARTBEAT_THROTTLE_MS) {
    lastHeartbeatSent = now
    apiFetch('/auth/heartbeat', { method: 'POST' }).catch(() => {
      // A failed heartbeat is not itself a reason to log out locally — the
      // NEXT real API call will surface a 401 if the session is genuinely
      // gone (see the global 401 handler below). Don't compound a transient
      // network blip into an unnecessary forced logout.
    })
  }
}

export function startIdleTimeoutWatcher(onIdle: () => void) {
  const events: (keyof WindowEventMap)[] = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']
  events.forEach((event) => window.addEventListener(event, recordActivity, { passive: true }))

  const interval = setInterval(() => {
    if (Date.now() - lastActivity > IDLE_TIMEOUT_MS) {
      onIdle()
    }
  }, WATCH_INTERVAL_MS)

  return () => {
    events.forEach((event) => window.removeEventListener(event, recordActivity))
    clearInterval(interval)
    channel.close()
  }
}
```

`recordActivity` needs its own throttle on the *listener* side too (don't
call it on every single `mousemove` firing — attach a lightweight throttle,
e.g. only update if >1s since the last recorded activity, before this even
gets to the heartbeat-throttle check) — the sketch above throttles the
*heartbeat network call*, but the event listeners themselves firing
unthrottled on `mousemove` is wasted work; add a cheap guard at the top of
`recordActivity` (`if (now - lastActivity < 1000) return`) before the rest of
the function runs.

### Wiring it into `AuthContext.tsx`

```typescript
useEffect(() => {
  if (!user) return
  return startIdleTimeoutWatcher(() => {
    window.localStorage.removeItem(STORAGE_KEY)
    setUser(null)
    // No call to backendLogout() here — the session may already be
    // considered expired server-side by now anyway, and per the "no
    // countdown modal" decision this should be silent and immediate, not
    // wait on a network round trip before navigating away.
    navigate('/login')
  })
}, [user])
```

Only runs while `user` is set — no idle-watching machinery active on the
login screen itself.

### The global 401 handler — needed regardless of the idle timer

Even with the client-side timer working perfectly, there's a real scenario it
doesn't cover: a user's session expires server-side (idle *or* the 3-hour
absolute cap) while they're mid-interaction, and their very next API call
comes back 401. Right now, `apiFetch` just throws `ApiError` — nothing
globally catches a 401 and forces a logout; each call site would need to
handle it individually, which is fragile and easy to miss on a new screen
later.

Add one central place that does this — a TanStack Query global error handler
(since `useQuery`/`useMutation` are already in use throughout, per
`useNotifications.ts` and the various `use*Dashboard.ts` hooks) is the
natural fit:

```typescript
// wherever the QueryClient is constructed
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        forceLogout()   // same local-clear-and-redirect as the idle watcher
      }
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) {
        forceLogout()
      }
    },
  }),
})
```

`forceLogout()` should be the same function the idle watcher calls (extract
it to a shared helper rather than duplicating the clear-and-redirect logic in
two places).

---

## Edge cases — go through every one of these before calling this done

1. **Clock skew between client and server.** The client's 30-minute local
   timer and the server's 30-minute `IDLE_TIMEOUT` are independent clocks —
   they don't need to agree to the second, but if the client's clock runs
   noticeably fast, its local watcher could fire *before* the server would
   have expired the session (harmless — just an early, client-only redirect,
   server session was still fine). If the client's clock runs slow, the local
   watcher fires *late*, but the server-side check still correctly rejects
   the next request either way. The server-side check is the actual
   enforcement; the client timer being imprecise is a UX-quality issue, not a
   security one.
2. **Heartbeat itself hitting `authenticate()`.** The heartbeat route calls
   `authenticate(request)` like any other route — so if a session is
   *already* past the idle threshold when a (very late, throttled) heartbeat
   finally fires, that heartbeat call itself gets a 401 rather than reviving
   the session. Confirm this is the intended behavior (it should be — a
   session that's already expired shouldn't be revivable by one more request
   pretending to be a heartbeat) and that the frontend's heartbeat error
   handler doesn't accidentally treat a 401 *from the heartbeat call itself*
   any differently than a 401 from any other call (it shouldn't — same global
   handler, same `forceLogout()`).
3. **Multiple tabs, one logs out explicitly (manual "Log out" click).** This
   should end the session for *all* tabs, not just the one clicked — because
   `logout()` calls the real `/auth/logout` endpoint, which clears the
   server-side `jti` entry and the cookie (cookie is shared across tabs).
   Other tabs won't know immediately, but their next API call (or next
   heartbeat) will get a 401 and trigger `forceLogout()` via the global
   handler — verify this actually happens rather than those tabs silently
   sitting in a stale "logged in" UI state indefinitely until the user
   interacts with one.
4. **A tab open with `user` set but the backend restarted** (wiping the
   in-memory `_LAST_SEEN` dict). Every `jti` this app issued is gone from
   memory, but the JWTs themselves are still valid (signed, unexpired). Per
   `authenticate()`'s `if jti and session_activity.is_idle(jti)` — a `jti`
   with no entry in `_LAST_SEEN` returns `is_idle() == False` (not found ≠
   idle, per the `is_idle` implementation above), so **a backend restart does
   NOT force-logout everyone** — sessions continue working, just without idle
   enforcement until the next heartbeat re-seeds them. Confirm this is the
   desired behavior (it should be — restarting the server shouldn't be a
   surprise mass-logout event) rather than assuming the alternative
   (treating "no entry" as "expired") without checking which one is actually
   wanted.
5. **The `IDLE_TIMEOUT` constant needs to live in exactly one place** on each
   side — `session_activity.py`'s `IDLE_TIMEOUT` (backend) and
   `idleTimeout.ts`'s `IDLE_TIMEOUT_MS` (frontend) are two separate constants
   in two separate languages/codebases; they can't literally share a value.
   Keep them numerically equal (30 minutes) and comment each one pointing at
   the other, so a future change to one doesn't silently drift from the
   other.
6. **Test the admin log-feed screen specifically**, since it was called out
   as a deliberate decision: open it, don't touch mouse/keyboard for 30+
   minutes, confirm the tab gets logged out despite the WebSocket staying
   connected and receiving live log pushes the whole time. If it doesn't,
   the WebSocket connection or its message handling is doing something that
   counts as activity when it shouldn't — trace that down specifically.
7. **`BroadcastChannel` unsupported browsers.** Confirm this LAN app's actual
   target browsers all support it (virtually all modern browsers do; the
   Chrome-on-corporate-LAN case this app almost certainly targets is fine)
   before shipping without a fallback — don't add `localStorage`-event
   fallback complexity preemptively if it's genuinely unneeded here.

---

## Testing / validation

1. **Backend, in isolation:** hit `/auth/heartbeat` repeatedly (script or
   Postman) at intervals under 30 minutes — confirm the session stays valid.
   Stop for 31+ minutes, hit any authenticated route — confirm a 401 with
   `"Session expired due to inactivity"`.
2. **Frontend, in isolation:** temporarily lower `IDLE_TIMEOUT_MS` to e.g. 30
   seconds in a local branch, confirm an untouched tab redirects to `/login`
   at roughly that mark, with no console errors and no lingering
   `BroadcastChannel`/`setInterval` after the redirect (check for cleanup —
   the returned teardown function from `startIdleTimeoutWatcher` must
   actually run).
3. **Cross-tab:** open two tabs, keep interacting in tab A only, confirm tab
   B does **not** locally redirect while tab A stays active (BroadcastChannel
   sync working) — then stop touching *both* tabs, confirm both redirect at
   the same idle mark.
4. **Admin log-feed case specifically**, per edge case 6 above.
5. **Backend restart mid-session:** log in, restart the backend process,
   confirm the existing session keeps working (per edge case 4) rather than
   immediately 401ing.
6. **Explicit logout from one tab with a second tab open:** confirm the
   second tab gets forced out on its next request/heartbeat, per edge case 3.
7. **Re-run the Part 0 frontend audit one more time** against the final code,
   post-implementation — confirm the new heartbeat call itself doesn't
   accidentally become the very kind of "silent periodic request" Part 0
   warned about (it shouldn't, since it's gated behind real interaction
   events and throttled — but verify the throttle is actually working and
   not, say, resetting on every render for some unrelated reason).

---

## Definition of done

- [ ] Part 0 audit complete, findings resolved or explicitly accepted.
- [ ] `create_token` returns `(token, jti)`; every call site updated.
- [ ] `session_activity.py` created with `touch`/`seed`/`is_idle`/`forget`.
- [ ] `authenticate()` checks idleness (doesn't touch); `login.py` seeds;
      `logout.py` forgets; both guard against a missing `jti` (pre-deploy tokens).
- [ ] `/auth/heartbeat` route added, is the *only* caller of `touch()`.
- [ ] Frontend: shared cross-tab activity clock via `BroadcastChannel`,
      throttled heartbeat sender, local silent-redirect watcher, no modal.
- [ ] Global 401 handler added (QueryCache/MutationCache `onError`), shared
      `forceLogout()` used by both the idle watcher and the 401 handler.
- [ ] All edge cases in this doc individually verified, not just "looks
      right."
- [ ] No schema/database changes anywhere in the diff.
