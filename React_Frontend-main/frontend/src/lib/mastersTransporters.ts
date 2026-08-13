/**
 * Transporters master — MOCK, client-side only.
 *
 * The backend has no transporter master today (the registry has customer,
 * supplier, port, agent, branch, item — no transporter). This is a stand-in so
 * the Masters screen can offer a Transporters tab now, and so the trucking
 * wizard can pick from a managed list instead of free text. It lists and adds
 * in memory for the session.
 *
 * When the backend adds a real `transporter` master (a registry entry + model +
 * `/masters/transporter` routes, mirroring `supplier`), delete this file and
 * point the tab + the trucking dropdown at listMasters('transporter') /
 * createMaster('transporter'). Because it's in-memory, additions don't persist
 * across a reload.
 */

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

const SEED: TransporterRow[] = [
  { id: 1, name: 'Daewoo Logistics', contact_name: null, phone: null, ntn: null, is_active: true, is_verified: true, used: 0 },
  { id: 2, name: 'TCS Freight', contact_name: null, phone: null, ntn: null, is_active: true, is_verified: true, used: 0 },
  { id: 3, name: 'National Carriers', contact_name: null, phone: null, ntn: null, is_active: true, is_verified: true, used: 0 },
]

const TRANSPORTERS: TransporterRow[] = [...SEED]
let seq = SEED.length + 1

export function listTransporters(): TransporterRow[] {
  return [...TRANSPORTERS]
}

/** Just the active transporter names, for the trucking wizard dropdown. */
export function transporterNames(): string[] {
  return TRANSPORTERS.filter((t) => t.is_active).map((t) => t.name)
}

export function createTransporter(payload: Record<string, unknown>): TransporterRow {
  const name = String(payload.name ?? '').trim()
  if (!name) throw new Error('Name is required')
  if (TRANSPORTERS.some((t) => t.name.trim().toLowerCase() === name.toLowerCase())) {
    throw new Error('A transporter with this name already exists')
  }
  const row: TransporterRow = {
    id: seq++,
    name,
    contact_name: (payload.contact_name as string) ?? null,
    phone: (payload.phone as string) ?? null,
    ntn: (payload.ntn as string) ?? null,
    is_active: true,
    is_verified: true,
    used: 0,
  }
  TRANSPORTERS.unshift(row)
  return row
}
