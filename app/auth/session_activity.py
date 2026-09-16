"""In-memory last-activity tracking, keyed by jti (one entry per login
session, not per user - logging in on a second device must not reset the
idle clock on the first).

SINGLE-PROCESS ONLY. This is a plain dict, not shared across processes. That
is an accepted constraint (this app runs as one NSSM-managed uvicorn process,
confirmed via server-survey.ps1 / start-all.bat - no multi-worker/load-balanced
deployment). If this app is ever deployed with more than one worker process or
more than one instance behind a load balancer, this store must move to
something shared (Redis, a DB table) BEFORE idle-logout would work correctly
across processes. That migration is out of scope here - do not assume this
still holds without re-checking the deployment.

Only touch() counts as activity. Do not call this from authenticate() for
every request: not every authenticated request represents a real user action
(a websocket handshake, a background refetch, a passively-open log-watching
screen should not reset this clock). The ONLY caller of touch() is the
/auth/heartbeat route, which the frontend calls only in response to real
interaction events.
"""

from datetime import datetime, timedelta, timezone

# Keep numerically equal to idleTimeout.ts's IDLE_TIMEOUT_MS on the frontend -
# the two are separate constants in separate languages and can't literally
# share a value, so a change to one must be mirrored in the other by hand.
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
    recorded activity. A jti with NO entry (never seeded - shouldn't happen
    for a token this code issued, but treat defensively, e.g. after a backend
    restart wipes this dict) is NOT treated as idle here; that's a caller
    concern elsewhere; not this session's fault, and a restart should not be
    a surprise mass-logout event."""
    last = _LAST_SEEN.get(jti)
    if last is None:
        return False
    return (datetime.now(timezone.utc) - last) > IDLE_TIMEOUT


def forget(jti: str) -> None:
    """Called on explicit logout, so the entry doesn't linger until the JWT's
    own 3-hour expiry would have cleaned it up implicitly anyway."""
    _LAST_SEEN.pop(jti, None)
