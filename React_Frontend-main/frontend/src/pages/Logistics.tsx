import { useState } from 'react'
import { PageHeader } from '@/components/PageHeader'
import { SegmentedControl } from '@/components/SegmentedControl'
import { ShipmentsView } from './logistics/ShipmentsView'
import { PackingView } from './logistics/PackingView'
import { TransportView } from './logistics/TransportView'
import { DocumentationView } from './logistics/DocumentationView'

const VIEWS = [
  { value: 'shipments', label: 'Export Shipments' },
  { value: 'packing', label: 'Packing' },
  { value: 'transport', label: 'Transport' },
  { value: 'documentation', label: 'Export Documentation' },
] as const

export function Logistics() {
  const [view, setView] = useState<(typeof VIEWS)[number]['value']>('shipments')

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader title="Logistics" subtitle="Export shipments/documentation, plus packing and transport" module="logistics" />
        <SegmentedControl options={VIEWS} value={view} onChange={setView} />
      </div>

      <div key={view} className="animate-fade-in-up">
        {view === 'shipments' && <ShipmentsView />}
        {view === 'packing' && <PackingView />}
        {view === 'transport' && <TransportView />}
        {view === 'documentation' && <DocumentationView />}
      </div>
    </div>
  )
}
