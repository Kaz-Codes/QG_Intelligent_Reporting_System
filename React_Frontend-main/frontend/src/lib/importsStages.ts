/**
 * The six-stage pipeline the Imports list rolls the eleven statuses into.
 *
 * Pure logic, no data — extracted from lib/importsStatusData.ts so the list
 * screen (now on the live API) doesn't have to import the mock module just to
 * colour a status pill. Mirrors STAGE_GROUPS in app/imports/helpers.py; the
 * backend filters by the same stage names, so the two must stay in step.
 */

export const STAGE_GROUPS = [
  { key: 'Pre-shipment', statuses: ['TT/LC in Process'] },
  { key: 'Production', statuses: ['Under Production', 'Ready Awaiting Sailing'] },
  { key: 'In transit', statuses: ['In Transit'] },
  { key: 'Clearance', statuses: ['Arrived at Port', 'Under Custom Clearance', 'Under Examination', 'Under Assessment', 'Under De-Stuffing'] },
  { key: 'Inbound', statuses: ['Arrived at QFL', 'On Road'] },
  // Both terminal states, so the strip can reach a cancelled order. Only
  // 'Arrived at Works' locks a record.
  { key: 'Closed', statuses: ['Arrived at Works', 'Order Cancelled'] },
] as const

export type StageKey = (typeof STAGE_GROUPS)[number]['key'] | 'all'

/**
 * Which stage a status belongs to. Falls back to Pre-shipment for a value the
 * pipeline doesn't know — imported rows carry sheet-only statuses like "Order
 * Cancelled". Callers that can distinguish should check `canonical` first
 * (see StatusPill) rather than letting the fallback imply a real position.
 */
export const stageOf = (status: string): StageKey =>
  STAGE_GROUPS.find((g) => (g.statuses as readonly string[]).includes(status))?.key ?? 'Pre-shipment'
