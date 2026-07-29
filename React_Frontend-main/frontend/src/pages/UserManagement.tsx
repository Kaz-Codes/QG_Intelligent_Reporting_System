import { useState } from 'react'
import { UserPlus } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { listUsers, createUser } from '@/lib/mockAuth'
import type { Role } from '@/lib/roleAccess'

const ROLES: { value: Role; label: string }[] = [
  { value: 'admin', label: 'Admin' },
  { value: 'manager', label: 'Manager' },
  { value: 'entry', label: 'Entry' },
  { value: 'viewer', label: 'Viewer' },
]

const ROLE_COLOR: Record<Role, string> = {
  admin: '#4F46E5',
  manager: '#0EA5E9',
  entry: '#10B981',
  viewer: '#64748B',
}

function RoleBadge({ role }: { role: Role }) {
  const color = ROLE_COLOR[role]
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold capitalize"
      style={{ color, backgroundColor: `${color}1A` }}
    >
      {role}
    </span>
  )
}

export function UserManagement() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState(() => listUsers())
  const [name, setName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('entry')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      createUser({ name, username, password, role })
      setUsers(listUsers())
      setName('')
      setUsername('')
      setPassword('')
      setRole('entry')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="User Management" subtitle="Create accounts and see who has access to what" module="userManagement" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <p className="mb-4 text-sm font-semibold text-ink">Accounts ({users.length})</p>
            <div className="flex flex-col">
              {users.map((u, i) => (
                <div
                  key={u.username}
                  className={`flex items-center justify-between gap-3 py-2.5 ${i !== 0 ? 'border-t border-line' : ''}`}
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-ink">
                      {u.name}
                      {u.username === me?.username && <span className="ml-1.5 text-xs text-muted">(you)</span>}
                    </p>
                    <p className="truncate text-xs text-muted">@{u.username}</p>
                  </div>
                  <RoleBadge role={u.role} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-ink">
              <UserPlus size={15} />
              Create account
            </p>
            <p className="mb-4 text-xs text-muted">Only admins can create accounts.</p>
            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-name">Name</Label>
                <Input id="new-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-username">Username</Label>
                <Input id="new-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-password">Password</Label>
                <Input id="new-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="new-role">Role</Label>
                <select
                  id="new-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as Role)}
                  className="flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>{r.label}</option>
                  ))}
                </select>
              </div>

              {error && <p className="animate-scale-in rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">{error}</p>}

              <Button type="submit" disabled={submitting} className="mt-1">
                {submitting ? 'Creating…' : 'Create account'}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
