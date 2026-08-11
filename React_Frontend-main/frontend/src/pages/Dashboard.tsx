import { useState } from 'react'
import { SegmentedControl } from '@/components/SegmentedControl'
import { useSetPageModule } from '@/components/ActiveModule'
import { OverviewTab } from '@/features/overview/OverviewTab'
import { Purchases } from '@/pages/Purchases'
import { Inventory } from '@/pages/Inventory'
import { Imports } from '@/pages/Imports'
import { Logistics } from '@/pages/Logistics'

/**
 * The dashboards shell: a tab per module, plus the cross-module overview.
 *
 * This file used to BE the overview — several hundred lines of hardcoded KPIs,
 * a fabricated weekly trend, invented alerts and made-up supplier scores from
 * `lib/mockData/dashboard`. All of it is gone; the overview now lives in
 * features/overview and reads `/dashboard/overview`, so every dashboard in the
 * app is on real data.
 */

const DASH_TABS = [
  { value: 'overview', label: 'Overview' },
  { value: 'purchases', label: 'Purchases' },
  { value: 'inventory', label: 'Inventory' },
  { value: 'imports', label: 'Imports' },
  { value: 'logistics', label: 'Logistics' },
] as const

type DashTab = (typeof DASH_TABS)[number]['value']

const TAB_MODULE = {
  overview: 'dashboard', purchases: 'purchases', inventory: 'inventory',
  imports: 'imports', logistics: 'logistics',
} as const

export function Dashboard() {
  const [tab, setTab] = useState<DashTab>('overview')
  useSetPageModule(TAB_MODULE[tab])

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold text-navy">Dashboards</h1>
          <p className="text-sm text-muted">Executive overview, plus each module's own dashboard</p>
        </div>
        <SegmentedControl options={DASH_TABS} value={tab} onChange={setTab} />
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'purchases' && <Purchases />}
      {tab === 'inventory' && <Inventory />}
      {tab === 'imports' && <Imports />}
      {tab === 'logistics' && <Logistics />}
    </div>
  )
}
