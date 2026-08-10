import type { MetricHelp } from '@/components/MetricInfo'

/**
 * What every dashboard number means, in one place.
 *
 * Kept out of the pages so the same figure is never explained two different
 * ways on two screens, and so the wording can be corrected once.
 *
 * The `basis` line is NOT written here. Coverage is a fact about the data, so
 * it comes from the API at render time (`withBasis` below) — a hardcoded
 * "measured on 95 consignments" would be a lie the moment the data changed.
 *
 * The `differs` line exists because most confusion on these screens is between
 * two figures that sound alike: "Delayed" (a count of orders) against
 * "Delay %" (a rate over a smaller measurable set), or 12-month issuance
 * against 3-month. Where two KPIs could be mistaken for each other, each one
 * names the other.
 */

export function withBasis(help: MetricHelp, basis?: string | null): MetricHelp {
  return basis ? { ...help, basis } : help
}

/** "Measured on N of M ..." — the standard way of stating a denominator. */
export function measuredOn(n: number | null | undefined, total: number, noun: string) {
  if (n === null || n === undefined) return undefined
  return `Measured on ${n.toLocaleString()} of ${total.toLocaleString()} ${noun} that carry both dates needed.`
}

/* ---------------------------------------------------------------- imports */

export const IMPORTS_HELP: Record<string, MetricHelp> = {
  totalValue: {
    what: 'What the imports in this period are worth, in rupees.',
    how: 'Each line is quantity x unit price, converted at the exchange rate booked on that consignment — never a live rate, so a printed figure never changes afterwards.',
    differs: 'Shafts Value covers only the shaft item lines; this covers everything imported.',
  },
  consignments: {
    what: 'How many consignments are still in progress in this period.',
    how: 'Counted on ETA Works — when the goods reach the factory. Consignments that have already arrived at works are excluded from this screen entirely: it is an operational view of what is still moving.',
    differs: 'This is not the total ever imported — landed consignments have dropped off.',
  },
  cancelled: {
    what: 'Consignments cancelled rather than delivered.',
    how: 'Status is "Order Cancelled". They are still shown because the order existed, but they carry no arrival date so they never enter the delay figures.',
    differs: 'Consignments counts everything on the screen, cancelled ones included.',
  },
  shaftsValue: {
    what: 'What the shaft items specifically are worth — the material the business tracks most closely.',
    how: 'Quantity x unit price at the booked rate, for lines named Forged Steel Round Bar, Forged Alloy Steel Round Bar or Forged Steel Hollow Drill Bars. Only those lines count, not the whole consignment they arrive in.',
    differs: 'Total Value is every item imported; this is the shaft lines alone, which is a much smaller number.',
  },
  efs: {
    what: 'How many consignments came in under the EFS scheme rather than as regular imports.',
    how: 'Read from the EFS column on the imports sheet. Records where the sheet says nothing are shown as "Not stated" rather than counted as regular.',
    differs: 'The percentage of stated records is shown separately — most records do not state it, so a share of everything and a share of the stated ones are very different numbers.',
  },
  inProcess: {
    what: 'Consignments still moving — not yet arrived at works and not cancelled.',
    how: 'Every consignment whose status is not "Arrived at Works" or "Order Cancelled".',
    differs: 'Demands Processed is the opposite: the ones that have finished.',
  },
  demandsReceived: {
    what: 'Every import demand in this period, finished or not.',
    how: 'A count of consignments. Processed plus In Process always adds back to this.',
    differs: 'In Process is the unfinished subset of this figure.',
  },
  deliveryDelay: {
    what: 'How often imports reach the factory meaningfully later than they were needed.',
    how: 'ETA Works minus the required date. More than SEVEN days late counts as delayed; anything from arriving early up to a week late is on time, because a day or two of slip is normal port and sailing scheduling rather than a problem to chase. Only consignments carrying both dates can be measured.',
    differs: 'Average Days Late describes only the delayed ones — how bad they are, not how often.',
  },
  avgDaysLate: {
    what: 'When an import is late, how late it typically is.',
    how: 'The average of (ETA Works minus required date) across the delayed consignments only. Early arrivals are excluded so they cannot cancel out the late ones.',
    differs: 'Delivery Delay % is how OFTEN imports are late; this is how MUCH.',
  },
  suppliers: {
    what: 'How many distinct suppliers these imports came from.',
    how: 'Distinct suppliers on the consignments in this period.',
  },
}

/* -------------------------------------------------------------- purchases */

export const PURCHASES_HELP: Record<string, MetricHelp> = {
  totalValue: {
    what: 'What local procurement spent in this period.',
    how: 'The sum of the amount on every purchase line whose purchase date falls in the window.',
    differs: 'Top Supplier and the supplier chart exclude Import (IOL), which is the in-house import channel rather than a vendor — so those will not add up to this total.',
  },
  orders: {
    what: 'How many purchase orders the lines in this period belong to.',
    how: 'Distinct PO numbers. One PO usually covers several lines.',
    differs: 'The delayed and completed figures count LINES, not orders.',
  },
  avgOrderValue: {
    what: 'What a typical purchase order is worth.',
    how: 'Total value divided by the number of distinct POs.',
  },
  delayed: {
    what: 'How many purchase lines were bought after the date they were required.',
    how: 'A line is Delayed when its purchase date is later than its required date.',
    differs: 'Average Delay tells you how many days late those lines were; this is just how many.',
  },
  onTimeRate: {
    what: 'The share of purchased lines that were bought by the date they were needed.',
    how: 'Completed lines divided by all lines that have actually been purchased.',
    differs: 'This counts lines; Orders counts POs.',
  },
  avgDelay: {
    what: 'When purchasing runs late, how late it typically is.',
    how: 'The average of (purchase date minus required date) across the LATE lines only, so lines bought early do not mask the late ones.',
    differs: 'Delayed is the count of late lines; this is their average lateness in days.',
  },
  topSupplier: {
    what: 'The vendor the business spent most with in this period.',
    how: 'Highest total amount, excluding Import (IOL) — that is the in-house import channel, not a supplier, and it is the largest line in the table.',
    differs: 'Total Value includes Import (IOL); the supplier figures do not.',
  },
}

/* --------------------------------------------------------------- overview */

export const OVERVIEW_HELP: Record<string, MetricHelp> = {
  importValue: {
    what: 'What the imports landing in this period are worth.',
    how: 'The stored PKR total of consignments whose ETD falls in the window, converted at the rate booked on each one.',
    differs: 'Procurement Value is what was bought locally; this is what was imported.',
  },
  importsInProcess: {
    what: 'Consignments still moving through the pipeline right now.',
    how: 'Every consignment not yet at "Arrived at Works" and not cancelled. A snapshot, so it ignores the reporting period.',
    differs: 'Import Value is a period figure; this is where things stand today.',
  },
  shafts: {
    what: 'How the shaft material — the item the business watches most closely — is moving.',
    how: 'Consignments carrying a shaft item, split by whether they have reached works yet. Matched on the item name, since shafts are not a category in the item master.',
    differs: 'Counted in consignments, not item lines: one consignment carrying six shaft rows is one.',
  },
  procurementValue: {
    what: 'What local procurement spent in this period.',
    how: 'Total amount on purchase lines bought in the window, counted as ORDERS (distinct POs) rather than lines.',
    differs: 'Import Value covers goods bought abroad; this is domestic purchasing only.',
  },
  procurementDelay: {
    what: 'How often local purchasing lands after the date it was needed.',
    how: 'Orders whose purchase date is later than the required date, over the orders that have a required date at all.',
    differs: 'Cycle Time is how LONG buying takes; this is how often it is late.',
  },
  cycleTime: {
    what: 'How long it takes from a store raising demand to the purchase being made.',
    how: 'Average days from the store demand date to the purchase date. Orders where the demand date falls after the purchase are excluded as data errors rather than counted as negative time.',
    differs: 'Delay Rate measures lateness against a required date; this measures duration regardless of whether it was late.',
  },
  categories: {
    what: 'How many distinct item categories the business bought from this period.',
    how: 'Distinct categories on the purchased items, taken from the item master.',
  },
  truckingCost: {
    what: 'What has been spent moving goods by road.',
    how: 'Actual freight summed across every trucking job to date — a running total, not a period figure.',
    differs: 'Jobs with no movement type are shown separately as Unclassified; there is no "Local" type in the data and none can be inferred.',
  },
  shipmentsHandled: {
    what: 'How much the business has shipped and imported in total.',
    how: 'Standard logistics orders plus import consignments, all-time. Rework service jobs are excluded — they are not shipments handled for a customer.',
    differs: 'A running total, so it does not move with the reporting period.',
  },
  stockValue: {
    what: 'What is sitting in the stores right now.',
    how: 'Stock value summed across every store, counted as distinct ITEMS rather than item-at-a-branch records.',
  },
  stockDays: {
    what: 'How long the stock on hand would last at the rate it is being used.',
    how: 'Stock value divided by the average value issued per day over the last 12 months. In rupees, because a store holds many units that cannot be added together.',
  },
  deadStock: {
    what: 'Stock that has not moved at all — the money standing still.',
    how: 'Items with value on hand and no issuance within the threshold. An item still moving at one store is not dead because it sat still at another.',
    differs: 'Stock Value is everything held; this is the part of it nobody has drawn on.',
  },
  stores: {
    what: 'How many stores are holding stock.',
    how: 'Distinct branches with at least one stock record.',
  },
}

/* -------------------------------------------------------------- inventory */

export const INVENTORY_HELP: Record<string, MetricHelp> = {
  stockValue: {
    what: 'What the stock on hand is worth across every store.',
    how: 'The sum of the stock value on every stock line. A snapshot of today, not a period figure.',
    differs: 'Available Value excludes stock that is held or reserved.',
  },
  availableValue: {
    what: 'What of the stock is actually free to use.',
    how: 'The sum of the available value per line — stock value less anything held.',
    differs: 'Total Stock Value counts everything, including held stock.',
  },
  stockDays: {
    what: 'How long the stock on hand would last at the rate it is being used.',
    how: 'Stock value divided by the average value issued per day over the last 12 months. Measured in rupees because a store holds many different units — adding kilograms to pieces would mean nothing.',
    differs: 'This is the whole business; the per-branch chart breaks the same figure down by store.',
  },
  issued12m: {
    what: 'What left the stores over the last 12 months.',
    how: 'The total value issued in the 12 months up to the most recent issuance in the data.',
    differs: 'The 3-month figure is the recent slice of this one — it is not a separate total to be added.',
  },
  issued3m: {
    what: 'What left the stores over the last 3 months — the recent run rate.',
    how: 'The total value issued in the 92 days up to the most recent issuance in the data.',
    differs: 'This is INCLUDED in the 12-month figure, not additional to it.',
  },
  deadStock: {
    what: 'Stock that has not moved at all in a year — the money sitting still.',
    how: 'Stock lines with value on hand and no issuance at all in the last 12 months.',
    differs: 'Slow moving items DID move in the last year, just not in the last 3 months.',
  },
  fastMoving: {
    what: 'Items that have been issued recently and are genuinely turning over.',
    how: 'Stock lines with at least one issuance in the last 3 months.',
    differs: 'Slow moving items moved within the year but not the last 3 months; dead ones have not moved at all.',
  },
  outOfStock: {
    what: 'Lines with nothing available to issue.',
    how: 'Available quantity is zero or less.',
    differs: 'Below Reorder still has stock, just less than its reorder level.',
  },
  belowReorder: {
    what: 'Lines that still have stock but have dropped under their reorder level.',
    how: 'Available quantity is below the reorder level derived from requisition demand and lead time.',
    differs: 'Out of Stock has already run out; these have not yet.',
  },
}
