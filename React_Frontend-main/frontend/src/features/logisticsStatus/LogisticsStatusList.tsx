import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Truck } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { MultiSelectFilter } from '@/components/MultiSelectFilter'
import { StatusBadge } from '@/components/StatusBadge'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  totalNetWeight, totalPackageGrossWeight, orderTypeLabel, jobNumbers, batchDisplayLabel,
  arrivalDelayDays, latestPlannedRfd, latestActualRfd,
} from '@/features/logisticsStatus/schema'
import { exportListExcel, exportListPdf, type ListColumn } from '@/lib/listExport'
import { usePagination, Pagination, useSort, SortHeader } from '@/components/Pagination'
import { SegmentedControl } from '@/components/SegmentedControl'
import { ServiceJobsTab } from './ServiceJobsTab'
import {
  getLogisticsOrders,
  customerList, orderTypeList, statusList,
  type LogisticsOrder, type LogisticsFilters,
} from '@/lib/logisticsStatusData'
import { getTruckingReadthrough } from '@/lib/truckingStatusData'

const num = (v: number) => v.toLocaleString('en-US')

/**
 * Consistent delay pill used across the status modules: red when late, green
 * when on time / early, muted dash when there's no data. `settled` means the
 * real arrival date is in — an unsettled positive delay is an in-flight
 * estimate ("slipping"), which reads differently from a locked-in late.
 */
function DelayCell({ days, settled }: { days: number | null; settled: boolean }) {
  if (days === null) return <span className="text-muted" title="No planned arrival date yet">—</span>
  if (days <= 0) {
    return <span className="tabular-nums text-[var(--color-healthy)]">{days === 0 ? 'on time' : `${-days}d early`}</span>
  }
  return (
    <span
      className="inline-block rounded border border-[var(--color-risk)] bg-[var(--color-risk-bg)] px-1.5 py-0.5 text-[11px] tabular-nums text-[var(--color-risk)]"
      title={settled ? 'Arrived later than planned' : 'Past planned arrival, still in transit'}
    >
      {days}d {settled ? 'late' : 'slipping'}
    </span>
  )
}

function TruckingHandoffBadge({ order }: { order: LogisticsOrder }) {
  if (!order.sentToTrucking) {
    return <span className="text-xs text-muted">Not sent</span>
  }
  const readthrough = getTruckingReadthrough(order.systemId)
  if (!readthrough || !readthrough.taken) {
    return (
      <span className="rounded border border-[var(--color-watch)]/30 bg-[var(--color-watch-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-watch)]">
        Awaiting pickup
      </span>
    )
  }
  return (
    <span className="rounded border border-[var(--color-healthy)]/30 bg-[var(--color-healthy-bg)] px-1.5 py-0.5 text-[11px] text-[var(--color-healthy)]" title={readthrough.trackingRollupLabel}>
      {readthrough.trackingRollupLabel}
    </span>
  )
}

/**
 * Logistics Status — list view.
 *
 * Columns per the confirmed spec: MO # (the system id itself — see
 * generateLogisticsSystemId in lib/logisticsStatusData.ts — with the batch
 * label alongside for Batch 2+), merged department+order-type label, Job #s,
 * Customer, Batch # (with an MO-group accent when siblings are visible),
 * Items, Packages, Net/Gross Weight, Works (first package's packing works),
 * Incoterm — plus Status and actions, which every other list in this app
 * keeps.
 *
 * An Orders / Service Jobs tab switch sits above the table — Service Jobs
 * (ServiceJobsTab) holds the read-only Import FOB feed alongside owned
 * Customer Rework jobs, replacing the old inline FOB table here.
 */
export function LogisticsStatusList() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [filters, setFilters] = useState<LogisticsFilters>({})
  const [tab, setTab] = useState<'orders' | 'services'>('orders')

  const rowsRaw = useMemo(() => getLogisticsOrders(filters), [filters])
  const { sorted: rows, sort, toggle } = useSort(rowsRaw, {
    systemId: (o) => o.systemId,
    orderType: (o) => orderTypeLabel(o.department, o.orderType),
    customer: (o) => o.customerName,
    batch: (o) => o.batchNo,
    packages: (o) => o.packages.length,
    net: (o) => totalNetWeight(o.items),
    gross: (o) => totalPackageGrossWeight(o.packages),
    incoterm: (o) => o.incoterm ?? '',
    status: (o) => o.status,
    delay: (o) => arrivalDelayDays(o) ?? -99999,
    actualRfd: (o) => latestActualRfd(o.items) ?? '',
  })
  const { page, pageCount, pageRows, setPage, total, pageSize } = usePagination(rows, 10)
  const canEdit = can(user, 'editAny')

  // MO-group sizes across the currently-visible rows — drives the "shares an
  // MO with other batches" accent on the Batch # column.
  const moCounts = useMemo(() => {
    const m = new Map<string, number>()
    rows.forEach((o) => { if (o.moNo) m.set(o.moNo, (m.get(o.moNo) ?? 0) + 1) })
    return m
  }, [rows])

  const exportColumns: ListColumn<LogisticsOrder>[] = [
    { header: 'System ID', value: (o) => o.systemId },
    { header: 'MO No.', value: (o) => o.moNo ?? '' },
    { header: 'Batch', value: (o) => batchDisplayLabel(o.batchNo, o.batchLabel) },
    { header: 'Department', value: (o) => o.department },
    { header: 'Order Type', value: (o) => orderTypeLabel(o.department, o.orderType) },
    { header: 'Job No(s).', value: (o) => jobNumbers(o.items).join('; ') },
    { header: 'Customer', value: (o) => o.customerName },
    { header: 'Items', value: (o) => o.items.map((it) => `${it.itemDetail} ×${it.quantity ?? 0}`).join('; ') },
    { header: 'Net Weight', value: (o) => totalNetWeight(o.items) },
    { header: 'Gross Weight', value: (o) => totalPackageGrossWeight(o.packages) },
    { header: 'Packages', value: (o) => o.packages.length },
    { header: 'Works', value: (o) => o.packages.find((p) => p.packingWorks)?.packingWorks ?? '' },
    { header: 'Incoterm', value: (o) => o.incoterm ?? '' },
    { header: 'Origin', value: (o) => (o.orderType === 'Export' ? o.originCountry ?? '' : `${o.originCity}, ${o.originProvince}`) },
    { header: 'Status', value: (o) => o.status },
    { header: 'Arrival delay (days)', value: (o) => arrivalDelayDays(o) ?? '' },
    { header: 'Planned RFD', value: (o) => latestPlannedRfd(o.items) ?? '' },
    { header: 'Actual RFD', value: (o) => latestActualRfd(o.items) ?? '' },
    { header: 'Gate Out Date', value: (o) => o.gateOutDate ?? '' },
    { header: 'Sent to Trucking', value: (o) => (o.sentToTrucking ? 'Yes' : 'No') },
  ]
  const stamp = () => new Date().toISOString().slice(0, 10)
  const doExcel = () => exportListExcel(rows, exportColumns, `logistics_orders_${stamp()}.xlsx`, 'Logistics')
  const doPdf = () => exportListPdf(rows, exportColumns, `logistics_orders_${stamp()}.pdf`, 'Logistics Status')

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Logistics Status" subtitle={`${rows.length} shown`} module="logisticsStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={doExcel}>Export Excel</Button>
          <Button variant="outline" onClick={doPdf}>Export PDF</Button>
          {can(user, 'enter') && (
            <Button asChild>
              <Link to="/logistics-status/new">New Logistics Order</Link>
            </Button>
          )}
        </div>
      </div>

      <SegmentedControl
        options={[{ value: 'orders' as const, label: 'Orders' }, { value: 'services' as const, label: 'Service Jobs' }]}
        value={tab}
        onChange={setTab}
      />

      {tab === 'services' ? (
        <ServiceJobsTab />
      ) : (
      <>
      <FilterBar
        search={{
          value: filters.search ?? '',
          onChange: (search) => setFilters((f) => ({ ...f, search })),
          placeholder: 'ID, MO no., customer, item, job no…',
        }}
      >
        <MultiSelectFilter label="Order type" options={orderTypeList} value={filters.orderType ?? []} onChange={(orderType) => setFilters((f) => ({ ...f, orderType: orderType as typeof f.orderType }))} />
        <MultiSelectFilter label="Status" options={statusList} value={filters.status ?? []} onChange={(status) => setFilters((f) => ({ ...f, status }))} />
        <MultiSelectFilter label="Customer" options={customerList} value={filters.customer ?? []} onChange={(customer) => setFilters((f) => ({ ...f, customer }))} />
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Gate out from</label>
          <input
            type="date"
            value={filters.gateOutFrom ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, gateOutFrom: e.target.value || undefined }))}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-muted">Gate out to</label>
          <input
            type="date"
            value={filters.gateOutTo ?? ''}
            onChange={(e) => setFilters((f) => ({ ...f, gateOutTo: e.target.value || undefined }))}
            className="h-10 rounded-lg border border-line bg-surface px-3 text-sm text-ink"
          />
        </div>
      </FilterBar>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted">
            <Truck size={28} />
            <p>No logistics orders match this search.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-surface [scrollbar-width:auto]">
          <table className="w-full min-w-[1000px] text-sm">
            <thead className="bg-canvas-alt text-xs text-muted">
              <tr>
                <SortHeader label="MO #" sortKey="systemId" sort={sort} onToggle={toggle} />
                <SortHeader label="Order Type" sortKey="orderType" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-left">Job #</th>
                <SortHeader label="Customer" sortKey="customer" sort={sort} onToggle={toggle} />
                <SortHeader label="Batch #" sortKey="batch" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-left">Items</th>
                <SortHeader label="Packages" sortKey="packages" sort={sort} onToggle={toggle} />
                <SortHeader label="Net Wt (kg)" sortKey="net" sort={sort} onToggle={toggle} align="right" />
                <SortHeader label="Gross Wt (kg)" sortKey="gross" sort={sort} onToggle={toggle} align="right" />
                <th className="px-3 py-2 text-left">Works</th>
                <SortHeader label="Incoterm" sortKey="incoterm" sort={sort} onToggle={toggle} />
                <SortHeader label="Status" sortKey="status" sort={sort} onToggle={toggle} />
                <SortHeader label="Arrival delay" sortKey="delay" sort={sort} onToggle={toggle} align="right" />
                <SortHeader label="Actual RFD" sortKey="actualRfd" sort={sort} onToggle={toggle} />
                <th className="px-3 py-2 text-left">Sent to Trucking</th>
                <th className="px-3 py-2 text-left"></th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((o) => {
                const jobNos = jobNumbers(o.items)
                const itemsSummary = o.items.map((it) => `${it.itemDetail}${it.quantity !== undefined ? ` ×${it.quantity}` : ''}`)
                const inMoGroup = !!o.moNo && (moCounts.get(o.moNo) ?? 0) > 1
                const works = o.packages.find((p) => p.packingWorks)?.packingWorks
                const colours = [...new Set(o.packages.map((p) => p.colourCode).filter(Boolean))]
                return (
                  <tr
                    key={o.systemId}
                    className={`cursor-pointer border-t border-line hover:bg-canvas-alt ${inMoGroup ? 'border-l-2 border-l-brand' : ''}`}
                    onClick={() => navigate(`/logistics-status/${o.systemId}`)}
                  >
                    <td className="px-3 py-2">
                      <div className="tabular-nums font-semibold">
                        {o.systemId}
                        {o.batchNo > 1 && (
                          <span className="ml-1 font-normal text-muted">({batchDisplayLabel(o.batchNo, o.batchLabel)})</span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">{orderTypeLabel(o.department, o.orderType)}</td>
                    <td className="px-3 py-2 text-[13px] tabular-nums" title={jobNos.join(', ') || undefined}>
                      {jobNos.length === 0 ? '—' : jobNos.length <= 2 ? jobNos.join(', ') : `${jobNos.slice(0, 2).join(', ')} +${jobNos.length - 2}`}
                    </td>
                    <td className="px-3 py-2">{o.customerName}</td>
                    <td className="px-3 py-2">
                      <span className="text-[13px]">{batchDisplayLabel(o.batchNo, o.batchLabel)}</span>
                      {inMoGroup && (
                        <span className="ml-1.5 rounded-full bg-brand/10 px-1.5 py-0.5 text-[10px] text-brand">MO group</span>
                      )}
                    </td>
                    <td className="px-3 py-2 max-w-[220px] truncate text-[13px]" title={itemsSummary.join(', ') || undefined}>
                      {itemsSummary.length === 0 ? '—' : itemsSummary.join(', ')}
                    </td>
                    <td className="px-3 py-2 text-[13px] text-muted">
                      {o.packages.length === 0 ? '—' : `${o.packages.length} pkg${o.packages.length === 1 ? '' : 's'}${colours.length ? ` (${colours.join(', ')})` : ''}`}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{num(totalNetWeight(o.items))}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{num(totalPackageGrossWeight(o.packages))}</td>
                    <td className="px-3 py-2 text-[13px] text-muted">{works || '—'}</td>
                    <td className="px-3 py-2 text-[13px]">{o.incoterm || '—'}</td>
                    <td className="px-3 py-2">
                      <StatusBadge label={o.status} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      <DelayCell days={arrivalDelayDays(o)} settled={!!o.actualArrivalDate} />
                    </td>
                    <td className="px-3 py-2 text-[13px] tabular-nums">
                      {(() => {
                        const actual = latestActualRfd(o.items)
                        const planned = latestPlannedRfd(o.items)
                        if (actual) return <span>{actual}</span>
                        if (planned) return <span className="text-muted" title="Planned RFD — not yet actualised">{planned} <span className="text-[10px]">(planned)</span></span>
                        return <span className="text-muted">—</span>
                      })()}
                    </td>
                    <td className="px-3 py-2">
                      <TruckingHandoffBadge order={o} />
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/logistics-status/${o.systemId}`)}
                          className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                        >
                          Open
                        </button>
                        {canEdit && (
                          <button
                            onClick={() => navigate(`/logistics-status/${o.systemId}/edit/order`)}
                            className="rounded border border-line px-2.5 py-1 text-[11px] hover:border-muted"
                          >
                            Edit
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <Pagination page={page} pageCount={pageCount} total={total} pageSize={pageSize} onPage={setPage} />

      </>
      )}
    </div>
  )
}
