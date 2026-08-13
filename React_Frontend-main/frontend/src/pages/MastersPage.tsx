import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { SegmentedControl } from '@/components/SegmentedControl'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { ApiError } from '@/lib/api/client'
import {
  listMasters, createMaster,
  CURRENCIES, PORT_TYPES, PORT_USED_AS,
  type MasterKey, type MasterRow,
} from '@/lib/api/masters'

/**
 * Masters management — view and add the reference lists the operations screens
 * pick from (customers, suppliers, ports, clearing agents, transporters,
 * branches). One screen for all of them: a tab per master, a searchable
 * table, and an "Add new" form. Every master has the same shape of work, so
 * the columns and form fields are described once per master in MASTER_DEFS
 * and one list + one form component render them all. (Item is managed inside
 * the imports item flow and isn't duplicated here.)
 */

type FieldType = 'text' | 'select'

interface FieldDef {
  key: string
  label: string
  type?: FieldType
  required?: boolean
  options?: readonly string[]
  placeholder?: string
  /** Show this field as a column in the list table. */
  column?: boolean
}

interface MasterDef {
  key: MasterKey
  label: string
  /** Fields for both the add form and (where column=true) the table. */
  fields: FieldDef[]
}

const MASTER_DEFS: MasterDef[] = [
  {
    // Who physically moves a trucking job. The trucking wizard resolves a
    // typed transporter name to this master server-side (transporter_id),
    // the same pairing Customer uses for logistics orders.
    key: 'transporter', label: 'Transporters',
    fields: [
      { key: 'name', label: 'Name', required: true, column: true },
      { key: 'contact_name', label: 'Contact name', column: true },
      { key: 'phone', label: 'Phone', column: true },
      { key: 'ntn', label: 'NTN', column: true },
    ],
  },
  {
    // Name only — the logistics workbooks carry nothing else about a customer,
    // so address/contact fields would just be six empty columns.
    key: 'customer', label: 'Customers',
    fields: [
      { key: 'name', label: 'Name', required: true, column: true },
    ],
  },
  {
    key: 'supplier', label: 'Suppliers',
    fields: [
      { key: 'name', label: 'Name', required: true, column: true },
      { key: 'country', label: 'Country', required: true, column: true },
      { key: 'city', label: 'City', column: true },
      { key: 'contact_name', label: 'Contact name' },
      { key: 'phone', label: 'Phone' },
      { key: 'email', label: 'Email' },
      { key: 'default_currency', label: 'Default currency', type: 'select', options: CURRENCIES, column: true },
      { key: 'default_payment_terms', label: 'Default payment terms' },
    ],
  },
  {
    key: 'port', label: 'Ports',
    fields: [
      { key: 'name', label: 'Name', required: true, column: true },
      { key: 'country', label: 'Country', column: true },
      { key: 'port_type', label: 'Port type', type: 'select', options: PORT_TYPES, column: true },
      { key: 'used_as', label: 'Used as', type: 'select', options: PORT_USED_AS, column: true },
      { key: 'un_locode', label: 'UN/LOCODE', column: true },
    ],
  },
  {
    key: 'agent', label: 'Clearing Agents',
    fields: [
      { key: 'name', label: 'Name', required: true, column: true },
      { key: 'licence_no', label: 'Licence no.', column: true },
      { key: 'contact_name', label: 'Contact name', column: true },
      { key: 'phone', label: 'Phone', column: true },
    ],
  },
  {
    key: 'branch', label: 'Branches',
    fields: [
      { key: 'name', label: 'Name', required: true, column: true },
      { key: 'code', label: 'Code', column: true },
      { key: 'city', label: 'City', column: true },
      { key: 'address', label: 'Address' },
    ],
  },
  // No "Works" tab. Works and Branch are the same thing to the business (the
  // imports sheet's "Works" column is what fills a consignment's branch), so
  // the duplicate list was removed here and from the backend registry together.
]

export function MastersPage() {
  const { user } = useAuth()
  const canAdd = can(user, 'manageMastersFull') || can(user, 'manageMastersInlineCreate')
  const [activeKey, setActiveKey] = useState<MasterKey>('customer')
  const def = MASTER_DEFS.find((d) => d.key === activeKey)!

  return (
    <div className="space-y-4">
      <PageHeader title="Masters" subtitle="Reference lists used across operations" module="dataEntry" />

      <SegmentedControl
        options={MASTER_DEFS.map((d) => ({ value: d.key, label: d.label }))}
        value={activeKey}
        onChange={setActiveKey}
      />

      {/* Remount on tab change so list + form state reset cleanly. */}
      <MasterPanel key={def.key} def={def} canAdd={canAdd} />
    </div>
  )
}

function MasterPanel({ def, canAdd }: { def: MasterDef; canAdd: boolean }) {
  const [rows, setRows] = useState<MasterRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [showForm, setShowForm] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listMasters(def.key, { includeInactive })
      setRows(data)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load this list.')
    } finally {
      setLoading(false)
    }
  }, [def.key, includeInactive])

  useEffect(() => { void load() }, [load])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return rows
    return rows.filter((r) =>
      Object.values(r).some((v) => typeof v === 'string' && v.toLowerCase().includes(q)),
    )
  }, [rows, search])

  const columns = def.fields.filter((f) => f.column)

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Input
            placeholder={`Search ${def.label.toLowerCase()}…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 w-64"
          />
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <input type="checkbox" checked={includeInactive} onChange={(e) => setIncludeInactive(e.target.checked)} />
            Show inactive
          </label>
        </div>
        {canAdd && (
          <Button onClick={() => setShowForm((v) => !v)} variant={showForm ? 'outline' : 'default'}>
            {showForm ? 'Cancel' : `Add ${def.label.replace(/s$/, '')}`}
          </Button>
        )}
      </div>

      {showForm && (
        <AddMasterForm
          def={def}
          onCreated={() => { setShowForm(false); void load() }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {error && (
        <div className="rounded-lg border border-risk/40 bg-[var(--color-risk-bg)] px-3 py-2 text-sm text-risk">
          {error} <button onClick={() => void load()} className="underline">Retry</button>
        </div>
      )}

      <div className="max-h-[65vh] overflow-auto rounded-xl border border-line bg-surface [scrollbar-width:auto]">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="sticky top-0 z-10 bg-canvas-alt text-xs text-muted shadow-[0_1px_0_var(--color-line)]">
            <tr>
              {columns.map((c) => <th key={c.key} className="px-3 py-2 text-left">{c.label}</th>)}
              <th className="px-3 py-2 text-left">Used in</th>
              <th className="px-3 py-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={columns.length + 2} className="px-3 py-8 text-center text-muted">Loading…</td></tr>
            )}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={columns.length + 2} className="px-3 py-8 text-center text-muted">
                {search ? 'Nothing matches your search.' : 'No records yet.'}
              </td></tr>
            )}
            {!loading && filtered.map((r) => {
              const row = r as unknown as Record<string, unknown>
              return (
                <tr key={r.id} className={`border-t border-line ${r.is_active ? '' : 'opacity-50'}`}>
                  {columns.map((c) => (
                    <td key={c.key} className="px-3 py-2">{String(row[c.key] ?? '—') || '—'}</td>
                  ))}
                  <td className="px-3 py-2 tabular-nums text-muted">{r.used}</td>
                  <td className="px-3 py-2">
                    {!r.is_verified
                      ? <span className="rounded-full bg-[var(--color-watch-bg)] px-2 py-0.5 text-[11px] text-[var(--color-watch)]">Unverified</span>
                      : r.is_active
                        ? <span className="rounded-full bg-[var(--color-healthy-bg)] px-2 py-0.5 text-[11px] text-[var(--color-healthy)]">Active</span>
                        : <span className="rounded-full bg-canvas-alt px-2 py-0.5 text-[11px] text-muted">Inactive</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function AddMasterForm({ def, onCreated, onCancel }: {
  def: MasterDef
  onCreated: () => void
  onCancel: () => void
}) {
  const initial = useMemo(() => {
    const o: Record<string, string> = {}
    for (const f of def.fields) o[f.key] = f.type === 'select' && f.options ? f.options[0] : ''
    return o
  }, [def])

  const [values, setValues] = useState<Record<string, string>>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (key: string, v: string) => setValues((prev) => ({ ...prev, [key]: v }))

  const submit = async () => {
    // Required fields must be present.
    const missing = def.fields.filter((f) => f.required && !values[f.key]?.trim())
    if (missing.length) {
      setError(`${missing.map((f) => f.label).join(', ')} required.`)
      return
    }
    setSaving(true)
    setError(null)
    // Only send non-empty values; the backend treats absent optionals as null.
    const payload: Record<string, unknown> = {}
    for (const f of def.fields) {
      const v = values[f.key]?.trim()
      if (v) payload[f.key] = v
    }
    try {
      await createMaster(def.key, payload)
      onCreated()
    } catch (e) {
      setError(e instanceof ApiError ? (e.message || 'Could not save.') : (e instanceof Error ? e.message : 'Could not save.'))
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <h3 className="mb-3 text-sm font-semibold">Add {def.label.replace(/s$/, '')}</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {def.fields.map((f) => (
          <div key={f.key} className="flex flex-col gap-1.5">
            <Label htmlFor={`m-${f.key}`}>
              {f.label}{f.required && <span className="text-risk"> *</span>}
            </Label>
            {f.type === 'select' && f.options ? (
              <select
                id={`m-${f.key}`}
                value={values[f.key]}
                onChange={(e) => set(f.key, e.target.value)}
                className="flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
              >
                {f.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <Input
                id={`m-${f.key}`}
                value={values[f.key]}
                placeholder={f.placeholder}
                onChange={(e) => set(f.key, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>
      {error && <p className="mt-2 text-xs text-risk">{error}</p>}
      <div className="mt-4 flex gap-2">
        <Button onClick={() => void submit()} disabled={saving}>{saving ? 'Saving…' : 'Create'}</Button>
        <Button variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>
      </div>
    </div>
  )
}
