import { useMemo, useState } from 'react'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { DataTable, type Column } from '@/components/DataTable'
import { StatusBadge } from '@/components/StatusBadge'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { monthInRange } from '@/lib/format'
import { getDocumentation, getDocumentTypes, documentationStatusList } from '@/lib/mockData/logistics'

const TABS = [
  { value: 'status', label: 'Status' },
  { value: 'lowest', label: 'Lowest Completion %' },
  { value: 'category', label: 'By Category' },
] as const

export function DocumentationView() {
  const [status, setStatus] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')

  const filtered = useMemo(() => getDocumentation({ status }), [status])
  const data = useMemo(
    () => filtered.filter((r) => monthInRange(r.submitted_date, dateFrom, dateTo)),
    [filtered, dateFrom, dateTo],
  )
  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) => [r.exp_no, r.batch_no].some((v) => v.toLowerCase().includes(needle)))
  }, [data, search])
  const docTypes = useMemo(() => getDocumentTypes(), [])

  const complete = data.filter((r) => r.status === 'Complete').length
  const incomplete = data.filter((r) => r.status === 'Incomplete').length
  const avgCompletion = data.length ? data.reduce((s, r) => s + r.completion_pct, 0) / data.length : null
  const avgCustoms = data.length ? data.reduce((s, r) => s + r.customs_completion_pct, 0) / data.length : null
  const pendingDocs = data.reduce((s, r) => s + r.pending_documents, 0)

  const byStatus = [...new Set(data.map((r) => r.status))].map((s) => ({ label: s, value: data.filter((r) => r.status === s).length }))
  const lowest = [...data].sort((a, b) => a.completion_pct - b.completion_pct).slice(0, 8)
    .map((r) => ({ exp_no: r.exp_no, completion_pct: r.completion_pct }))
  const byCategory = data.length
    ? [
        { category: 'Customs', avg_pct: Math.round(data.reduce((s, r) => s + r.customs_completion_pct, 0) / data.length) },
        { category: 'Customer', avg_pct: Math.round(data.reduce((s, r) => s + r.customer_completion_pct, 0) / data.length) },
        { category: 'Bank', avg_pct: Math.round(data.reduce((s, r) => s + r.bank_completion_pct, 0) / data.length) },
      ]
    : []

  const byDocType = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of docTypes) map.set(r.document_type, (map.get(r.document_type) ?? 0) + r.n)
    return [...map.entries()].map(([document_type, n]) => ({ document_type, n })).sort((a, b) => b.n - a.n).slice(0, 10)
  }, [docTypes])
  const byDocStatus = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of docTypes) map.set(r.status, (map.get(r.status) ?? 0) + r.n)
    return [...map.entries()].map(([status_, n]) => ({ status: status_, n })).sort((a, b) => b.n - a.n)
  }, [docTypes])

  const columns: Column[] = [
    { key: 'exp_no', label: 'Export No' },
    { key: 'batch_no', label: 'Batch No' },
    { key: 'completion_pct', label: 'Completion %', align: 'right' },
    { key: 'pending_documents', label: 'Pending Docs', align: 'right' },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge label={row.status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by export no or batch no…' }}>
        <DateRangeFilter label="Submitted Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Status" options={documentationStatusList} value={status} onChange={setStatus} />
      </FilterBar>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Exports Tracked" value={data.length.toLocaleString()} />
        <KpiCard label="Complete" value={`${complete}`} direction={complete ? 'up' : null} goodWhen="up" />
        <KpiCard label="Incomplete" value={`${incomplete}`} direction={incomplete ? 'up' : null} goodWhen="down" />
        <KpiCard label="Avg Completion" value={avgCompletion != null ? `${avgCompletion.toFixed(0)}%` : '—'} />
        <KpiCard label="Avg Customs Completion" value={avgCustoms != null ? `${avgCustoms.toFixed(0)}%` : '—'} />
        <KpiCard label="Pending Documents" value={pendingDocs.toLocaleString()} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={TABS} active={tab} onChange={setTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No exports match the current filter.</p>}
          {data.length > 0 && tab === 'status' && <Donut labels={byStatus.map((s) => s.label)} values={byStatus.map((s) => s.value)} height={300} />}
          {data.length > 0 && tab === 'lowest' && <RankedBar data={lowest} category="exp_no" value="completion_pct" height={300} invertColor />}
          {data.length > 0 && tab === 'category' && <CategoryBar data={byCategory} category="category" value="avg_pct" height={300} />}
        </InsightsCard>
        <ChartCard title="Completion Snapshot">
          {byCategory.length > 0
            ? <RankedBar data={byCategory} category="category" value="avg_pct" height={300} />
            : <p className="py-12 text-center text-sm text-muted">No category completion data in the current view.</p>}
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Document Types (all exports)">
          <p className="-mt-2 mb-3 text-xs text-muted">Not scoped to the status filter above — tracked per export, covers every export.</p>
          <RankedBar data={byDocType} category="document_type" value="n" height={260} />
        </ChartCard>
        <ChartCard title="Document Status (all exports)">
          <p className="-mt-2 mb-3 text-xs text-muted">Not scoped to the status filter above — tracked per export, covers every export.</p>
          <Donut labels={byDocStatus.map((s) => s.status)} values={byDocStatus.map((s) => s.n)} height={260} />
        </ChartCard>
      </div>

      <Disclosure title="View data">
        <div className="pb-4">
          <DataTable columns={columns} rows={tableRows as unknown as Record<string, unknown>[]} statusColumn="status" height={420} />
        </div>
      </Disclosure>
    </div>
  )
}
