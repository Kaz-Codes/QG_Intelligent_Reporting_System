import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import { LoginPage } from '@/features/auth/LoginPage'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { RequirePage } from '@/features/auth/RequirePage'
import { RootRedirect } from '@/features/auth/RootRedirect'
import { AppLayout } from '@/components/AppLayout'
import { Dashboard } from '@/pages/Dashboard'
import { Reports } from '@/pages/Reports'
import { Assistant } from '@/pages/Assistant'
import { UserManagement } from '@/pages/UserManagement'
import { ImportsStatusList } from '@/features/importsStatus/ImportsStatusList'
import { ImportsStatusDetail } from '@/features/importsStatus/ImportsStatusDetail'
import { ImportsStatusWizard } from '@/features/importsStatus/wizard/ImportsStatusWizard'
import { LogisticsStatusList } from '@/features/logisticsStatus/LogisticsStatusList'
import LogisticsStatusDetail from '@/features/logisticsStatus/LogisticsStatusDetail'
import { LogisticsStatusWizard } from '@/features/logisticsStatus/wizard/LogisticsStatusWizard'
import { TruckingStatusList } from '@/features/truckingStatus/TruckingStatusList'
import { TruckingStatusDetail } from '@/features/truckingStatus/TruckingStatusDetail'
import { TruckingStatusWizard } from '@/features/truckingStatus/wizard/TruckingStatusWizard'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            {/* Purchases/Inventory/Imports/Logistics no longer have their
                own routes — they're tabs inside Dashboard now. */}
            <Route path="/dashboard" element={<RequirePage pageKey="dashboard"><Dashboard /></RequirePage>} />

            {/* Consignment tracking + Logistics order tracking + Trucking
                Status — grouped in the sidebar as "Operations", gated
                together the same way. */}
            <Route element={<RequirePage pageKey="dataEntry"><Outlet /></RequirePage>}>
              <Route path="/imports-status">
                <Route index element={<ImportsStatusList />} />
                <Route path="new" element={<ImportsStatusWizard />} />
                <Route path=":id" element={<ImportsStatusDetail />} />
                <Route path=":id/edit/:step" element={<ImportsStatusWizard />} />
              </Route>

              <Route path="/logistics-status">
                <Route index element={<LogisticsStatusList />} />
                <Route path="new" element={<LogisticsStatusWizard />} />
                <Route path=":id" element={<LogisticsStatusDetail />} />
                <Route path=":id/edit/:step" element={<LogisticsStatusWizard />} />
              </Route>

              <Route path="/trucking-status">
                <Route index element={<TruckingStatusList />} />
                <Route path="new" element={<TruckingStatusWizard />} />
                <Route path=":id" element={<TruckingStatusDetail />} />
                <Route path=":id/edit/:step" element={<TruckingStatusWizard />} />
              </Route>
            </Route>

            <Route path="/reports" element={<RequirePage pageKey="reports"><Reports /></RequirePage>} />
            <Route path="/assistant" element={<RequirePage pageKey="assistant"><Assistant /></RequirePage>} />
            <Route path="/user-management" element={<RequirePage pageKey="userManagement"><UserManagement /></RequirePage>} />
          </Route>
        </Route>

        <Route path="/" element={<RootRedirect />} />
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
