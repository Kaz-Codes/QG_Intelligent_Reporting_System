import { useEffect, useState, useCallback } from 'react'
import { UserPlus, Pencil, X, Search, ShieldCheck, RefreshCw } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { logActivity, getActivityLog } from '@/lib/activityLog'
import { PERMISSION_GROUPS, permissionLabel, type Permission } from '@/lib/roleAccess'
import {
  listUsers, createUser, updateUser, setUserActive,
  credentialError, MIN_CREDENTIAL_LENGTH, type UserAccount,
} from '@/lib/api/users'

/** The grouped permission checklist, shared by the create form and the
 * per-account edit panel. Disabled (and dimmed) once "Make Admin" is
 * checked — an admin already passes every check, so the checklist stops
 * meaning anything until admin is unchecked again (the backend clears it too). */
function PermissionChecklist({
  value, onChange, disabled, idPrefix,
}: { value: Permission[]; onChange: (v: Permission[]) => void; disabled: boolean; idPrefix: string }) {
  function toggle(p: Permission) {
    onChange(value.includes(p) ? value.filter((v) => v !== p) : [...value, p])
  }
  function toggleGroup(perms: Permission[], all: boolean) {
    onChange(all ? value.filter((v) => !perms.includes(v)) : [...new Set([...value, ...perms])])
  }
  return (
    <div className={`flex flex-col gap-3 ${disabled ? 'opacity-50' : ''}`}>
      {PERMISSION_GROUPS.map((g) => {
        const perms = g.permissions.map((p) => p.value)
        const allOn = perms.every((p) => value.includes(p))
        return (
          <div key={g.group}>
            <div className="mb-1 flex items-center justify-between">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted">{g.group}</p>
              <button
                type="button"
                disabled={disabled}
                onClick={() => toggleGroup(perms, allOn)}
                className="text-[11px] text-brand hover:underline disabled:opacity-50"
              >
                {allOn ? 'Clear' : 'All'}
              </button>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1.5">
              {g.permissions.map((p) => (
                <label
                  key={p.value}
                  htmlFor={`${idPrefix}-${p.value}`}
                  className="flex items-center gap-1.5 text-sm text-ink"
                >
                  <input
                    id={`${idPrefix}-${p.value}`}
                    type="checkbox"
                    checked={value.includes(p.value)}
                    onChange={() => toggle(p.value)}
                    disabled={disabled}
                    className="accent-brand"
                  />
                  {p.label}
                </label>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AccessSummary({ isAdmin, permissions }: { isAdmin: boolean; permissions: Permission[] }) {
  if (isAdmin) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-2.5 py-1 text-xs font-semibold text-brand">
        <ShieldCheck size={12} />
        Admin
      </span>
    )
  }
  if (permissions.length === 0) {
    return <span className="text-xs text-muted">No access</span>
  }
  // The full list can be 20+ names, so show a few and count the rest.
  const shown = permissions.slice(0, 3)
  return (
    <div className="flex flex-wrap justify-end gap-1">
      {shown.map((p) => (
        <span key={p} className="rounded-full bg-canvas-alt px-2 py-0.5 text-[11px] font-medium text-muted">
          {permissionLabel(p)}
        </span>
      ))}
      {permissions.length > shown.length && (
        <span className="rounded-full bg-canvas-alt px-2 py-0.5 text-[11px] font-medium text-muted">
          +{permissions.length - shown.length} more
        </span>
      )}
    </div>
  )
}

export function UserManagement() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<UserAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [log, setLog] = useState(() => getActivityLog())
  const [logSearch, setLogSearch] = useState('')

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(false)
  const [permissions, setPermissions] = useState<Permission[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const [editingId, setEditingId] = useState<number | null>(null)
  const [editUsername, setEditUsername] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editIsAdmin, setEditIsAdmin] = useState(false)
  const [editPermissions, setEditPermissions] = useState<Permission[]>([])
  const [editError, setEditError] = useState<string | null>(null)
  const [savingEdit, setSavingEdit] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      setUsers(await listUsers())
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Could not load accounts')
    } finally {
      setLoading(false)
      setLog(getActivityLog())
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    const invalid = credentialError(username, password)
    if (invalid) { setError(invalid); return }

    setSubmitting(true)
    try {
      await createUser({ username, password, isAdmin, permissions })
      logActivity(
        me?.username ?? 'unknown',
        `Created account @${username} — ${isAdmin ? 'Admin' : permissions.length ? `${permissions.length} permission(s)` : 'no permissions'}`,
      )
      setUsername('')
      setPassword('')
      setIsAdmin(false)
      setPermissions([])
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the account')
    } finally {
      setSubmitting(false)
    }
  }

  function startEdit(u: UserAccount) {
    setEditingId(u.id)
    setEditUsername(u.username)
    setEditPassword(u.password)
    setEditIsAdmin(u.isAdmin)
    setEditPermissions(u.permissions)
    setEditError(null)
  }

  async function saveEdit(u: UserAccount) {
    setEditError(null)

    const invalid = credentialError(editUsername, editPassword)
    if (invalid) { setEditError(invalid); return }

    setSavingEdit(true)
    try {
      // PUT /users/{id} replaces the whole account, so username/password go
      // back too (pre-filled from the row we're editing).
      await updateUser(u.id, {
        username: editUsername,
        password: editPassword,
        isAdmin: editIsAdmin,
        permissions: editPermissions,
        isActive: u.isActive,
      })
      logActivity(
        me?.username ?? 'unknown',
        `Updated access for @${editUsername} — ${editIsAdmin ? 'Admin' : editPermissions.length ? `${editPermissions.length} permission(s)` : 'no permissions'}`,
      )
      setEditingId(null)
      await refresh()
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Could not update this account')
    } finally {
      setSavingEdit(false)
    }
  }

  async function toggleActive(u: UserAccount) {
    try {
      await setUserActive(u.id, !u.isActive)
      logActivity(me?.username ?? 'unknown', `${u.isActive ? 'Deactivated' : 'Activated'} account @${u.username}`)
      await refresh()
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Could not change the account status')
    }
  }

  const filteredLog = logSearch.trim()
    ? log.filter((l) => `${l.actor} ${l.message}`.toLowerCase().includes(logSearch.trim().toLowerCase()))
    : log

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="User Management" subtitle="Create accounts and control who has access to what" module="userManagement" />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardContent className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <p className="text-sm font-semibold text-ink">
                Accounts {loading ? '' : `(${users.length})`}
              </p>
              <button
                type="button"
                onClick={() => void refresh()}
                title="Reload"
                className="rounded-lg p-1.5 text-muted hover:bg-canvas-alt hover:text-ink"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              </button>
            </div>

            {loadError && (
              <p className="mb-3 rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">{loadError}</p>
            )}
            {loading && <p className="py-6 text-center text-sm text-muted">Loading accounts…</p>}
            {!loading && !loadError && users.length === 0 && (
              <p className="py-6 text-center text-sm text-muted">No accounts yet.</p>
            )}

            <div className="flex flex-col">
              {users.map((u, i) => (
                <div key={u.id} className={`py-2.5 ${i !== 0 ? 'border-t border-line' : ''}`}>
                  {editingId === u.id ? (
                    <div className="flex flex-col gap-3 rounded-lg bg-canvas-alt p-3">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-medium text-ink">Editing @{u.username}</p>
                        <button type="button" onClick={() => setEditingId(null)} className="text-muted hover:text-ink">
                          <X size={16} />
                        </button>
                      </div>

                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`edit-username-${u.id}`}>Username</Label>
                          <Input id={`edit-username-${u.id}`} value={editUsername} onChange={(e) => setEditUsername(e.target.value)} />
                        </div>
                        <div className="flex flex-col gap-1.5">
                          <Label htmlFor={`edit-password-${u.id}`}>Password</Label>
                          <Input id={`edit-password-${u.id}`} value={editPassword} onChange={(e) => setEditPassword(e.target.value)} />
                        </div>
                      </div>

                      <label className="flex items-center gap-2 text-sm font-medium text-ink">
                        <input
                          type="checkbox"
                          checked={editIsAdmin}
                          onChange={(e) => setEditIsAdmin(e.target.checked)}
                          className="accent-brand"
                        />
                        Make Admin
                      </label>
                      <PermissionChecklist
                        idPrefix={`edit-${u.id}`}
                        value={editPermissions}
                        onChange={setEditPermissions}
                        disabled={editIsAdmin}
                      />
                      {editError && <p className="rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">{editError}</p>}
                      <Button type="button" onClick={() => void saveEdit(u)} disabled={savingEdit} className="w-fit">
                        {savingEdit ? 'Saving…' : 'Save'}
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink">
                          @{u.username}
                          {u.username === me?.username && <span className="ml-1.5 text-xs text-muted">(you)</span>}
                          {!u.isActive && (
                            <span className="ml-1.5 rounded-full bg-risk-bg px-1.5 py-0.5 text-[10.5px] font-medium text-risk">
                              Inactive
                            </span>
                          )}
                        </p>
                      </div>
                      <div className="flex items-center gap-3">
                        <AccessSummary isAdmin={u.isAdmin} permissions={u.permissions} />
                        <button
                          type="button"
                          onClick={() => void toggleActive(u)}
                          disabled={u.username === me?.username}
                          title={u.username === me?.username ? "You can't deactivate your own account" : u.isActive ? 'Deactivate' : 'Activate'}
                          className="shrink-0 rounded-lg border border-line px-2 py-1 text-[11px] text-muted hover:text-ink disabled:opacity-40"
                        >
                          {u.isActive ? 'Deactivate' : 'Activate'}
                        </button>
                        <button
                          type="button"
                          onClick={() => startEdit(u)}
                          title="Edit access"
                          className="shrink-0 rounded-lg p-1.5 text-muted hover:bg-canvas-alt hover:text-ink"
                        >
                          <Pencil size={14} />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardContent className="p-5">
              <p className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-ink">
                <UserPlus size={15} />
                Create account
              </p>
              <p className="mb-4 text-xs text-muted">
                Only admins can create accounts. Username and password must be at least {MIN_CREDENTIAL_LENGTH} characters.
              </p>
              <form onSubmit={handleCreate} className="flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-username">Username</Label>
                  <Input id="new-username" value={username} onChange={(e) => setUsername(e.target.value)} required />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="new-password">Password</Label>
                  <Input id="new-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </div>

                <label className="flex items-center gap-2 text-sm font-medium text-ink">
                  <input type="checkbox" checked={isAdmin} onChange={(e) => setIsAdmin(e.target.checked)} className="accent-brand" />
                  Make Admin
                </label>

                <div className="flex flex-col gap-1.5">
                  <Label>Permissions</Label>
                  <PermissionChecklist idPrefix="new" value={permissions} onChange={setPermissions} disabled={isAdmin} />
                </div>

                {error && <p className="animate-scale-in rounded-lg bg-risk-bg px-3 py-2 text-sm text-risk">{error}</p>}

                <Button type="submit" disabled={submitting} className="mt-1">
                  {submitting ? 'Creating…' : 'Create account'}
                </Button>
              </form>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5">
              <p className="mb-3 text-sm font-semibold text-ink">Activity Log</p>
              <div className="relative mb-3">
                <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
                <Input
                  value={logSearch}
                  onChange={(e) => setLogSearch(e.target.value)}
                  placeholder="Search by user or action…"
                  className="pl-8"
                />
              </div>
              <div className="flex max-h-80 flex-col gap-2.5 overflow-y-auto">
                {filteredLog.length === 0 && <p className="py-6 text-center text-sm text-muted">No activity yet.</p>}
                {filteredLog.map((entry) => (
                  <div key={entry.id} className="border-t border-line pt-2.5 first:border-t-0 first:pt-0">
                    <p className="text-xs text-ink">
                      <span className="font-semibold">@{entry.actor}</span> {entry.message}
                    </p>
                    <p className="text-[11px] text-muted">{new Date(entry.timestamp).toLocaleString()}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
