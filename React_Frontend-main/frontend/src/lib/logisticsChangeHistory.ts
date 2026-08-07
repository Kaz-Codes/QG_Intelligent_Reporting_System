import {
  buildMockHistory, mulberry32, seedFrom,
  type ChangeHistoryEntry, type SectionSpec, type CollectionSpec,
} from './changeHistory'

/** Mock change history for Logistics Status — field vocabulary mirrors the
 *  wizard's own steps (schema.ts WIZARD_STEPS). See importsChangeHistory.ts
 *  for the shared engine and the eventual real-backend field mapping. */

const SECTIONS: SectionSpec[] = [
  {
    key: 'order', label: 'Order Details',
    fields: [
      { key: 'orderType', label: 'Order type', kind: 'text', options: ['Export', 'Local'] },
      { key: 'department', label: 'Department', kind: 'text', options: ['Cement', 'Sugar', 'General'] },
      { key: 'customerName', label: 'Customer', kind: 'text', options: ['Al Rawabi Trading', 'Nile Delta Co.', 'Karachi Steel Works'] },
      { key: 'moNo', label: 'MO No.', kind: 'text' },
      { key: 'incoterm', label: 'Incoterm', kind: 'text', options: ['FOB', 'CIF', 'CFR', 'EXW'] },
    ],
  },
  {
    key: 'shipping', label: 'Shipping',
    fields: [
      { key: 'pol', label: 'Port of loading', kind: 'text' },
      { key: 'pod', label: 'Port of discharge', kind: 'text' },
      { key: 'shippingLine', label: 'Shipping line', kind: 'text', options: ['Maersk', 'MSC', 'CMA CGM'] },
      { key: 'bookingNo', label: 'Booking no.', kind: 'text' },
      { key: 'portInDate', label: 'Port-in date', kind: 'date' },
      { key: 'etdSailingDate', label: 'ETD sailing', kind: 'date' },
    ],
  },
  {
    key: 'expenditures', label: 'Expenditures',
    fields: [
      { key: 'packingCost', label: 'Packing cost', kind: 'money' },
      { key: 'transportationCharges', label: 'Transportation charges', kind: 'money' },
      { key: 'containerDetention', label: 'Container detention', kind: 'money' },
      { key: 'seaAirFreight', label: 'Sea/air freight', kind: 'money' },
    ],
  },
  {
    key: 'status', label: 'Status',
    fields: [
      { key: 'status', label: 'Status', kind: 'text', options: ['Under Production', 'Under Packing', 'Transportation', 'On Water', 'Delivered'] },
      { key: 'gateOutDate', label: 'Gate out date', kind: 'date' },
      { key: 'sentToTrucking', label: 'Sent to trucking', kind: 'text', options: ['Yes', 'No'] },
    ],
  },
]

const COLLECTIONS: CollectionSpec[] = [
  {
    key: 'items', label: 'Items', rowNoun: 'Item',
    fields: [
      { key: 'itemDetail', label: 'Item detail', kind: 'text', options: ['Cement bags 50kg', 'Sugar sacks 50kg', 'Steel coil'] },
      { key: 'quantity', label: 'Quantity', kind: 'number' },
      { key: 'unitWeight', label: 'Unit weight (kg)', kind: 'number' },
    ],
  },
  {
    key: 'packages', label: 'Packages', rowNoun: 'Package',
    fields: [
      { key: 'colourCode', label: 'Colour code', kind: 'text' },
      { key: 'status', label: 'Status', kind: 'text', options: ['Under Packing', 'Under Paint', 'Packed'] },
      { key: 'grossWeight', label: 'Gross weight (kg)', kind: 'number' },
    ],
  },
]

const CACHE = new Map<string, ChangeHistoryEntry[]>()

export function getOrderChangeHistory(orderId: string): ChangeHistoryEntry[] {
  const cached = CACHE.get(orderId)
  if (cached) return cached
  const built = buildMockHistory(orderId, SECTIONS, COLLECTIONS)
  CACHE.set(orderId, built)
  return built
}

export function getRecordProvenance(orderId: string): { createdBy: string; createdAt: string } {
  const rng = mulberry32(seedFrom(`${orderId}-created`))
  const staff = ['A. Rehman', 'S. Fatima', 'M. Tariq', 'H. Baig', 'N. Qureshi']
  const createdBy = staff[Math.floor(rng() * staff.length)]
  const base = new Date('2026-01-15T09:00:00Z').getTime()
  const createdAt = new Date(base + Math.floor(rng() * 150) * 86_400_000).toISOString()
  return { createdBy, createdAt }
}

export function revertChangeHistoryEntry(orderId: string, entryId: string, revertedBy: string): boolean {
  const entries = getOrderChangeHistory(orderId)
  const newestActive = entries.find((e) => !e.isReverted)
  if (!newestActive || newestActive.id !== entryId) return false

  newestActive.isReverted = true
  newestActive.revertedBy = revertedBy
  newestActive.revertedAt = new Date().toISOString()
  return true
}
