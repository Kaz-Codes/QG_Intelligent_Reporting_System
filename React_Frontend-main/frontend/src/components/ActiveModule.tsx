import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { PageKey } from '@/theme/tokens'

/**
 * Lets a page override which module's themed backdrop AppLayout shows,
 * instead of AppLayout always inferring it from the URL. Needed because
 * Dashboard now hosts Purchases/Inventory/Imports/Logistics as internal
 * tabs (one route, five "modules") — each tab still wants its own photo
 * backdrop, which a path-only lookup can't see.
 */

interface Ctx {
  override: PageKey | null
  setOverride: (module: PageKey | null) => void
}

const ActiveModuleContext = createContext<Ctx | null>(null)

export function ActiveModuleProvider({ children }: { children: ReactNode }) {
  const [override, setOverride] = useState<PageKey | null>(null)
  return <ActiveModuleContext.Provider value={{ override, setOverride }}>{children}</ActiveModuleContext.Provider>
}

function useActiveModuleContext() {
  const ctx = useContext(ActiveModuleContext)
  if (!ctx) throw new Error('useActiveModuleContext must be used within an ActiveModuleProvider')
  return ctx
}

export function useActiveModuleOverride() {
  return useActiveModuleContext().override
}

/** A page with its own internal tabs calls this with whichever module
 * should currently back it — the override is cleared automatically on
 * unmount (or when the module changes), so leaving the page always falls
 * back to AppLayout's normal path-based backdrop. */
export function useSetPageModule(module: PageKey | null) {
  const { setOverride } = useActiveModuleContext()
  useEffect(() => {
    setOverride(module)
    return () => setOverride(null)
  }, [module, setOverride])
}
