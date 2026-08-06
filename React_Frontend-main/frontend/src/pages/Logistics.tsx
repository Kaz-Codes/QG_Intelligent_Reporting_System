import { useState } from 'react'
import { Truck } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { SegmentedControl } from '@/components/SegmentedControl'
import { ShipmentsView } from './logistics/ShipmentsView'
import { PackingView } from './logistics/PackingView'
import { TransportView } from './logistics/TransportView'

const VIEWS = [
  { value: 'shipments', label: 'Export Shipments' },
  { value: 'packing', label: 'Packing' },
  { value: 'transport', label: 'Transport' },
] as const

export function Logistics() {
  const [view, setView] = useState<(typeof VIEWS)[number]['value']>('shipments')

  return (
    <div className="flex flex-col gap-6">
      {/* Hero band — same role as Dashboard's greeting card: an open,
          low-density area over the module's photo backdrop (see
          ThemedBackground's MODULE_PHOTOS) before the filter bar and
          KPI/chart grid below get dense. Kept to title/subtitle + the view
          switcher rather than adding fabricated summary numbers here —
          each of the four views below computes its own filtered stats
          independently, so a real cross-view KPI would need shared state
          this page doesn't have yet; flag if that's wanted next. */}
      <Card className="p-6 lg:p-8">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <span className="mb-2 inline-flex items-center gap-1.5 rounded-full border border-brand/25 bg-brand-soft px-3 py-1 text-xs font-semibold text-brand">
              <Truck size={12} />
              Logistics
            </span>
            <h1 className="font-display text-2xl font-extrabold leading-tight tracking-tight text-navy lg:text-3xl">
              Export shipments &amp; transport
            </h1>
            <p className="mt-1 max-w-md text-sm text-muted">Shipments, packing, and transport in one place.</p>
          </div>
          <SegmentedControl options={VIEWS} value={view} onChange={setView} variant="solid" />
        </div>
      </Card>

      <div key={view} className="animate-fade-in-up">
        {view === 'shipments' && <ShipmentsView />}
        {view === 'packing' && <PackingView />}
        {view === 'transport' && <TransportView />}
      </div>
    </div>
  )
}
