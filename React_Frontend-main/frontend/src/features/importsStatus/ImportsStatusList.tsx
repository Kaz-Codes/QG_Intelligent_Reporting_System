import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { SegmentedControl } from '@/components/SegmentedControl'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import { SortableTable, type SortableColumn } from './components/SortableTable'
import { StatusPill, Tag, PaymentDot } from './components/atoms'
import { pkr, fx, dateShort, days as daysFmt, num } from './format'
import {
  getConsignments, stageCounts, pkrValue, slippageDays, freeDaysLeft,
  branchList, statusList, supplierList, requisitionList,
  type ConsignmentRow, type ConsignmentFilters, type StageKey,
} from '@/lib/importsStatusData'

/**
 * Imports Status — list view.
 *
 * The centre of gravity of the whole feature: the screen people watch all day.
 * A pipeline strip rolls 11 statuses into 6 scannable stages (and doubles as a
 * filter); the table adds slippage, a free-days countdown and a named
 * "information pending" flag on top of the plain fields. Completed consignments
 * are hidden by default. Both exports run on the *filtered* set.
 */
export function ImportsStatusList() {
  const navigate = useNavigate()
  const { user } = useAuth()

  const [filters, setFilters] = useState<ConsignmentFilters>({})
  const [stage, setStage] = useState<StageKey>('all')
  const [includeClosed, setIncludeClosed] = useState(false)
  const [missingOnly, setMissingOnly] = useState(false)

  const rows = useMemo(
    () => getConsignments({ ...filters, stage, includeClosed, missingOnly }),
    [filters, stage, includeClosed, missingOnly],
  )
  const stages = useMemo(() => stageCounts(includeClosed), [includeClosed])

  const stageOptions = stages.map((s) => ({
    value: s.key,
    label: s.key === 'all' ? (includeClosed ? 'All' : 'All open') : s.key,
    badge: s.count,
  }))

  const columns: SortableColumn<ConsignmentRow>[] = [
    {
      key: 'systemId', label: 'ID / Reference', width: 150,
      sortValue: (r) => r.systemId,
      render: (r) => {
        const first = r.items[0]
        const ref = first?.referenceNo || (r.requisitionSummary && `${r.requisitionSummary} — no reference`)
        return (
          <div>
            <div className="font-semibold tabular-nums">{r.systemId}</div>
            <div className="text-[11px] text-muted">{ref || '—'}</div>
          </div>
        )
      },
    },
    {
      key: 'branch', label: 'Branch', width: 120,
      sortValue: (r) => r.branch,
      render: (r) => (
        <div>
          <div>{r.branch}</div>
          <div className="text-[11px] text-muted">{r.requisitionSummary}</div>
        </div>
      ),
    },
    {
      key: 'supplier', label: 'Supplier / Origin', width: 190,
      sortValue: (r) => r.supplier,
      render: (r) => (
        <div>
          <div>{r.supplier}</div>
          <div className="text-[11px] text-muted">{r.origin}</div>
        </div>
      ),
    },
    {
      key: 'items', label: 'Items', width: 170,
      render: (r) => {
        const first = r.items[0]
        const more = r.items.length - 1
        return (
          <div>
            <div>{first?.itemName}</div>
            <div className="text-[11px] text-muted tabular-nums">
              {num(first?.quantity ?? 0)} {first?.uom}
              {more > 0 && ` · +${more} more`}
            </div>
          </div>
        )
      },
    },
    {
      key: 'status', label: 'Status', width: 170,
      sortValue: (r) => statusList.indexOf(r.status),
      render: (r) => (
        <div className="space-y-1">
          <StatusPill status={r.status} />
          {r.missing.length > 0 && (
            <div>
              <Tag tone="warning" title={`Missing: ${r.missing.join(', ')}`}>
                {r.missing.length} field{r.missing.length > 1 ? 's' : ''} missing
              </Tag>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'etd', label: 'ETD', width: 90, align: 'right',
      sortValue: (r) => r.etd ?? '9999',
      render: (r) => <span className="tabular-nums">{dateShort(r.etd)}</span>,
    },
    {
      key: 'eta', label: 'ETA', width: 110, align: 'right',
      sortValue: (r) => r.eta ?? '9999',
      render: (r) => (
        <div className="tabular-nums">
          {dateShort(r.eta)}
          {r.etaHistory.length > 0 && (
            <div className="mt-0.5">
              <Tag tone="warning" title={`Revised ${r.etaHistory.length} time(s)`}>
                ETA ×{r.etaHistory.length}
              </Tag>
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'slippage', label: 'Slippage', width: 90, align: 'right',
      sortValue: (r) => slippageDays(r) ?? -1,
      render: (r) => {
        const s = slippageDays(r)
        if (s === null) return <span className="text-muted">—</span>
        return s <= 0
          ? <span className="tabular-nums text-[var(--color-success)]">on time</span>
          : <Tag tone="danger">{daysFmt(s)}</Tag>
      },
    },
    {
      key: 'value', label: 'Value', width: 110, align: 'right',
      sortValue: (r) => r.foreignValue,
      render: (r) => <span className="tabular-nums whitespace-nowrap">{fx(r.foreignValue, r.currency)}</span>,
    },
    {
      key: 'pkr', label: 'Value (PKR)', width: 130, align: 'right',
      sortValue: (r) => pkrValue(r),
      render: (r) => (
        <div className="tabular-nums">
          {pkr(pkrValue(r))}
          <div className="text-[11px] text-muted" title={`Rate booked ${dateShort(r.rateDate)}`}>
            @ {r.exchangeRate.toFixed(2)} · {dateShort(r.rateDate)}
          </div>
        </div>
      ),
    },
    {
      key: 'payment', label: 'Payment', width: 120,
      sortValue: (r) => r.paymentState,
      render: (r) => (
        <span className="whitespace-nowrap text-[13px]">
          <PaymentDot state={r.paymentState} />
          {r.paymentLabel}
        </span>
      ),
    },
    {
      key: 'clearance', label: 'Clearance', width: 120,
      render: (r) => {
        if (r.gateOut) return <span className="tabular-nums text-[13px]">Out {dateShort(r.gateOut)}</span>
        const left = freeDaysLeft(r)
        if (left === null) return <span className="text-muted">—</span>
        const tone = left <= 2 ? 'danger' : left <= 4 ? 'warning' : 'neutral'
        return <Tag tone={tone}>{left} free day{left === 1 ? '' : 's'} left</Tag>
      },
    },
    {
      key: 'actions', label: '', width: 120,
      render: (r) => (
        <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => navigate(`/imports-status/${r.systemId}`)}
            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
          >
            Open
          </button>
          {can(user, 'editAny') && (
            <button
              onClick={() => navigate(`/imports-status/${r.systemId}/edit/consignment`)}
              className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
            >
              Edit
            </button>
          )}
        </div>
      ),
    },
  ]

  /* exports run on the current filtered set — the single most-wanted behaviour */
  const exportCsv = () => {
    const cols = [
      'Consignment ID', 'Branch', 'Supplier', 'Origin', 'Requisition', 'Status',
      'ETD', 'ETA', 'ETA revisions', 'Slippage (days)', 'Currency', 'Value (foreign)',
      'Exchange rate', 'Rate date', 'Value (PKR)', 'Payment', 'Clearing agent',
      'Gate out', 'Missing fields',
    ]
    const line = (r: ConsignmentRow) => [
      r.systemId, r.branch, r.supplier, r.origin, r.requisitionSummary, r.status,
      r.etd ?? '', r.eta ?? '', r.etaHistory.length, slippageDays(r) ?? '',
      r.currency, r.foreignValue, r.exchangeRate, r.rateDate, Math.round(pkrValue(r)),
      r.paymentLabel, r.clearingAgent ?? '', r.gateOut ?? '', r.missing.join('; '),
    ].map((v) => {
      const s = String(v ?? '')
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }).join(',')

    const csv = [cols.join(','), ...rows.map(line)].join('\r\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `consignments_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Consignments" subtitle={`${rows.length} shown`} module="importsStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportCsv}>Export Excel</Button>
          <Button variant="outline" onClick={() => window.print()}>Export PDF</Button>
          {can(user, 'enter') && (
            <Button asChild>
              <Link to="/imports-status/new">New consignment</Link>
            </Button>
          )}
        </div>
      </div>

      <SegmentedControl
        options={stageOptions.map((s) => ({ value: s.value, label: `${s.label} (${s.badge})` }))}
        value={stage}
        onChange={(v) => setStage(v as StageKey)}
      />

      <FilterBar
        search={{
          value: filters.search ?? '',
          onChange: (search) => setFilters((f) => ({ ...f, search })),
          placeholder: 'ID, reference, supplier, item…',
        }}
      >
        <MultiSelectFilter label="Branch" options={branchList} value={filters.branch ?? []} onChange={(branch) => setFilters((f) => ({ ...f, branch }))} />
        <MultiSelectFilter label="Status" options={statusList} value={filters.status ?? []} onChange={(status) => setFilters((f) => ({ ...f, status }))} />
        <MultiSelectFilter label="Requisition" options={requisitionList} value={filters.requisition ?? []} onChange={(requisition) => setFilters((f) => ({ ...f, requisition }))} />
        <MultiSelectFilter label="Supplier" options={supplierList} value={filters.supplier ?? []} onChange={(supplier) => setFilters((f) => ({ ...f, supplier }))} />
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={missingOnly} onChange={(e) => setMissingOnly(e.target.checked)} />
          Missing information only
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={includeClosed} onChange={(e) => setIncludeClosed(e.target.checked)} />
          Include completed
        </label>
      </FilterBar>

      <SortableTable
        columns={columns}
        rows={rows}
        flagged={(r) => r.missing.length > 0}
        onRowClick={(r) => navigate(`/imports-status/${r.systemId}`)}
        initialSort={{ key: 'systemId', dir: 'desc' }}
        empty={
          <div>
            <div className="mb-1 font-semibold text-ink">No consignments match these filters</div>
            Clear a filter or widen the search to see results.
          </div>
        }
      />
    </div>
  )
}
