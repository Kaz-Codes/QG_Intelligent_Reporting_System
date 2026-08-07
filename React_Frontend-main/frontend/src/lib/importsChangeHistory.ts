import {
  buildMockHistory, mulberry32, seedFrom,
  type ChangeHistoryEntry, type SectionSpec, type CollectionSpec,
} from './changeHistory'

/**
 * Mock change history for Imports Status. Field vocabulary mirrors the
 * wizard's own steps (schema.ts WIZARD_STEPS) so a card's sections line up
 * 1:1 with the step a correction would actually be made on.
 */

const SECTIONS: SectionSpec[] = [
  {
    key: 'consignment', label: 'Consignment',
    fields: [
      { key: 'branch', label: 'Branch', kind: 'text', options: ['Qadcast', 'Qadri Brothers Unit 2', 'Qadri Engineering', 'Qadbros Engineering'] },
      { key: 'supplier', label: 'Supplier', kind: 'text', options: ['Wuxi Kaiyuan Machinery', 'SKF Sverige AB', 'Siemens AG', 'Bosch Rexroth AG'] },
      { key: 'origin', label: 'Country of origin', kind: 'text', options: ['China', 'Germany', 'Sweden', 'Japan'] },
      { key: 'currency', label: 'Currency', kind: 'text', options: ['USD', 'EUR', 'JPY'] },
      { key: 'incoterm', label: 'Incoterm', kind: 'text', options: ['FOB', 'CIF', 'CFR', 'EXW'] },
      { key: 'requisitionDate', label: 'Requisition date', kind: 'date' },
      { key: 'requiredDate', label: 'Required date', kind: 'date' },
    ],
  },
  {
    key: 'finance', label: 'Finance',
    fields: [
      { key: 'paymentInstrument', label: 'Payment instrument', kind: 'text', options: ['LC', 'Adv', 'DP', 'CAD'] },
      { key: 'instrumentNo', label: 'Instrument number', kind: 'text' },
      { key: 'works', label: 'Works', kind: 'text', options: ['Qadcast', 'Qadri Brothers Unit 2', 'Qadri Engineering'] },
      { key: 'exchangeRate', label: 'Exchange rate', kind: 'number' },
      { key: 'rateDate', label: 'Rate booked on', kind: 'date' },
    ],
  },
  {
    key: 'shipping', label: 'Shipping',
    fields: [
      { key: 'modeOfShipment', label: 'Mode of shipment', kind: 'text', options: ['Sea freight FCL', 'Sea freight LCL', 'Air freight'] },
      { key: 'portOfLoading', label: 'Port of loading', kind: 'text' },
      { key: 'portOfDelivery', label: 'Port of delivery', kind: 'text' },
      { key: 'etd', label: 'ETD', kind: 'date' },
      { key: 'eta', label: 'ETA', kind: 'date' },
    ],
  },
  {
    key: 'status-remarks', label: 'Status & Remarks',
    fields: [
      { key: 'status', label: 'Status', kind: 'text', options: ['TT/LC in Process', 'Under Production', 'In Transit', 'Arrived at Port', 'Under Custom Clearance'] },
      { key: 'userRemarks', label: 'Remarks', kind: 'text' },
    ],
  },
  {
    key: 'clearance', label: 'Clearance',
    fields: [
      { key: 'clearingAgent', label: 'Clearing agent', kind: 'text', options: ['Prime Cargo Services', 'Indus Clearing Co.', 'Sea Link Logistics'] },
      { key: 'gdNumber', label: 'GD number', kind: 'text' },
      { key: 'gdDate', label: 'GD filing date', kind: 'date' },
      { key: 'freeDays', label: 'Free days allowed', kind: 'number' },
      { key: 'gateOutDate', label: 'Gate out', kind: 'date' },
      { key: 'demurrageCost', label: 'Demurrage (PKR)', kind: 'money' },
    ],
  },
]

const COLLECTIONS: CollectionSpec[] = [
  {
    key: 'items', label: 'Items', rowNoun: 'Item',
    fields: [
      { key: 'itemName', label: 'Item name', kind: 'text', options: ['Ball bearing 6205-2RS', 'Oil seal TC 35x52x7', 'V-belt SPB 2000', 'Servo drive SGD7S'] },
      { key: 'quantity', label: 'Quantity', kind: 'number' },
      { key: 'foreignUnitPrice', label: 'Unit price', kind: 'money' },
      { key: 'hsCode', label: 'H.S. code', kind: 'text' },
    ],
  },
  {
    key: 'payments', label: 'Payments', rowNoun: 'Payment',
    fields: [
      { key: 'value', label: 'Value', kind: 'money' },
      { key: 'status', label: 'Status', kind: 'text', options: ['Paid', 'Unpaid'] },
      { key: 'reference', label: 'Reference', kind: 'text' },
    ],
  },
]

// Per-record cache so a revert mutation (session-local) persists across
// navigating away from and back to the history page, same pattern as
// importsStatusData.ts's DRAFTS cache.
const CACHE = new Map<string, ChangeHistoryEntry[]>()

export function getConsignmentChangeHistory(consignmentId: string): ChangeHistoryEntry[] {
  const cached = CACHE.get(consignmentId)
  if (cached) return cached
  const built = buildMockHistory(consignmentId, SECTIONS, COLLECTIONS)
  CACHE.set(consignmentId, built)
  return built
}

/** A one-line "who created / last touched this record" summary for the page
 *  header — deterministic from the id, independent of the edit history above
 *  (creation is never itself a change-history row, on the real backend either). */
export function getRecordProvenance(consignmentId: string): { createdBy: string; createdAt: string } {
  const rng = mulberry32(seedFrom(`${consignmentId}-created`))
  const staff = ['A. Rehman', 'S. Fatima', 'M. Tariq', 'H. Baig', 'N. Qureshi']
  const createdBy = staff[Math.floor(rng() * staff.length)]
  const base = new Date('2026-01-15T09:00:00Z').getTime()
  const createdAt = new Date(base + Math.floor(rng() * 150) * 86_400_000).toISOString()
  return { createdBy, createdAt }
}

/**
 * Session-local revert — mutates the cached list, enforcing the same
 * LIFO rule the real endpoint would (a UI-only guard; the backend is the real
 * gate once this is wired). Returns false if the revert wasn't allowed.
 */
export function revertChangeHistoryEntry(consignmentId: string, entryId: string, revertedBy: string): boolean {
  const entries = getConsignmentChangeHistory(consignmentId)
  const newestActive = entries.find((e) => !e.isReverted)
  if (!newestActive || newestActive.id !== entryId) return false

  newestActive.isReverted = true
  newestActive.revertedBy = revertedBy
  newestActive.revertedAt = new Date().toISOString()
  return true
}
