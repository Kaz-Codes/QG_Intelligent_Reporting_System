import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import { LoginPage } from '@/features/auth/LoginPage'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { RequirePage } from '@/features/auth/RequirePage'
import { RootRedirect } from '@/features/auth/RootRedirect'
import { AppLayout } from '@/components/AppLayout'
import { Dashboard } from '@/pages/Dashboard'
import { Purchases } from '@/pages/Purchases'
import { Inventory } from '@/pages/Inventory'
import { Imports } from '@/pages/Imports'
import { Logistics } from '@/pages/Logistics'
import { Reports } from '@/pages/Reports'
import { Assistant } from '@/pages/Assistant'
import { UserManagement } from '@/pages/UserManagement'
import { ImportsStatusList } from '@/features/importsStatus/ImportsStatusList'
import { ImportsStatusDetail } from '@/features/importsStatus/ImportsStatusDetail'
import { ImportsStatusWizard } from '@/features/importsStatus/wizard/ImportsStatusWizard'
import { LogisticsStatusList } from '@/features/logisticsStatus/LogisticsStatusList'
import { LogisticsStatusDetail } from '@/features/logisticsStatus/LogisticsStatusDetail'
import { LogisticsStatusWizard } from '@/features/logisticsStatus/wizard/LogisticsStatusWizard'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<RequirePage pageKey="dashboard"><Dashboard /></RequirePage>} />
            <Route path="/purchases" element={<RequirePage pageKey="purchases"><Purchases /></RequirePage>} />
            <Route path="/inventory" element={<RequirePage pageKey="inventory"><Inventory /></RequirePage>} />
            <Route path="/imports" element={<RequirePage pageKey="imports"><Imports /></RequirePage>} />

            {/* Consignment tracking + Logistics order tracking — grouped in
                the sidebar as "Operations", gated together the same way. */}
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
            </Route>

            <Route path="/logistics" element={<RequirePage pageKey="logistics"><Logistics /></RequirePage>} />
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
