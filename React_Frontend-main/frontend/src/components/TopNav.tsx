import { useState, useRef, useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Moon, Sun, LogOut, ChevronDown } from 'lucide-react'
import { useAuth } from '@/features/auth/AuthContext'
import { useTheme } from '@/theme/ThemeContext'
import { pagesForUser } from '@/lib/roleAccess'
import { PAGE_DEFS, type PageDef } from '@/lib/pages'
import { cn } from '@/lib/utils'
import logo from '@/assets/qadri_logo_transparent.webp'

/** Top-bar analogue of the old sidebar's collapsible group — Operations'
 * two independent route trees don't fit as a single link, so they show as
 * a small dropdown menu instead of an inline expand. */
function GroupNavItem({ item }: { item: PageDef & { children: NonNullable<PageDef['children']> } }) {
  const { pathname } = useLocation()
  const childActive = item.children.some((c) => pathname === c.path || pathname.startsWith(c.path + '/'))
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const Icon = item.icon

  // Close on outside click / Escape instead of onBlur — onBlur fired the
  // instant focus left the button (i.e. right as a child NavLink was
  // clicked), so the menu unmounted before the click could register as a
  // navigation. This only closes for interaction truly outside the group.
  useEffect(() => {
    if (!open) return
    function handlePointerDown(e: PointerEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          childActive ? 'bg-brand text-on-brand shadow-sm' : 'text-ink hover:bg-canvas-alt',
        )}
      >
        <Icon size={16} />
        {item.label}
        <ChevronDown size={13} className={cn('transition-transform duration-200', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="animate-scale-in absolute left-0 top-full z-20 mt-1 flex w-48 flex-col gap-1 rounded-xl border border-line bg-surface p-1.5 shadow-lg">
          {item.children.map((child) => (
            <NavLink
              key={child.path}
              to={child.path}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                cn(
                  'rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-brand text-on-brand' : 'text-ink hover:bg-canvas-alt',
                )
              }
            >
              {child.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )
}

/** Replaces the left sidebar: one slim row (logo, nav links, dark-mode
 * toggle, user + logout) instead of a full-height rail — frees up screen
 * width for content and reads as a more modern SaaS shell now that the app
 * is down to five top-level destinations. Same glass treatment as every
 * card (see ui/card.tsx) so it sits quietly over the themed photo backdrop. */
export function TopNav() {
  const { user, logout } = useAuth()
  const { dark, toggle } = useTheme()
  const allowed = pagesForUser(user)
  const visiblePages = PAGE_DEFS.filter((p) => allowed.includes(p.key))

  return (
    <header
      className={cn(
        'relative z-20 flex h-16 shrink-0 items-center gap-5 border-b-2 border-line/80 bg-sidebar/25 px-5 dark:border-line/45 dark:bg-sidebar/38',
        'shadow-[inset_0_-1px_0_rgba(255,255,255,0.5)] dark:shadow-[inset_0_-1px_0_rgba(255,255,255,0.06)]',
      )}
    >
      <div className="flex shrink-0 items-center gap-2.5">
        <img src={logo} alt="Qadri Group" className="h-8 w-8 object-contain" />
        <div className="leading-tight">
          <p className="font-display text-sm font-bold text-navy">QG-IRS</p>
          <p className="text-[10px] font-bold text-brand">Intelligent Reporting System</p>
        </div>
      </div>

      <nav className="flex flex-1 items-center gap-1">
        {visiblePages.map((page) => {
          if (page.children) {
            return <GroupNavItem key={page.key} item={page as PageDef & { children: NonNullable<PageDef['children']> }} />
          }
          const Icon = page.icon
          return (
            <NavLink
              key={page.key}
              to={page.path}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-brand text-on-brand shadow-sm' : 'text-ink hover:bg-canvas-alt',
                )
              }
            >
              <Icon size={16} />
              {page.label}
            </NavLink>
          )
        })}
      </nav>

      <button
        type="button"
        onClick={toggle}
        title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
        className="shrink-0 rounded-lg p-2 text-muted hover:bg-canvas-alt hover:text-ink"
      >
        {dark ? <Moon size={17} /> : <Sun size={17} />}
      </button>

      {user && (
        <div className="flex shrink-0 items-center gap-2 border-l border-line pl-4">
          <div className="text-right leading-tight">
            <p className="max-w-[10rem] truncate text-sm font-semibold text-ink">{user.name}</p>
            <p className="truncate text-xs text-muted">{user.isAdmin ? 'Admin' : 'Member'}</p>
          </div>
          <button
            type="button"
            onClick={() => logout()}
            title="Log out"
            className="shrink-0 rounded-lg p-2 text-muted hover:bg-canvas-alt hover:text-risk"
          >
            <LogOut size={16} />
          </button>
        </div>
      )}
    </header>
  )
}
