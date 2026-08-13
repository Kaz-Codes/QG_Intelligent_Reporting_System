import { Outlet, useLocation } from 'react-router-dom'
import { TopNav } from './TopNav'
import { ThemedBackground } from './ThemedBackground'
import { ActiveModuleProvider, useActiveModuleOverride } from './ActiveModule'
import { PAGE_DEFS } from '@/lib/pages'
import type { PageKey } from '@/theme/tokens'

/** Map the current path to its module key so each section gets its own
 * subject-themed backdrop. Longest matching path wins (so /imports-status
 * doesn't resolve to /imports). Imports Status, Logistics Status, and
 * Trucking Status are grouped under one "Operations" nav entry but keep
 * their own distinct theming identity, so they're resolved by their own
 * PageKey, not `dataEntry`'s. */
function moduleForPath(pathname: string): PageKey {
  if (pathname === '/imports-status' || pathname.startsWith('/imports-status/')) return 'importsStatus'
  if (pathname === '/logistics-status' || pathname.startsWith('/logistics-status/')) return 'logisticsStatus'
  if (pathname === '/trucking-status' || pathname.startsWith('/trucking-status/')) return 'truckingStatus'
  const match = [...PAGE_DEFS]
    .sort((a, b) => b.path.length - a.path.length)
    .find((p) => pathname === p.path || pathname.startsWith(p.path + '/'))
  return match?.key ?? 'dashboard'
}

export function AppLayout() {
  return (
    <ActiveModuleProvider>
      <AppLayoutShell />
    </ActiveModuleProvider>
  )
}

/** Split from AppLayout so it can read the override via context — a
 * provider can't consume the context it itself creates. */
function AppLayoutShell() {
  const { pathname } = useLocation()
  const override = useActiveModuleOverride()
  const module = override ?? moduleForPath(pathname)

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-canvas">
      {/* Backdrop sits behind the entire shell (nav bar included) so its
          glass transparency reveals the actual photo/aurora layer. Fixed +
          full-viewport so it doesn't scroll or resize with main. */}
      <ThemedBackground key={module} module={module} variant="ambient" className="fixed" />
      <TopNav />
      {/* main is a fixed-height frame: only the inner region scrolls, so
          the ambient layer reads as a calm background rather than
          scrolling away with the content. */}
      <main className="relative z-10 flex-1 overflow-hidden">
        <div className="relative z-10 h-full overflow-y-auto p-8">
          {/* min-h-full (not h-full): most pages just size to their content
              and this is a no-op for them, but it gives a page that wants to
              pin something to the bottom (Assistant's input bar) a real
              height to anchor a `sticky` element against — without it, the
              nearest ancestor with a resolvable height is several levels up
              and a `sticky bottom-0` here only starts pinning once the box
              already overflows, not before. */}
          <div key={pathname} className="animate-fade-in-up min-h-full">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  )
}
