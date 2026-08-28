import { useState } from 'react'
import { SegmentedControl } from '@/components/SegmentedControl'
import { useAuth } from '@/features/auth/AuthContext'
import { canViewDashboard } from '@/lib/roleAccess'
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
  { value: 'overview', label: 'Supply Chain' },
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
  const { user } = useAuth()

  //-----------------------------------------------------
  // A TAB IS A NAV ENTRY TOO.
  //
  // Each of these five has its OWN backend permission
  // (can_view_{overview,imports,logistics,purchases,inventory}_dashboard), but
  // the bar rendered all five to everyone. Reaching this page only means the
  // account can see AT LEAST ONE of them — pagesForUser gates /dashboard on
  // "any dashboard permission" — so an inventory-only account was shown four
  // tabs whose contents it could not load.
  //
  // Same rule as the Operations group in TopNav: show what the account can
  // actually open. And the same caveat — THIS IS NOT ACCESS CONTROL. Each
  // dashboard endpoint authorizes on its own and returns 403 regardless of
  // which tabs were drawn; hiding a tab only stops someone being shown a
  // panel that was going to fail.
  //-----------------------------------------------------
  const tabs = DASH_TABS.filter((t) => canViewDashboard(user, t.value))

  // Opens on the first tab the account can see, not unconditionally on
  // Overview — which is precisely the one a module-scoped account tends not
  // to have.
  const [tab, setTab] = useState<DashTab>(tabs[0]?.value ?? 'overview')
  useSetPageModule(TAB_MODULE[tab])

  if (tabs.length === 0) {
    // Not reachable through the nav (pagesForUser would not have offered
    // /dashboard), but a direct URL plus a permission change can get here.
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-3xl font-bold text-navy">Dashboards</h1>
        <p className="text-sm text-muted">
          You do not have access to any dashboard. Ask an admin if you think
          this is wrong.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold text-navy">Dashboards</h1>
          <p className="text-sm text-muted">Executive overview, plus each module's own dashboard</p>
        </div>
        <SegmentedControl options={tabs} value={tab} onChange={setTab} />
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'purchases' && <Purchases />}
      {tab === 'inventory' && <Inventory />}
      {tab === 'imports' && <Imports />}
      {tab === 'logistics' && <Logistics />}
    </div>
  )
}
