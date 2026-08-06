import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SegmentedControl } from '@/components/SegmentedControl'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  getServiceJobs, createReworkJob, reworkStatusList,
  customerList, type ServiceJobType,
} from '@/lib/logisticsStatusData'

/**
 * Service Jobs tab — the shipping/clearing work Logistics does that isn't one
 * of its own export/local orders. Two job types side by side:
 *
 *   - Import FOB      : handed over from Imports (item details entered there
 *                       first). Read-only here; opens the source consignment.
 *   - Customer Rework : a customer sends old rolls / used goods for rework.
 *                       Imports isn't involved, so Logistics enters everything
 *                       via the lightweight form below — no full 5-step wizard.
 *
 * A type filter switches between All / Import FOB / Customer Rework.
 */
type TypeFilter = 'all' | ServiceJobType

const TYPE_OPTIONS = [
  { value: 'all' as const, label: 'All' },
  { value: 'import-fob' as const, label: 'Import FOB' },
  { value: 'customer-rework' as const, label: 'Customer Rework' },
]

export function ServiceJobsTab() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const canEnter = can(user, 'enter')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [showForm, setShowForm] = useState(false)
  // Bump to re-read the store after a create.
  const [version, setVersion] = useState(0)

  const jobs = useMemo(
    () => getServiceJobs(typeFilter === 'all' ? undefined : typeFilter),
    [typeFilter, version],
  )

  const fobCount = useMemo(() => getServiceJobs('import-fob').length, [version])
  const reworkCount = useMemo(() => getServiceJobs('customer-rework').length, [version])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <SegmentedControl options={TYPE_OPTIONS} value={typeFilter} onChange={setTypeFilter} />
          <span className="text-xs text-muted">
            {fobCount} import FOB · {reworkCount} customer rework
          </span>
        </div>
        {canEnter && (
          <Button onClick={() => setShowForm((v) => !v)} variant={showForm ? 'outline' : 'default'}>
            {showForm ? 'Cancel' : 'New Rework Job'}
          </Button>
        )}
      </div>

      {showForm && (
        <ReworkForm
          onCreated={() => { setShowForm(false); setVersion((v) => v + 1); setTypeFilter('customer-rework') }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <div className="overflow-x-auto rounded-xl border border-line bg-surface [scrollbar-width:auto]">
        <table className="w-full min-w-[900px] text-sm">
          <thead className="bg-canvas-alt text-xs text-muted">
            <tr>
              <th className="px-3 py-2 text-left">Job ID</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-left">Customer</th>
              <th className="px-3 py-2 text-left">Item details</th>
              <th className="px-3 py-2 text-left">Origin</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Clearing agent</th>
              <th className="px-3 py-2 text-left"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-muted">
                  No service jobs of this type yet.
                </td>
              </tr>
            )}
            {jobs.map((j) => (
              <tr key={j.systemId} className="border-t border-line hover:bg-canvas-alt">
                <td className="px-3 py-2 font-semibold tabular-nums">{j.systemId}</td>
                <td className="px-3 py-2">
                  <TypeTag type={j.jobType} />
                </td>
                <td className="px-3 py-2">{j.customerName}</td>
                <td className="px-3 py-2">{j.itemDetails}{j.quantity ? <span className="text-muted"> · {j.quantity} units</span> : null}</td>
                <td className="px-3 py-2 text-muted">{j.origin}</td>
                <td className="px-3 py-2"><StatusBadge label={j.status} /></td>
                <td className="px-3 py-2 text-[13px]">
                  {j.jobType === 'import-fob' && !j.clearingAgent
                    ? <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">Needs agent</span>
                    : (j.clearingAgent ?? '—')}
                </td>
                <td className="px-3 py-2">
                  {j.jobType === 'import-fob' ? (
                    <button
                      onClick={() => j.sourceRef && navigate(`/imports-status/${j.sourceRef}`)}
                      className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                    >
                      Open in Imports
                    </button>
                  ) : (
                    <span className="text-[11px] text-muted">Logistics-owned</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TypeTag({ type }: { type: ServiceJobType }) {
  const isFob = type === 'import-fob'
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[11px]"
      style={isFob
        ? { backgroundColor: 'var(--color-watch-bg)', color: 'var(--color-watch)' }
        : { backgroundColor: 'var(--color-info-bg)', color: 'var(--color-info)' }}
    >
      {isFob ? 'Import FOB' : 'Customer Rework'}
    </span>
  )
}

/**
 * Lightweight single-form entry for a customer-rework job. Logistics enters
 * every field itself (unlike FOB, where Imports pre-fills the item details).
 * Deliberately not the full 5-step order wizard — these are simpler service
 * jobs, so a single panel is the right weight.
 */
function ReworkForm({ onCreated, onCancel }: { onCreated: () => void; onCancel: () => void }) {
  const [customerName, setCustomerName] = useState('')
  const [itemDetails, setItemDetails] = useState('')
  const [quantity, setQuantity] = useState('')
  const [origin, setOrigin] = useState('')
  const [status, setStatus] = useState<string>(reworkStatusList[0])
  const [receivedDate, setReceivedDate] = useState('')
  const [targetDate, setTargetDate] = useState('')
  const [remarks, setRemarks] = useState('')
  const [error, setError] = useState('')

  const submit = () => {
    if (!customerName.trim() || !itemDetails.trim()) {
      setError('Customer name and item details are required.')
      return
    }
    createReworkJob({
      customerName: customerName.trim(),
      itemDetails: itemDetails.trim(),
      quantity: quantity === '' ? undefined : Number(quantity),
      origin: origin.trim(),
      status,
      receivedDate: receivedDate || undefined,
      targetDate: targetDate || undefined,
      remarks: remarks.trim() || undefined,
    })
    onCreated()
  }

  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold">New Customer Rework Job</h3>
        <span className="text-xs text-muted">Logistics enters all details — customer-owned goods sent in for rework</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rw-customer">Customer name</Label>
          <Input id="rw-customer" list="rw-customers" value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
          <datalist id="rw-customers">{customerList.map((c) => <option key={c} value={c} />)}</datalist>
        </div>
        <div className="flex flex-col gap-1.5 lg:col-span-2">
          <Label htmlFor="rw-item">Item details</Label>
          <Input id="rw-item" placeholder="e.g. Old kraft paper rolls — re-slitting" value={itemDetails} onChange={(e) => setItemDetails(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rw-qty">Quantity</Label>
          <Input id="rw-qty" type="number" min="0" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rw-origin">Origin</Label>
          <Input id="rw-origin" placeholder="e.g. Lahore" value={origin} onChange={(e) => setOrigin(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rw-status">Status</Label>
          <select
            id="rw-status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="flex h-10 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/50"
          >
            {reworkStatusList.map((sName) => <option key={sName} value={sName}>{sName}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rw-received">Received date</Label>
          <Input id="rw-received" type="date" value={receivedDate} onChange={(e) => setReceivedDate(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="rw-target">Target date</Label>
          <Input id="rw-target" type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5 lg:col-span-3">
          <Label htmlFor="rw-remarks">Remarks</Label>
          <Input id="rw-remarks" value={remarks} onChange={(e) => setRemarks(e.target.value)} />
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-risk">{error}</p>}
      <div className="mt-4 flex gap-2">
        <Button onClick={submit}>Create Job</Button>
        <Button variant="outline" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  )
}
