import {
  buildMockHistory, mulberry32, seedFrom,
  type ChangeHistoryEntry, type SectionSpec, type CollectionSpec,
} from './changeHistory'

/** Mock change history for Trucking Status — field vocabulary mirrors the
 *  wizard's own steps (schema.ts WIZARD_STEPS). See importsChangeHistory.ts
 *  for the shared engine and the eventual real-backend field mapping. */

const SECTIONS: SectionSpec[] = [
  {
    key: 'movement', label: 'Movement & Item',
    fields: [
      { key: 'movementType', label: 'Movement type', kind: 'text', options: ['Intrafactory', 'Outbound', 'Inbound'] },
      { key: 'executionDate', label: 'Execution date', kind: 'date' },
      { key: 'transporterName', label: 'Transporter', kind: 'text', options: ['Bilal Goods Transport', 'Al Madina Movers', 'Fast Freight Co.'] },
      { key: 'pickup', label: 'Pickup', kind: 'text' },
      { key: 'destination', label: 'Destination', kind: 'text' },
      { key: 'referenceNo', label: 'Reference / IDM', kind: 'text' },
    ],
  },
  {
    key: 'freight', label: 'Freight & Payment',
    fields: [
      { key: 'quotedFreight', label: 'Quoted freight', kind: 'money' },
      { key: 'actualFreight', label: 'Actual freight', kind: 'money' },
      { key: 'paymentStatus', label: 'Payment status', kind: 'text', options: ['Customer to pay', 'QG to pay'] },
      { key: 'detention', label: 'Detention', kind: 'money' },
    ],
  },
  {
    key: 'tracking', label: 'Tracking',
    fields: [
      { key: 'dispatchNoteDate', label: 'Dispatch note date', kind: 'date' },
      { key: 'etaWorks', label: 'ETA to works', kind: 'date' },
      { key: 'remarks', label: 'Remarks', kind: 'text' },
    ],
  },
]

const COLLECTIONS: CollectionSpec[] = [
  {
    key: 'vehicles', label: 'Vehicles', rowNoun: 'Vehicle',
    fields: [
      { key: 'vehicleNumber', label: 'Vehicle number', kind: 'text' },
      { key: 'vehicleType', label: 'Vehicle type', kind: 'text', options: ['10-wheeler', '20ft flatbed', '40ft trailer'] },
      { key: 'grossWeight', label: 'Gross weight (kg)', kind: 'number' },
      { key: 'trackingStatus', label: 'Tracking status', kind: 'text', options: ['Going to load', 'Loading', 'On road', 'Delivered'] },
    ],
  },
]

const CACHE = new Map<string, ChangeHistoryEntry[]>()

export function getJobChangeHistory(jobId: string): ChangeHistoryEntry[] {
  const cached = CACHE.get(jobId)
  if (cached) return cached
  const built = buildMockHistory(jobId, SECTIONS, COLLECTIONS)
  CACHE.set(jobId, built)
  return built
}

export function getRecordProvenance(jobId: string): { createdBy: string; createdAt: string } {
  const rng = mulberry32(seedFrom(`${jobId}-created`))
  const staff = ['A. Rehman', 'S. Fatima', 'M. Tariq', 'H. Baig', 'N. Qureshi']
  const createdBy = staff[Math.floor(rng() * staff.length)]
  const base = new Date('2026-01-15T09:00:00Z').getTime()
  const createdAt = new Date(base + Math.floor(rng() * 150) * 86_400_000).toISOString()
  return { createdBy, createdAt }
}

export function revertChangeHistoryEntry(jobId: string, entryId: string, revertedBy: string): boolean {
  const entries = getJobChangeHistory(jobId)
  const newestActive = entries.find((e) => !e.isReverted)
  if (!newestActive || newestActive.id !== entryId) return false

  newestActive.isReverted = true
  newestActive.revertedBy = revertedBy
  newestActive.revertedAt = new Date().toISOString()
  return true
}
