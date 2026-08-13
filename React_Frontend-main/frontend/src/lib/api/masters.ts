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
export const fetchTransporters = () => fetchMaster<MasterOption>('transporter')

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


/* ---------------------------------------------------------------------------
 * Masters management screen — list + create.
 *
 * The read-only lookups above feed the Imports wizard. The Masters SCREEN
 * needs a bit more: the full row (so a table can show country/city/type/etc.),
 * plus the ability to add a record. Both hit the same `/masters/{master}`
 * path — GET to list, POST to create — behind the `{status, message, data}`
 * envelope the masters module uses.
 *
 * The backend registry defines: customer, supplier, port, agent, transporter,
 * branch, item. This screen exposes the ones an ops user maintains by hand —
 * items are excluded because item data entry is not done here.
 *
 * There is no "works" master. Works and Branch are the same thing to the
 * business (the imports sheet's "Works" column is what fills a consignment's
 * branch), so the duplicate list was removed from the backend registry and
 * from this screen together.
 * ------------------------------------------------------------------------- */

export type MasterKey = 'customer' | 'supplier' | 'branch' | 'port' | 'agent' | 'transporter'

export interface SupplierRow {
  id: number
  name: string
  country: string | null
  city: string | null
  contact_name: string | null
  phone: string | null
  email: string | null
  default_currency: string | null
  default_payment_terms: string | null
  is_active: boolean
  is_verified: boolean
  used: number
}

export interface BranchRow {
  id: number
  name: string
  code: string | null
  city: string | null
  address: string | null
  is_active: boolean
  is_verified: boolean
  used: number
}

/** Name only, by decision — the logistics workbooks carry nothing else about a
 *  customer. `used` is how many logistics orders point at this customer. */
export interface CustomerRow {
  id: number
  name: string
  is_active: boolean
  is_verified: boolean
  used: number
}

export interface PortRow {
  id: number
  name: string
  country: string | null
  port_type: string
  un_locode: string | null
  used_as: string
  is_active: boolean
  is_verified: boolean
  used: number
}

export interface AgentRow {
  id: number
  name: string
  licence_no: string | null
  contact_name: string | null
  phone: string | null
  primary_port_id: number | null
  primary_port: { id: number; name: string } | null
  is_active: boolean
  is_verified: boolean
  used: number
}

/** Name + light contact info, plus NTN (the Pakistani tax number — the
 *  closest existing analog is ClearingAgent.licence_no, but this is a
 *  distinct concept so it gets its own field). `used` is how many trucking
 *  jobs point at this transporter. */
export interface TransporterRow {
  id: number
  name: string
  contact_name: string | null
  phone: string | null
  ntn: string | null
  is_active: boolean
  is_verified: boolean
  used: number
}

export type MasterRow = SupplierRow | BranchRow | CustomerRow | PortRow | AgentRow | TransporterRow

export const CURRENCIES = ['USD', 'EUR', 'CNY', 'JPY', 'GBP', 'AED'] as const
export const PORT_TYPES = ['Sea', 'Air', 'Dry', 'Land'] as const
export const PORT_USED_AS = ['Loading', 'Delivery', 'Both'] as const

interface ListParams {
  q?: string
  includeInactive?: boolean
}

/** List one master's rows. Fresh call each time (not the wizard's cache) since
 *  the screen adds/edits and needs to see its own writes. */
export async function listMasters<T extends MasterRow = MasterRow>(
  master: MasterKey,
  { q, includeInactive }: ListParams = {},
): Promise<T[]> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (includeInactive) params.set('include_inactive', 'true')
  const qs = params.toString()
  const res = await apiFetch<MastersEnvelope<T>>(`/masters/${master}${qs ? `?${qs}` : ''}`)
  return res.data ?? []
}

/** Create a master record. Lands verified (the proper Masters-screen path,
 *  unlike an inline-created record which waits for review). Returns the new
 *  row. The backend enforces name uniqueness and replies 400 with a plain
 *  message on a clash — surfaced to the caller as an ApiError. */
export async function createMaster<T extends MasterRow = MasterRow>(
  master: MasterKey,
  payload: Record<string, unknown>,
): Promise<T> {
  const res = await apiFetch<{ status: number; message: string; data: T }>(
    `/masters/${master}`,
    { method: 'POST', body: JSON.stringify(payload) },
  )
  // A create can also invalidate the wizard's read-only cache for this master;
  // clear it so a wizard opened later sees the new option.
  cache.delete(master)
  return res.data
}
