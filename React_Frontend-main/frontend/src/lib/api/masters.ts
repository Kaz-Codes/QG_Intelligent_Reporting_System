import { apiFetch } from './client'

/**
 * Master-list lookups for the Imports wizard — `GET /masters/{master}`.
 *
 * Only what the wizard needs to turn a typed/picked NAME into the id the
 * backend's FK columns want (branch_id, supplier_id, loading_port_id,
 * delivery_port_id, clearing_agent_id). Note the masters module's envelope is
 * `{status, message, data, total}` — different from the data modules'
 * `{status_code, detail, data}`.
 *
 * Results are cached per master for the lifetime of the tab — the wizard
 * fetches once on mount, and a master list changing while someone has the
 * wizard open is rare enough not to warrant a refetch strategy.
 */

export interface MasterOption {
  id: number
  name: string
}

export interface PortOption extends MasterOption {
  port_type: string // "Sea" | "Air" | "Dry" | "Land"
  used_as: string // "Loading" | "Delivery" | "Both"
}

interface MastersEnvelope<T> {
  status: number
  message: string
  data: T[]
  total: number
}

const cache = new Map<string, Promise<unknown>>()

function fetchMaster<T>(master: string): Promise<T[]> {
  if (!cache.has(master)) {
    cache.set(
      master,
      apiFetch<MastersEnvelope<T>>(`/masters/${master}`).then((res) => res.data ?? []),
    )
  }
  return cache.get(master) as Promise<T[]>
}

export const fetchBranches = () => fetchMaster<MasterOption>('branch')
export const fetchSuppliers = () => fetchMaster<MasterOption>('supplier')
export const fetchClearingAgents = () => fetchMaster<MasterOption>('agent')
export const fetchPorts = () => fetchMaster<PortOption>('port')

/** Exact, case-insensitive name -> id. A typed value that doesn't match
 *  anything in the master (a typo, or a name not yet in the system) resolves
 *  to undefined — the caller omits that id from the payload rather than
 *  guessing, and the field stays whatever the backend's own validation says
 *  it is (e.g. "Branch is required" at submit time). */
export function nameToId(options: MasterOption[], name: string | undefined | null): number | undefined {
  if (!name) return undefined
  const needle = name.trim().toLowerCase()
  return options.find((o) => o.name.trim().toLowerCase() === needle)?.id
}
