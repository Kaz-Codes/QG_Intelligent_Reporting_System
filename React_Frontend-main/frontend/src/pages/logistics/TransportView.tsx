import { useMemo, useState, type ReactNode } from 'react'
import { Truck, PackageCheck, ArrowLeftRight, MapPin, Flag, Check, Radar, type LucideIcon } from 'lucide-react'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { DateRangeFilter } from '@/components/DateRangeFilter'
import { Disclosure } from '@/components/Disclosure'
import { KpiCard } from '@/components/KpiCard'
import { InsightsCard } from '@/components/InsightsCard'
import { ChartCard } from '@/components/ChartCard'
import { Card, CardContent } from '@/components/ui/card'
import { DataTable, type Column } from '@/components/DataTable'
import { StatusBadge } from '@/components/StatusBadge'
import { CategoryBar } from '@/components/charts/CategoryBar'
import { Donut } from '@/components/charts/Donut'
import { RankedBar } from '@/components/charts/RankedBar'
import { money, shortDate, monthInRange } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  getShifting, shiftingStatusList, shiftingMovementTypeList, shiftingPaymentStatusList,
  shiftingCustomerList, shiftingProvinceList, shiftingTransporterList, type ShiftingRow,
} from '@/lib/mockData/logistics'

const TABS = [
  { value: 'status', label: 'Status' },
  { value: 'transporter', label: 'By Transporter' },
  { value: 'province', label: 'By Province' },
] as const

const MOVEMENT_ICON: Record<string, LucideIcon> = {
  Inbound: PackageCheck,
  Outbound: Truck,
  'Inter-Branch': ArrowLeftRight,
}

const STEP_ORDER = ['Booked', 'In Progress', 'Delivered']
const STATUS_PRIORITY: Record<string, number> = { 'In Progress': 0, Booked: 1, Delivered: 2 }

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted">{label}</p>
      <div className="mt-1 text-sm font-semibold text-ink">{value}</div>
    </div>
  )
}

function RoutePoint({ icon: Icon, label, align }: { icon: LucideIcon; label: string; align: 'left' | 'right' }) {
  return (
    <div className={cn('flex flex-col items-center gap-1.5', align === 'right' && 'items-center')}>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
        <Icon size={14} />
      </span>
      <span className="max-w-[110px] truncate text-[11px] font-medium text-muted">{label}</span>
    </div>
  )
}

function RouteLine({ active }: { active: boolean }) {
  return (
    <div className="relative h-6 flex-1 self-start pt-4">
      <div className="absolute inset-x-0 top-0 h-px bg-line" />
      {active && (
        <svg className="absolute inset-x-0 top-0 h-px w-full overflow-visible text-brand" preserveAspectRatio="none">
          <line x1="0" y1="0" x2="100%" y2="0" stroke="currentColor" strokeWidth="2" strokeDasharray="6 6" className="animate-route-dash" />
        </svg>
      )}
    </div>
  )
}

function Stepper({ status }: { status: string }) {
  const idx = STEP_ORDER.indexOf(status)
  return (
    <div className="mt-6 flex items-center">
      {STEP_ORDER.map((step, i) => (
        <div key={step} className="flex flex-1 items-center last:flex-none">
          <div className="flex flex-col items-center gap-1.5">
            <span
              className={cn(
                'flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold transition-colors duration-300',
                i <= idx ? 'bg-brand text-white' : 'bg-canvas-alt text-muted',
              )}
            >
              {i < idx ? <Check size={12} /> : i + 1}
            </span>
            <span className={cn('whitespace-nowrap text-[11px] font-medium', i <= idx ? 'text-ink' : 'text-muted')}>{step}</span>
          </div>
          {i < STEP_ORDER.length - 1 && (
            <div className={cn('mx-2 h-0.5 flex-1 rounded-full transition-colors duration-300', i < idx ? 'bg-brand' : 'bg-line')} />
          )}
        </div>
      ))}
    </div>
  )
}

function MovementDetail({ row }: { row: ShiftingRow }) {
  const Icon = MOVEMENT_ICON[row.movement_type] ?? Truck
  return (
    <div key={`${row.customer}-${row.destination}-${row.execution_date.toISOString()}`} className="animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <Icon size={20} />
          </span>
          <div>
            <p className="font-display text-lg font-bold text-ink">{row.customer}</p>
            <p className="text-xs text-muted">{row.transporter} · {row.movement_type}</p>
          </div>
        </div>
        <StatusBadge label={row.status} />
      </div>

      <div className="mt-6 flex items-start gap-2">
        <RoutePoint icon={MapPin} label={row.province} align="left" />
        <RouteLine active={row.status === 'In Progress'} />
        <RoutePoint icon={Flag} label={row.destination} align="right" />
      </div>

      <Stepper status={row.status} />

      <div className="mt-6 grid grid-cols-2 gap-x-4 gap-y-5 sm:grid-cols-3">
        <Fact label="Payment Status" value={<StatusBadge label={row.payment_status} />} />
        <Fact label="Execution Date" value={shortDate(row.execution_date)} />
        <Fact label="Freight Cost" value={money(row.actual_freight_rs)} />
        <Fact label="Savings" value={row.savings_rs ? money(row.savings_rs) : '—'} />
        <Fact label="Province" value={row.province} />
        <Fact label="Movement Type" value={row.movement_type} />
      </div>
    </div>
  )
}

export function TransportView() {
  const [status, setStatus] = useState<string[]>([])
  const [movementType, setMovementType] = useState<string[]>([])
  const [paymentStatus, setPaymentStatus] = useState<string[]>([])
  const [customer, setCustomer] = useState<string[]>([])
  const [province, setProvince] = useState<string[]>([])
  const [transporter, setTransporter] = useState<string[]>([])
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<(typeof TABS)[number]['value']>('status')
  const [selectedIdx, setSelectedIdx] = useState(0)

  const filtered = useMemo(
    () => getShifting({ status, movementType, paymentStatus, customer, province, transporter }),
    [status, movementType, paymentStatus, customer, province, transporter],
  )
  const data = useMemo(
    () => filtered.filter((r) => monthInRange(r.execution_date, dateFrom, dateTo)),
    [filtered, dateFrom, dateTo],
  )
  const tableRows = useMemo(() => {
    if (!search.trim()) return data
    const needle = search.toLowerCase()
    return data.filter((r) => [r.customer, r.transporter, r.destination].some((v) => v.toLowerCase().includes(needle)))
  }, [data, search])

  const board = useMemo(
    () =>
      [...data].sort((a, b) => {
        const p = (STATUS_PRIORITY[a.status] ?? 3) - (STATUS_PRIORITY[b.status] ?? 3)
        return p !== 0 ? p : b.execution_date.getTime() - a.execution_date.getTime()
      }),
    [data],
  )
  const activeIdx = board.length > 0 ? Math.min(selectedIdx, board.length - 1) : -1
  const selected = activeIdx >= 0 ? board[activeIdx] : null

  const delivered = data.filter((r) => r.status === 'Delivered').length
  const inProgress = data.filter((r) => r.status === 'In Progress').length
  const totalFreight = data.reduce((s, r) => s + r.actual_freight_rs, 0)
  const totalSavings = data.reduce((s, r) => s + (r.savings_rs ?? 0), 0)
  const transporters = new Set(data.map((r) => r.transporter)).size

  const byStatus = [...new Set(data.map((r) => r.status))].map((s) => ({ label: s, value: data.filter((r) => r.status === s).length }))
  const byTransporter = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.transporter, (map.get(r.transporter) ?? 0) + 1)
    return [...map.entries()].map(([transporter, movements]) => ({ transporter, movements })).sort((a, b) => b.movements - a.movements).slice(0, 8)
  }, [data])
  const byProvince = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.province, (map.get(r.province) ?? 0) + 1)
    return [...map.entries()].map(([province, movements]) => ({ province, movements })).sort((a, b) => b.movements - a.movements)
  }, [data])
  const freightByTransporter = useMemo(() => {
    const map = new Map<string, number>()
    for (const r of data) map.set(r.transporter, (map.get(r.transporter) ?? 0) + r.actual_freight_rs)
    return [...map.entries()].map(([transporter, actual_freight_rs]) => ({ transporter, actual_freight_rs }))
      .sort((a, b) => b.actual_freight_rs - a.actual_freight_rs).slice(0, 8)
  }, [data])

  const columns: Column[] = [
    { key: 'customer', label: 'Customer' },
    { key: 'transporter', label: 'Transporter' },
    { key: 'province', label: 'Province' },
    { key: 'destination', label: 'Destination' },
    { key: 'actual_freight_rs', label: 'Freight', align: 'right', render: (row) => money(row.actual_freight_rs as number) },
    { key: 'status', label: 'Status', render: (row) => <StatusBadge label={row.status as string} /> },
  ]

  return (
    <div className="flex flex-col gap-6">
      <FilterBar search={{ value: search, onChange: setSearch, placeholder: 'Search by customer, transporter, or destination…' }}>
        <DateRangeFilter label="Execution Date" from={dateFrom} to={dateTo} onFromChange={setDateFrom} onToChange={setDateTo} />
        <MultiSelectFilter label="Movement Type" options={shiftingMovementTypeList} value={movementType} onChange={setMovementType} />
        <MultiSelectFilter label="Customer" options={shiftingCustomerList} value={customer} onChange={setCustomer} />
        <MultiSelectFilter label="Province" options={shiftingProvinceList} value={province} onChange={setProvince} />
        <MultiSelectFilter label="Transporter" options={shiftingTransporterList} value={transporter} onChange={setTransporter} />
        <MultiSelectFilter label="Operational Status" options={shiftingStatusList} value={status} onChange={setStatus} />
      </FilterBar>

      <Disclosure title="More filters — Payment Status">
        <div className="flex flex-wrap gap-4 pb-4">
          <div className="w-56">
            <MultiSelectFilter label="Payment Status" options={shiftingPaymentStatusList} value={paymentStatus} onChange={setPaymentStatus} />
          </div>
        </div>
      </Disclosure>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <KpiCard label="Movements Shown" value={data.length.toLocaleString()} />
        <KpiCard label="Delivered" value={`${delivered}`} direction={delivered ? 'up' : null} goodWhen="up" />
        <KpiCard label="In Progress" value={`${inProgress}`} />
        <KpiCard label="Total Freight Cost" value={money(totalFreight)} />
        <KpiCard label="Total Savings" value={totalSavings ? money(totalSavings) : '—'} />
        <KpiCard label="Transporters" value={`${transporters}`} />
      </div>

      <Card className="overflow-hidden py-0">
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr]">
          <div className="flex flex-col border-b border-line lg:border-b-0 lg:border-r">
            <div className="flex items-center justify-between border-b border-line px-4 py-3.5">
              <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                <Radar size={14} className="text-brand" />
                Fleet Board
              </span>
              <span className="text-xs text-muted">{board.length} shown</span>
            </div>
            <div className="flex max-h-[440px] flex-col gap-1.5 overflow-y-auto p-2.5">
              {board.length === 0 && (
                <p className="px-2 py-10 text-center text-sm text-muted">No movements match the current filter.</p>
              )}
              {board.map((r, i) => {
                const isSelected = i === activeIdx
                const Icon = MOVEMENT_ICON[r.movement_type] ?? Truck
                return (
                  <button
                    key={`${r.customer}-${r.destination}-${r.execution_date.toISOString()}`}
                    type="button"
                    onClick={() => setSelectedIdx(i)}
                    className={cn(
                      'flex flex-col gap-1.5 rounded-xl border p-3 text-left transition-colors duration-150',
                      isSelected
                        ? 'border-brand bg-brand-soft/70 ring-1 ring-brand/25'
                        : 'border-transparent bg-canvas-alt hover:border-line hover:bg-canvas',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface text-brand">
                          <Icon size={14} />
                        </span>
                        <span className="truncate text-sm font-semibold text-ink">{r.customer}</span>
                      </span>
                      <StatusBadge label={r.status} />
                    </div>
                    <p className="truncate pl-9 text-xs text-muted">{r.transporter} · {r.destination}</p>
                    <div className="flex items-center justify-between pl-9 text-xs">
                      <span className="text-muted">{shortDate(r.execution_date)}</span>
                      <span className="font-semibold text-ink">{money(r.actual_freight_rs)}</span>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>

          <CardContent className="p-5 lg:p-6">
            {selected ? (
              <MovementDetail row={selected} />
            ) : (
              <div className="flex h-full min-h-[280px] flex-col items-center justify-center gap-2 text-center">
                <Truck className="text-muted" size={28} />
                <p className="text-sm text-muted">No movement selected.</p>
              </div>
            )}
          </CardContent>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <InsightsCard title="Insights" tabs={TABS} active={tab} onChange={setTab} className="lg:col-span-2">
          {data.length === 0 && <p className="py-12 text-center text-sm text-muted">No movements match the current filter.</p>}
          {data.length > 0 && tab === 'status' && <Donut labels={byStatus.map((s) => s.label)} values={byStatus.map((s) => s.value)} height={300} />}
          {data.length > 0 && tab === 'transporter' && <RankedBar data={byTransporter} category="transporter" value="movements" height={300} />}
          {data.length > 0 && tab === 'province' && <CategoryBar data={byProvince} category="province" value="movements" height={300} />}
        </InsightsCard>
        <ChartCard title="Freight Cost by Transporter">
          {freightByTransporter.length > 0
            ? <RankedBar data={freightByTransporter} category="transporter" value="actual_freight_rs" height={300} />
            : <p className="py-12 text-center text-sm text-muted">No transporter data in the current view.</p>}
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
