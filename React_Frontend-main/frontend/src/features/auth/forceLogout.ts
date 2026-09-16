// Shared "kill the local session, from anywhere" helper - used by both the
// idle-timeout watcher (AuthContext.tsx) and the global 401 handler
// (main.tsx's QueryClient).
//
// A HARD redirect (window.location.href), not React Router's navigate(),
// because the two callers sit in places that don't have Router context:
// main.tsx constructs the QueryClient at module scope, before any component
// (let alone a Router) exists, and AuthProvider itself renders ABOVE
// <BrowserRouter> in the tree (main.tsx: ThemeProvider > QueryClientProvider
// > AuthProvider > App, with BrowserRouter only appearing inside App.tsx) -
// so useNavigate() is not available in either spot. A full-page reload also
// guarantees a completely fresh app + query cache, which fits the "no
// countdown, immediate and silent" idle-logout design at least as well as an
// SPA-style navigation would.
//
// Versioned: older sessions (roles, then the 5 coarse permissions, then the
// mock directory) aren't compatible with the backend's permission names, so
// this starts fresh (logged out) instead of gating the UI on stale values.
// What's cached here is only WHO the session belongs to and what the UI may
// show — the actual credential is the backend's httpOnly cookie, which
// JavaScript can't read. Clearing this key logs you out of the UI; the
// cookie itself is cleared by /auth/logout (or, for the idle/401 case here,
// simply left to expire — see the module docstring for why that's fine).
export const STORAGE_KEY = 'qgirs-user-v4'

export function forceLogout() {
  window.localStorage.removeItem(STORAGE_KEY)
  window.location.href = '/login'
}
