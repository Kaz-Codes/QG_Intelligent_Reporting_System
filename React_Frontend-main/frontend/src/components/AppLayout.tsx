import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { ThemedBackground } from './ThemedBackground'
import { PAGE_DEFS } from '@/lib/pages'
import type { PageKey } from '@/theme/tokens'

/** Map the current path to its module key so each section gets its own
 * subject-themed backdrop. Longest matching path wins (so /imports-status
 * doesn't resolve to /imports). */
function moduleForPath(pathname: string): PageKey {
  const match = [...PAGE_DEFS]
    .sort((a, b) => b.path.length - a.path.length)
    .find((p) => pathname === p.path || pathname.startsWith(p.path + '/'))
  return match?.key ?? 'dashboard'
}

export function AppLayout() {
  const { pathname } = useLocation()
  const module = moduleForPath(pathname)

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar />
      {/* main is a fixed-height frame: the themed backdrop stays put while
          only the inner region scrolls, so the ambient layer reads as a
          calm background rather than scrolling away with the content. */}
      <main className="relative flex-1 overflow-hidden">
        <ThemedBackground key={module} module={module} variant="ambient" />
        <div className="relative z-10 h-full overflow-y-auto p-8">
          <div key={pathname} className="animate-fade-in-up">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  )
}
