import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { LoginPage } from '@/features/auth/LoginPage'
import { ProtectedRoute } from '@/features/auth/ProtectedRoute'
import { AppLayout } from '@/components/AppLayout'
import { Dashboard } from '@/pages/Dashboard'
import { Purchases } from '@/pages/Purchases'
import { Inventory } from '@/pages/Inventory'
import { Imports } from '@/pages/Imports'
import { Logistics } from '@/pages/Logistics'
import { Reports } from '@/pages/Reports'
import { Assistant } from '@/pages/Assistant'
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
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/purchases" element={<Purchases />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/imports" element={<Imports />} />

            {/* Consignment tracking — separate from the Imports dashboard above.
                Nested so list/new/detail/edit share one parent path. */}
            <Route path="/imports-status">
              <Route index element={<ImportsStatusList />} />
              <Route path="new" element={<ImportsStatusWizard />} />
              <Route path=":id" element={<ImportsStatusDetail />} />
              <Route path=":id/edit/:step" element={<ImportsStatusWizard />} />
            </Route>

            {/* Logistics order tracking — Export/Local/Packing entry wizard,
                parallel to /imports-status. Separate from the Logistics
                dashboard route below. */}
            <Route path="/logistics-status">
              <Route index element={<LogisticsStatusList />} />
              <Route path="new" element={<LogisticsStatusWizard />} />
              <Route path=":id" element={<LogisticsStatusDetail />} />
              <Route path=":id/edit/:step" element={<LogisticsStatusWizard />} />
            </Route>

            <Route path="/logistics" element={<Logistics />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/assistant" element={<Assistant />} />
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
