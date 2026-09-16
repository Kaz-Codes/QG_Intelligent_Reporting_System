import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryCache, QueryClient, QueryClientProvider, MutationCache } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { ThemeProvider } from '@/theme/ThemeContext'
import { AuthProvider } from '@/features/auth/AuthContext'
import { ApiError } from '@/lib/api/client'
import { forceLogout } from '@/features/auth/forceLogout'

// A session can expire server-side (idle, or the 3-hour absolute cap) while
// the user is mid-interaction, independent of the idle-timeout's own local
// timer - the very next API call just comes back 401. This is the one
// central place that catches that and forces a logout, so no individual
// screen has to handle it (and none can forget to). Constructed here, not
// inside a component - see forceLogout.ts for why it's a hard redirect
// rather than a Router navigate() as a result.
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) forceLogout()
    },
  }),
  mutationCache: new MutationCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) forceLogout()
    },
  }),
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
