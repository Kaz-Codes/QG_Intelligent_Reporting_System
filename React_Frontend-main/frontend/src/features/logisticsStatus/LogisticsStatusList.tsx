import { useMemo, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Truck } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { FilterBar } from '@/components/FilterBar'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  getLogisticsOrders, type LogisticsOrder, type LogisticsFilters,
} from '@/lib/logisticsStatusData'

const num = (v: number) => v.toLocaleString('en-US')
const dateShort = (v?: string) => {
  if (!v) return '—'
  const d = new Date(v)
  if (Number.isNaN(+d)) return '—'
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`
}

export function LogisticsStatusList() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const [filters, setFilters] = useState<LogisticsFilters>({})

  const rows = useMemo(() => getLogisticsOrders(filters), [filters])

  /* Export runs on the current filtered set — same convention as
   * features/importsStatus/ImportsStatusList.tsx's exportCsv. */
  const exportCsv = () => {
    const cols = [
      'System ID', 'Order Type', 'Customer', 'Item Detail', 'Quantity', 'IDM',
      'Origin / Export No.', 'Destination', 'Status', 'Gate Out Date', 'Actual Delivery Date',
    ]
    const line = (o: LogisticsOrder) => [
      o.systemId, o.orderType, o.customerName, o.itemDetail, o.quantity, o.idm,
      o.orderType === 'Export' ? `${o.originCountry} · ${o.exportNo}` : `${o.originCity}, ${o.originProvince}`,
      o.destination, o.status, o.gateOutDate, o.actualDeliveryDate,
    ].map((v) => {
      const s = String(v ?? '')
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }).join(',')

    const csv = [cols.join(','), ...rows.map(line)].join('\r\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `logistics_orders_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Logistics Status" subtitle={`${rows.length} shown`} module="logisticsStatus" />
        <div className="flex gap-2">
          <Button variant="outline" onClick={exportCsv}>Export Excel</Button>
          <Button variant="outline" onClick={() => window.print()}>Export PDF</Button>
          {can(user, 'enter') && (
            <Button asChild>
              <Link to="/logistics-status/new">New Logistics Order</Link>
            </Button>
          )}
        </div>
      </div>

      <FilterBar
        search={{
          value: filters.search ?? '',
          onChange: (search) => setFilters((f) => ({ ...f, search })),
          placeholder: 'ID, customer, item, IDM…',
        }}
      >
        <span className="text-xs text-muted">Showing all order types and statuses</span>
      </FilterBar>

      {rows.length === 0 ? (
        <Card>
          <CardContent className="flex h-48 flex-col items-center justify-center gap-2 text-center text-muted">
            <Truck size={28} />
            <p>No logistics orders match this search.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-auto rounded-xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-canvas-alt text-xs text-muted">
              <tr>
                <th className="px-3 py-2 text-left">ID</th>
                <th className="px-3 py-2 text-left">Order type</th>
                <th className="px-3 py-2 text-left">Customer</th>
                <th className="px-3 py-2 text-left">Item detail</th>
                <th className="px-3 py-2 text-right">Quantity</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Destination</th>
                <th className="px-3 py-2 text-right">Gate out</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => (
                <tr
                  key={o.systemId}
                  className="cursor-pointer border-t border-line hover:bg-canvas-alt"
                  onClick={() => navigate(`/logistics-status/${o.systemId}`)}
                >
                  <td className="px-3 py-2 font-semibold tabular-nums">{o.systemId}</td>
                  <td className="px-3 py-2">{o.orderType}</td>
                  <td className="px-3 py-2">{o.customerName}</td>
                  <td className="px-3 py-2">{o.itemDetail}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(o.quantity)}</td>
                  <td className="px-3 py-2">
                    <span className="inline-block rounded-full border border-brand/30 bg-brand-soft px-2.5 py-0.5 text-xs font-medium text-brand whitespace-nowrap">
                      {o.status}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-[13px] text-muted">
                    {o.orderType === 'Export' ? o.destination : `${o.originCity}, ${o.originProvince}`}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{dateShort(o.gateOutDate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
