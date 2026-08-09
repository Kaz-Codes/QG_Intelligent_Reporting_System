/**
 * Customers master — MOCK, client-side only.
 *
 * The backend has no customer master today (no model, table, or endpoint —
 * customers are free-text `customer_name` on logistics orders). This is a
 * stand-in so the Masters screen can offer a Customers tab now: it lists and
 * adds customers in memory for the session. When the backend adds a real
 * `customer` master (a registry entry + model + `/masters/customer` routes,
 * mirroring supplier), delete this file and point the Customers tab at
 * listMasters('customer')/createMaster('customer') like the others — the tab
 * config in MastersPage already matches that shape.
 *
 * Because it's in-memory, additions don't persist across a reload.
 */

export interface CustomerRow {
  id: number
  name: string
  country: string | null
  city: string | null
  contact_name: string | null
  phone: string | null
  email: string | null
  is_active: boolean
  is_verified: boolean
  used: number
}

const SEED: CustomerRow[] = [
  { id: 1, name: 'Packages Ltd', country: 'Pakistan', city: 'Lahore', contact_name: null, phone: null, email: null, is_active: true, is_verified: true, used: 0 },
  { id: 2, name: 'Century Paper', country: 'Pakistan', city: 'Kasur', contact_name: null, phone: null, email: null, is_active: true, is_verified: true, used: 0 },
  { id: 3, name: 'Nishat Mills', country: 'Pakistan', city: 'Faisalabad', contact_name: null, phone: null, email: null, is_active: true, is_verified: true, used: 0 },
]

const CUSTOMERS: CustomerRow[] = [...SEED]
let seq = SEED.length + 1

export function listCustomers(): CustomerRow[] {
  return [...CUSTOMERS]
}

export function createCustomer(payload: Record<string, unknown>): CustomerRow {
  const name = String(payload.name ?? '').trim()
  if (CUSTOMERS.some((c) => c.name.trim().toLowerCase() === name.toLowerCase())) {
    // Mirror the backend's plain-message uniqueness clash.
    throw new Error('A customer with this name already exists')
  }
  const row: CustomerRow = {
    id: seq++,
    name,
    country: (payload.country as string) ?? null,
    city: (payload.city as string) ?? null,
    contact_name: (payload.contact_name as string) ?? null,
    phone: (payload.phone as string) ?? null,
    email: (payload.email as string) ?? null,
    is_active: true,
    is_verified: true,
    used: 0,
  }
  CUSTOMERS.unshift(row)
  return row
}
