import { NavLink } from 'react-router-dom'
import { Moon, Sun, LogOut } from 'lucide-react'
import { useAuth } from '@/features/auth/AuthContext'
import { useTheme } from '@/theme/ThemeContext'
import { pagesForRole } from '@/lib/roleAccess'
import { PAGE_DEFS } from '@/lib/pages'
import { cn } from '@/lib/utils'
import logo from '@/assets/qadri_logo_transparent.png'

export function Sidebar() {
  const { user, logout } = useAuth()
  const { dark, toggle } = useTheme()
  const allowed = pagesForRole(user?.role)
  const visiblePages = PAGE_DEFS.filter((p) => allowed.includes(p.key))

  return (
    <aside className="flex h-screen w-64 shrink-0 flex-col border-r border-line bg-sidebar px-4 py-6">
      <div className="flex flex-col items-center gap-2 pb-4">
        <img src={logo} alt="Qadri Group" className="h-12 w-12 object-contain" />
        <div className="text-center">
          <h2 className="font-display text-lg font-bold text-navy">QG-IRS</h2>
          <p className="text-xs font-semibold text-gold">Intelligent Reporting System</p>
        </div>
      </div>

      <button
        type="button"
        onClick={toggle}
        className="mb-4 flex items-center justify-center gap-2 rounded-lg border border-line py-2 text-sm text-ink hover:bg-canvas-alt"
      >
        {dark ? <Moon size={16} /> : <Sun size={16} />}
        {dark ? 'Dark mode' : 'Light mode'}
      </button>

      <nav className="flex flex-1 flex-col gap-1">
        {visiblePages.map(({ key, label, path, icon: Icon }) => (
          <NavLink
            key={key}
            to={path}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand text-white shadow-sm'
                  : 'text-ink hover:bg-canvas-alt',
              )
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      {user && (
        <div className="mt-4 flex items-center justify-between rounded-lg border border-line px-3 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">{user.name}</p>
            <p className="truncate text-xs capitalize text-muted">{user.role}</p>
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
    </aside>
  )
}
