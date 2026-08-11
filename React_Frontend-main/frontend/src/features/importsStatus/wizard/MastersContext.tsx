import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  fetchBranches, fetchSuppliers, fetchClearingAgents, fetchPorts,
  type MasterOption, type PortOption,
} from '@/lib/api/masters'

/**
 * Branch / supplier / port / clearing-agent master lists, fetched once and
 * shared across every wizard step via context — Step1 needs branches +
 * suppliers, Step3 needs ports, Step6 needs clearing agents, and
 * draftToPayload (lib/api/importsMap.ts) needs all four to resolve the names
 * the form holds into the ids the backend's FK columns want.
 */

interface MastersState {
  branches: MasterOption[]
  suppliers: MasterOption[]
  agents: MasterOption[]
  ports: PortOption[]
  loading: boolean
  error: string | null
}

const MastersCtx = createContext<MastersState | null>(null)

export function MastersProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<MastersState>({
    branches: [], suppliers: [], agents: [], ports: [], loading: true, error: null,
  })

  useEffect(() => {
    let cancelled = false

    Promise.all([fetchBranches(), fetchSuppliers(), fetchClearingAgents(), fetchPorts()])
      .then(([branches, suppliers, agents, ports]) => {
        if (cancelled) return
        setState({ branches, suppliers, agents, ports, loading: false, error: null })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setState((s) => ({
          ...s,
          loading: false,
          error: err instanceof Error ? err.message : 'Could not load master lists',
        }))
      })

    return () => { cancelled = true }
  }, [])

  return <MastersCtx.Provider value={state}>{children}</MastersCtx.Provider>
}

export function useMasters(): MastersState {
  const ctx = useContext(MastersCtx)
  if (!ctx) throw new Error('useMasters must be used within a MastersProvider')
  return ctx
}
