import { Link, useParams } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/features/auth/AuthContext'
import { can } from '@/lib/roleAccess'
import {
  freightSavings,
  ratePerKg,
  totalGrossWeight,
  totalNetWeight,
  outstanding,
  trackingRollup,
} from './schema'
import { getTruckingJobs, sourceLabel, type TruckingRow } from '@/lib/truckingStatusData'

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-line py-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className="text-right text-ink">{value ?? '—'}</span>
    </div>
  )
}

export function TruckingStatusDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const row: TruckingRow | undefined = getTruckingJobs().find((r) => r.systemId === id)
  const canEdit = can(user, 'editAny') || can(user, 'editOwnDraft')

  if (!row) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title={`Trucking Job ${id}`} subtitle="Detail view" module="truckingStatus" />
        <Card>
          <CardContent className="flex h-40 items-center justify-center text-muted">
            No trucking job found for {id}.
          </CardContent>
        </Card>
      </div>
    )
  }

  const gross = totalGrossWeight(row.vehicles)
  const net = totalNetWeight(row.vehicles)
  const savings = freightSavings(row.quotedFreight, row.actualFreight)
  const rate = ratePerKg(row.actualFreight, gross)
  const out = outstanding(row.actualFreight, row.paidAmount)
  const rollup = trackingRollup(row.vehicles)
  const isDerived = row.source !== 'manual'

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title={`Trucking Job ${row.systemId}`}
          subtitle={`${row.movementType} · ${sourceLabel(row.source)}`}
          module="truckingStatus"
        />
        {canEdit && !isDerived && (
          <Button asChild variant="outline">
            <Link to={`/trucking-status/${row.systemId}/edit/1`}>Edit</Link>
          </Button>
        )}
      </div>

      {isDerived && (
        <div className="rounded-lg border border-line bg-canvas-alt px-4 py-3 text-sm text-muted">
          This is a live request reflected from {sourceLabel(row.source)}. It updates automatically with
          its source — add vehicles and tracking here once the trucking team takes it on.
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardContent className="p-5">
            <h3 className="mb-3 text-sm font-semibold text-ink">Movement & Item</h3>
            <Row label="Execution date" value={row.executionDate} />
            <Row label="Transporter" value={row.transporterName} />
            <Row label="Shifting type" value={row.shiftingType} />
            <Row label="Item details" value={row.itemDetails} />
            <Row label="Pickup" value={row.pickup} />
            <Row label="Destination" value={row.destination} />
            {row.movementType !== 'Intrafactory' && <Row label="Reference / IDM" value={row.referenceNo} />}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            <h3 className="mb-3 text-sm font-semibold text-ink">Freight & Payment</h3>
            <Row label="Quoted freight" value={row.quotedFreight != null ? `Rs. ${row.quotedFreight}` : undefined} />
            <Row label="Actual freight" value={row.actualFreight != null ? `Rs. ${row.actualFreight}` : undefined} />
            <Row label="Savings" value={savings != null ? `Rs. ${savings.toFixed(2)}` : undefined} />
            <Row label="Rate per kg" value={rate != null ? `Rs. ${rate.toFixed(2)}` : undefined} />
            <Row label="Payment status" value={row.paymentStatus} />
            <Row label="Paid" value={row.paidAmount != null ? `Rs. ${row.paidAmount}` : undefined} />
            <Row label="Outstanding" value={out != null ? `Rs. ${out.toFixed(2)}` : undefined} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-ink">
              Vehicles ({row.vehicles.length}) · {rollup.label}
            </h3>
            <span className="text-xs text-muted">
              Gross {gross.toFixed(2)} kg · Net {net.toFixed(2)} kg
            </span>
          </div>
          {row.vehicles.length === 0 ? (
            <p className="text-sm text-muted">No vehicles assigned yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted">
                  <tr>
                    <th className="py-1 pr-3">#</th>
                    <th className="py-1 pr-3">Vehicle</th>
                    <th className="py-1 pr-3">Type</th>
                    <th className="py-1 pr-3">Packages</th>
                    <th className="py-1 pr-3">Gross</th>
                    <th className="py-1 pr-3">Driver</th>
                    {row.movementType === 'Inbound' && <th className="py-1 pr-3">Container</th>}
                    <th className="py-1 pr-3">Tracking</th>
                    <th className="py-1 pr-3">Builty</th>
                  </tr>
                </thead>
                <tbody className="text-ink">
                  {row.vehicles.map((v, i) => (
                    <tr key={i} className="border-t border-line">
                      <td className="py-1 pr-3">{i + 1}</td>
                      <td className="py-1 pr-3">{v.vehicleNumber || '—'}</td>
                      <td className="py-1 pr-3">{v.vehicleType || '—'}</td>
                      <td className="py-1 pr-3 tabular-nums">{v.noOfPackages ?? '—'}</td>
                      <td className="py-1 pr-3 tabular-nums">{v.grossWeight ?? '—'}</td>
                      <td className="py-1 pr-3">{v.driverPhone || '—'}</td>
                      {row.movementType === 'Inbound' && (
                        <td className="py-1 pr-3">{v.containerNo ? `${v.containerNo} (${v.containerType || '?'})` : '—'}</td>
                      )}
                      <td className="py-1 pr-3">{v.trackingStatus || '—'}</td>
                      <td className="py-1 pr-3">{v.builtyStatus || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
