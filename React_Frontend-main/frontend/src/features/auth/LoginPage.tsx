import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { ShieldCheck, Sparkles, Sun, Moon } from 'lucide-react'
import { useAuth } from './AuthContext'
import { useTheme } from '@/theme/ThemeContext'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ThemedBackground } from '@/components/ThemedBackground'
import logo from '@/assets/qadri_logo_transparent.png'

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const { dark, toggle } = useTheme()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (!loading && user) {
    const redirectTo = (location.state as { from?: string } | null)?.from ?? '/dashboard'
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
    <div className="flex min-h-screen flex-col bg-surface">
      {/* Top bar */}
      <div className="flex h-16 shrink-0 items-center justify-between border-b border-line px-6">
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

      <div className="grid flex-1 grid-cols-1 md:grid-cols-2">
        {/* Left: copy panel */}
        <div className="relative flex items-center overflow-hidden bg-canvas-alt px-8 py-16 md:px-14 lg:px-20">
          <div className="bg-grid-texture absolute inset-0" />
          <ThemedBackground module="login" variant="split" />

          <div className="animate-fade-in-up relative z-10 max-w-lg">
            <span className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-brand/25 bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">
              <Sparkles size={12} />
              Intelligent Reporting System
            </span>
            <h1 className="font-display text-4xl font-extrabold leading-[1.1] tracking-tight text-navy lg:text-5xl">
              Supply-chain reporting,<br />built for everyone who touches it.
            </h1>
            <p className="mt-5 max-w-md text-base leading-relaxed text-muted">
              Dashboards, custom reports and a natural-language assistant over
              Qadri Group's purchases, inventory, imports and logistics data —
              one workspace, every role.
            </p>
          </div>
        </div>

        {/* Right: sign-in card */}
        <div className="flex items-center justify-center bg-surface px-6 py-16">
          <div className="animate-fade-in-up w-full max-w-sm">
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-4 rounded-2xl border border-line bg-surface p-8 shadow-xl"
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
