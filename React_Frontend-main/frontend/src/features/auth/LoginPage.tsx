import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import {
  ShieldCheck, Sparkles, Sun, Moon,
  FileText, Search, Target, TrendingUp, LayoutDashboard, Bot,
} from 'lucide-react'
import { useAuth } from './AuthContext'
import { useTheme } from '@/theme/ThemeContext'
import { defaultPathForUser } from '@/lib/pages'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ThemedBackground } from '@/components/ThemedBackground'
import logo from '@/assets/qadri_logo_transparent.png'

// Each capability gets its own accent (drawn from the app's existing
// module-accent palette) instead of one uniform color — reads as a set of
// distinct features rather than a repeated template.
const CAPABILITIES = [
  { icon: FileText, label: 'Descriptive Reporting', hint: 'What happened', color: '#4F46E5' },
  { icon: Search, label: 'Diagnostic Reporting', hint: 'Why it happened', color: '#0EA5E9' },
  { icon: Target, label: 'Prescriptive Reporting', hint: 'What to do next', color: '#8B5CF6' },
  { icon: TrendingUp, label: 'Forecasting Reporting', hint: "What's coming", color: '#10B981' },
  { icon: LayoutDashboard, label: 'Dashboards', hint: 'Live, at a glance', color: '#06B6D4' },
  { icon: Bot, label: 'AI Chatbot', hint: 'Ask in plain language', color: '#F59E0B' },
] as const

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const { dark, toggle } = useTheme()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) {
    // Land on Bot (Assistant) by default post-login, not a hardcoded page —
    // unless the user was bounced here from a specific page they tried to
    // visit directly (location.state.from), in which case send them back there.
    const redirectTo = (location.state as { from?: string } | null)?.from ?? defaultPathForUser(user)
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden">
      {/* Full-page photo backdrop — same static-image, no-blur/no-animation
          treatment as Dashboard/Logistics/Imports (see ThemedBackground's
          ModulePhoto). Fixed so it doesn't move/resize as content lays out. */}
      <ThemedBackground module="login" className="fixed" />
      {/* The photo's brightest patch is the open sky between its two busy
          edges (port left, factory right) — exactly where the gap between
          the two cards lands on a wide screen, so it reads as an
          uncomfortable blown-out void instead of ambient depth. A centered
          radial dimmer tones it down without touching the busy edges. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-[5]"
        style={{ background: 'radial-gradient(55% 50% at 50% 40%, rgba(15,23,42,0.28), transparent 72%)' }}
      />

      {/* Top bar */}
      <div className="relative z-10 flex h-16 shrink-0 items-center justify-between border-b border-line/70 bg-surface/70 px-6 backdrop-blur-md">
        <div className="flex items-center gap-2.5">
          <img src={logo} alt="Qadri Group" className="h-7 w-7 object-contain" />
          <div className="leading-tight">
            <p className="font-display text-sm font-extrabold text-navy">QG-IRS</p>
            <p className="text-[11px] text-muted">Qadri Group</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={toggle}
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            className="flex h-8 w-8 items-center justify-center rounded-full border border-line text-muted transition-colors hover:bg-canvas-alt hover:text-ink"
          >
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </button>
          <span className="rounded-full border border-line px-3 py-1 text-xs font-medium text-muted">
            Internal system
          </span>
        </div>
      </div>

      {/* max-w caps how far the two cards can spread apart on wide screens
          — without it they hug the viewport edges and the gap between them
          (the photo's brightest patch) grows just as wide as the monitor. */}
      <div className="relative z-10 mx-auto grid w-full max-w-6xl flex-1 grid-cols-1 md:grid-cols-2">
        {/* Left: copy panel. A floating frosted-glass card (like every other
            page's Panel, just with backdrop-blur here — one static card on
            a static image costs one blur pass, not a per-frame one, so it's
            not the earlier many-cards-plus-animated-blobs lag), not a
            wall-to-wall scrim — the photo stays visible around it on every
            side, top to bottom, not just past some fade line. */}
        <div className="flex items-center px-6 py-12 md:px-10 lg:px-16">
          <div
            className="animate-fade-in-up w-full max-w-xl rounded-[28px] border border-white/40 bg-surface/78 p-8 backdrop-blur-xl dark:border-white/10 dark:bg-surface/72 lg:p-10"
            style={{ boxShadow: '0 30px 70px -20px rgba(79,70,229,0.35), 0 10px 30px -10px rgba(0,0,0,0.15)' }}
          >
            <span className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-brand/25 bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">
              <Sparkles size={12} />
              Intelligent Reporting System
            </span>
            <h1
              className="font-display bg-gradient-to-r from-brand via-violet-500 to-brand bg-clip-text text-6xl font-extrabold leading-[1.05] tracking-tight text-transparent lg:text-7xl"
            >
              QG-IRS
            </h1>
            <p className="mt-3 text-lg font-bold leading-snug text-ink">
              Helps you with reporting — descriptive, diagnostic, prescriptive
              &amp; forecasting — plus live dashboards and an AI chatbot.
            </p>

            <div className="mt-7 grid grid-cols-2 gap-3">
              {CAPABILITIES.map((c, i) => (
                <div
                  key={c.label}
                  className="animate-fade-in-up group flex items-start gap-3 rounded-2xl border border-line/70 bg-surface/60 p-3.5 transition-[transform,box-shadow] duration-200 hover:-translate-y-1 hover:shadow-lg"
                  style={{ animationDelay: `${i * 70}ms`, animationFillMode: 'backwards' }}
                >
                  <span
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-110"
                    style={{ backgroundColor: `${c.color}1A`, color: c.color }}
                  >
                    <c.icon size={19} />
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-bold leading-tight text-navy">{c.label}</p>
                    <p className="mt-0.5 text-xs text-muted">{c.hint}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: sign-in card — the photo shows through around it. Inputs
            (Input component) are already solidly opaque on their own, so
            the surrounding card can go frosted-glass like the copy panel
            without ever risking the form's own legibility. */}
        <div className="flex items-center justify-center px-6 py-16">
          <div className="animate-fade-in-up w-full max-w-sm">
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-4 rounded-[28px] border border-white/40 bg-surface/78 p-8 backdrop-blur-xl dark:border-white/10 dark:bg-surface/72"
              style={{ boxShadow: '0 30px 70px -20px rgba(79,70,229,0.3), 0 10px 30px -10px rgba(0,0,0,0.15)' }}
            >
              <div className="mb-1 flex flex-col gap-1">
                <h2 className="font-display text-xl font-bold text-ink">Welcome back</h2>
                <p className="text-sm text-muted">Sign in to your supply-chain workspace.</p>
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="username">Username</Label>
                <Input
                  id="username"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              {error && (
                <p className="animate-scale-in rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">{error}</p>
              )}

              <Button type="submit" disabled={submitting} className="mt-2">
                {submitting ? 'Signing in…' : 'Sign in'}
              </Button>

              <p className="flex items-center justify-center gap-1.5 text-[11px] text-muted">
                <ShieldCheck size={13} className="text-healthy" />
                Secure access · Qadri Group internal
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
