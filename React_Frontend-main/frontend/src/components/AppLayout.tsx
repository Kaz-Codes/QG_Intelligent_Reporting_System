import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { PanelLeftOpen } from 'lucide-react'
import { Sidebar } from './Sidebar'
import { ThemedBackground } from './ThemedBackground'
import { PAGE_DEFS } from '@/lib/pages'
import type { PageKey } from '@/theme/tokens'

const SIDEBAR_STORAGE_KEY = 'qgirs-sidebar-open'

/** Map the current path to its module key so each section gets its own
 * subject-themed backdrop. Longest matching path wins (so /imports-status
 * doesn't resolve to /imports). Imports Status and Logistics Status are
 * grouped under one "Operations" sidebar entry but keep their own distinct
 * theming identity, so they're resolved by their own PageKey, not
 * `dataEntry`'s. */
function moduleForPath(pathname: string): PageKey {
  if (pathname === '/imports-status' || pathname.startsWith('/imports-status/')) return 'importsStatus'
  if (pathname === '/logistics-status' || pathname.startsWith('/logistics-status/')) return 'logisticsStatus'
  const match = [...PAGE_DEFS]
    .sort((a, b) => b.path.length - a.path.length)
    .find((p) => pathname === p.path || pathname.startsWith(p.path + '/'))
  return match?.key ?? 'dashboard'
}

export function AppLayout() {
  const { pathname } = useLocation()
  const module = moduleForPath(pathname)
  const [sidebarOpen, setSidebarOpen] = useState(() => window.localStorage.getItem(SIDEBAR_STORAGE_KEY) !== 'false')

  function setOpen(open: boolean) {
    setSidebarOpen(open)
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, String(open))
  }

  return (
    <div className="relative flex h-screen overflow-hidden bg-canvas">
      {/* Backdrop now sits behind the ENTIRE shell, not just main, so the
          sidebar's glass transparency reveals the actual photo/aurora
          layer instead of the flat bg-canvas color (which was nearly the
          same white as the sidebar in light mode — that's why lowering
          the sidebar's opacity alone didn't visibly do anything before).
          Fixed + full-viewport so it doesn't scroll or resize with main. */}
      <ThemedBackground key={module} module={module} variant="ambient" className="fixed" />
      {sidebarOpen && <Sidebar onHide={() => setOpen(false)} />}
      {/* main is a fixed-height frame: only the inner region scrolls, so
          the ambient layer reads as a calm background rather than
          scrolling away with the content. */}
      <main className="relative z-10 flex-1 overflow-hidden">
        {!sidebarOpen && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            title="Show sidebar"
            className="absolute left-4 top-4 z-20 rounded-lg border border-line bg-surface p-2 text-muted shadow-sm hover:bg-canvas-alt hover:text-ink"
          >
            <PanelLeftOpen size={16} />
          </button>
        )}
        <div className="relative z-10 h-full overflow-y-auto p-8">
          <div key={pathname} className="animate-fade-in-up">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  )
}
