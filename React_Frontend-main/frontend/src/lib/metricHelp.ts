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
    how: 'The PKR total booked against each consignment. Where none was booked, the value is rebuilt from the item lines (quantity x unit price at that consignment’s own rate) rather than counted as zero. Never a live rate, so a printed figure does not change afterwards.',
    differs: 'Covers EVERY status, arrived consignments included — so it is the same figure, on the same population, as Import Value on the Overview. In Process, Arrived and Cancelled split it three ways. Shafts Value covers only the shaft item lines.',
  },
  arrived: {
    what: 'The money that has landed at works, and how many consignments it is.',
    how: 'Consignments in the window at "Arrived at Works".',
    differs: 'Cancelled is the other terminal state — work abandoned rather than completed — so the two are never folded together.',
  },
  cancelled: {
    what: 'Consignments cancelled rather than delivered, and what they were worth.',
    how: 'Status is "Order Cancelled". They are still shown because the order existed, but they carry no arrival date so they never enter the delay figures.',
    differs: 'Arrived is work that completed; this is work that stopped. Both are terminal, which is why neither is in In Process.',
  },
  shaftsValue: {
    what: 'What the shaft items specifically are worth — the material the business tracks most closely.',
    how: 'Quantity x unit price at the booked rate, for lines named Forged Steel Round Bar, Forged Alloy Steel Round Bar or Forged Steel Hollow Drill Bars. This is the one figure here read from the ITEM LINES rather than the consignment total — a consignment-level total cannot say what the shafts inside it were worth.',
    differs: 'Total Value is every item imported; this is the shaft lines alone, which is a much smaller number.',
  },
  efs: {
    what: 'How many consignments came in under the EFS scheme rather than as regular imports.',
    how: 'Read from the EFS column on the imports sheet. Records where the sheet says nothing are shown as "Not stated" rather than counted as regular.',
    differs: 'The percentage of stated records is shown separately — most records do not state it, so a share of everything and a share of the stated ones are very different numbers.',
  },
  inProcess: {
    what: 'The money still moving through the pipeline, and how many consignments it is.',
    how: 'Consignments in the window whose status is not "Arrived at Works" or "Order Cancelled", valued exactly as Total Import Value is.',
    differs: 'In Process + Arrived + Cancelled = Total Import Value. This screen used to hide arrived consignments entirely, which is why it disagreed with the Overview by Rs 52.7m.',
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
    how: 'The sum of the amount on every purchase line falling in the window. Which date the window measures is yours to choose: PO date (when the order was placed) or purchase date (when it was bought).',
    differs: 'Top Supplier and the supplier chart exclude Import (IOL), which is the in-house import channel rather than a vendor — so those will not add up to this total.',
  },
  orders: {
    what: 'How many purchase orders the lines in this period belong to.',
    how: 'Distinct PO numbers. One PO usually covers several item lines; nothing on this screen counts lines.',
    differs: 'The delayed and completed figures count LINES, not orders.',
  },
  avgOrderValue: {
    what: 'What a typical purchase order is worth.',
    how: 'Total value divided by the number of distinct POs.',
  },
  delayed: {
    what: 'How many purchase lines were bought after the date they were required.',
    how: 'An ORDER is Delayed when any of its lines was bought after the date it was required. Worst case wins: an order is not on time while any part of it is late.',
    differs: 'Average Delay tells you how many days late those lines were; this is just how many.',
  },
  onTimeRate: {
    what: 'The share of purchased lines that were bought by the date they were needed.',
    how: 'On Time orders divided by all orders that have actually been purchased. Counted over ORDERS (distinct POs), not item lines.',
    differs: 'This counts lines; Orders counts POs.',
  },
  avgDelay: {
    what: 'When purchasing runs late, how late it typically is.',
    how: 'The average of (purchase date minus required date) across the LATE orders only, so orders bought early do not mask them. Each order’s own figure is the average of ITS late lines, so one very late line no longer speaks for a whole order. Open the list icon for the per-line breakdown — the PO, the item and how late each one was.',
    differs: 'Delayed Orders is how MANY ran late; this is how late they ran.',
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
    how: 'The PKR total booked against each consignment, falling back to its item lines where none was booked — the same rule the Imports dashboard uses. Which date the window measures is yours to choose: ETA at works, or the date the goods were required.',
    differs: 'Procurement Value is what was bought locally; this is what was imported. This section still includes consignments that have arrived at works, which the Imports dashboard excludes — so its count is higher.',
  },
  importsInProcess: {
    what: 'The money still moving through the pipeline, and how many consignments it is.',
    how: 'Consignments in the window that have not reached "Arrived at Works" and were not cancelled, valued at their booked PKR total (or their item lines at the booked rate where no total was entered).',
    differs: 'Import Value is every consignment in the window; this is the part still in flight. Arrived and Cancelled are the other two, and the three add up to it.',
  },
  importsArrived: {
    what: 'The money that has landed at works, and how many consignments it is.',
    how: 'Consignments in the window at "Arrived at Works", valued the same way as every other figure on this screen.',
    differs: 'Cancelled is the other terminal state — work abandoned rather than completed — so the two are never folded together.',
  },
  importsCancelled: {
    what: 'Consignments that were cancelled, and what they were worth.',
    how: 'Consignments in the window at "Order Cancelled".',
    differs: 'Arrived is work that completed; this is work that stopped. Both are terminal, which is why neither is in the In Process figure.',
  },
  importsDelayed: {
    what: 'Consignments that landed materially later than they were needed, and what they were worth.',
    how: 'ETA at works minus the required date, counted as delayed only beyond a 7-day grace — a slip of a day or two is normal port scheduling, not a problem to chase. Only consignments carrying both dates can be measured.',
    differs: 'In Process says what has not arrived yet; this says what did arrive, late. The two overlap only where a consignment is both still moving and already past its date.',
  },
  shafts: {
    what: 'How the shaft material — the item the business watches most closely — is moving.',
    how: 'Consignments carrying a shaft item, split by whether they have reached works yet. Matched on the item name, since shafts are not a category in the item master.',
    differs: 'Counted in consignments, not item lines: one consignment carrying six shaft rows is one.',
  },
  procurementValue: {
    what: 'What local procurement spent in this period.',
    how: 'Total amount on purchase lines in the window, counted as ORDERS (distinct POs) rather than lines. The window measures the PO date by default; switch it to the purchase date with the control above.',
    differs: 'Import Value covers goods bought abroad; this is domestic purchasing only.',
  },
  procurementDelay: {
    what: 'How often local purchasing lands after the date it was needed.',
    how: 'Orders bought after the date they were required, over the orders that have a required date at all. Both are counted within whichever date the section is filtered on.',
    differs: 'Cycle Time is how LONG buying takes; this is how often it is late.',
  },
  cycleTime: {
    what: 'How long it takes from a store raising demand to the purchase being made.',
    how: 'Average days from the store demand date to the purchase date. Orders where the demand date falls after the purchase are excluded as data errors rather than counted as negative time.',
    differs: 'Delay Rate measures lateness against a required date; this measures duration regardless of whether it was late.',
  },
  truckingCost: {
    what: 'What has been spent moving goods by road.',
    how: 'Actual freight summed across the trucking jobs in the window. ETD means the job’s execution date; ETA means its arrival at works. Jobs with no movement type are shown separately as Unclassified rather than folded into a category they may not belong to.',
    differs: 'There is no "Local" movement type in the data and none can be inferred, so those jobs are Unclassified rather than guessed at.',
  },
  shipmentsHandled: {
    what: 'How much the business has shipped and imported in total.',
    how: 'Standard logistics orders plus import consignments falling in the window. Rework service jobs are excluded — they are not shipments handled for a customer. Most logistics orders carry no ETD or arrival date, so the export half covers only the dated ones; the note above the section says how many.',
    differs: 'Unlike Trucking Cost this counts shipments, not money.',
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
  exportOrders: {
    what: 'How many logistics orders in this period are export business.',
    how: 'Orders with order type "Export" whose chosen date falls in the window.',
    differs: 'Only exports carry dates, so in practice this is nearly the whole windowed count. The Undated tile holds the rest.',
  },
  localOrders: {
    what: 'How many logistics orders are local business, across the whole book.',
    how: 'Every order with order type "Local". NOT filtered by the period above, deliberately: not one local order records a sailing, arrival, gate-out or port-in date, so a windowed count would read zero in every period there has ever been \u2014 which says "no local business" rather than "local orders are undated".',
    differs: 'Export Orders beside it IS windowed. The two sit on different bases, which is why this one says "all time" on its face instead of leaving you to assume they match.',
  },
  packedTonnage: {
    what: 'How much weight was packed for shipping in this period.',
    how: 'Gross weight summed across the packages packed in the window, in tonnes.',
    differs: 'This is what PACKING handled; freight per kg is what ROAD movement cost. A package can be packed in one month and trucked in the next.',
  },
  freightPerKg: {
    what: 'What it costs to move a kilogram by road.',
    how: 'Actual freight divided by the gross weight on the vehicles, over the jobs that record both.',
    differs: 'A RATE, not another cost total — Trucking Cost already reports the money. This says whether that money is buying more or less movement than it used to.',
  },
  transitTime: {
    what: 'How long a shipment takes from sailing to arrival.',
    how: 'Average days from ETD to actual arrival. Orders arriving before they sailed are excluded as data errors rather than counted as negative transit.',
    differs: 'Measured only on the orders recording BOTH dates, which is a minority of the book — the basis line says how many.',
  },
  issued: {
    what: 'What left the stores in this period, and across how many distinct items.',
    how: 'Issuance value summed over the window, with items counted by ITEM CODE folded across the branches that issued them — the same unit the Inventory dashboard counts, so the figure is identical on both screens.',
    differs: 'Stock Value is what is on the shelf right now; this is what went out over the period. Days of Stock is the two divided into each other.',
  },
}

/* -------------------------------------------------------------- inventory */

export const INVENTORY_HELP: Record<string, MetricHelp> = {
  issued: {
    what: 'What left the stores in the chosen period, and across how many distinct items.',
    how: 'Issuance value summed over the window, with items counted by ITEM CODE folded across the branches that issued them — the same unit the Overview’s Stores section uses, so the figure is identical on both screens.',
    differs: 'This replaced the fixed 12-month and 3-month tiles, which asked one question at two lengths nobody chose. Those windows still drive the movement split and the days-of-stock runway; they are just no longer tiles. Stock Value is what is on the shelf now, this is what went out.',
  },
  stockValue: {
    what: 'What the stock on hand is worth across every store.',
    how: 'Stock value summed across every store, counted as distinct ITEMS rather than item-at-a-branch records. A snapshot of today, not a period figure.',
    differs: 'Available Value excludes stock that is held or reserved.',
  },
  availableValue: {
    what: 'What of the stock is actually free to use.',
    how: 'Available value summed per item across the stores holding it — stock value less anything held.',
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
    how: 'ITEMS with value on hand and no issuance at all in the last 12 months, judged on the item’s total issuance across every store — an item still moving at one factory is not dead because it sat still at another.',
    differs: 'Slow moving items DID move in the last year, just not in the last 3 months.',
  },
  fastMoving: {
    what: 'Items that have been issued recently and are genuinely turning over.',
    how: 'Items with at least one issuance in the last 3 months, anywhere they are stocked.',
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


/* -------------------------------------------------------------- logistics */

export const LOGISTICS_HELP: Record<string, MetricHelp> = {
  shipments: {
    what: 'How many logistics orders fall in this period.',
    how: 'Orders whose chosen date — sailing (ETD) or arrival (ETA) — lands in the window. Local and export orders both count; the Local/Export filter narrows to one.',
    differs: 'Packages on the Packing tab counts PACKAGES, several of which can sit under one order, so the two numbers are not meant to match.',
  },
  delivered: {
    what: 'Shipments that have reached the customer.',
    how: 'Orders at status "Delivered" within the period.',
    differs: 'Transport’s Delivered counts trucking JOBS, which is a different unit and a different table.',
  },
  totalCost: {
    what: 'What these shipments cost to move, all charges together.',
    how: 'Sea/air freight, port and clearance charges, packing, fumigation, lashing, DHL, insurance and inland trucking, summed across the orders in the period.',
    differs: 'Transport’s freight total covers ROAD movements only, from the trucking table. The two overlap only in the inland leg.',
  },
  costPerKg: {
    what: 'What it costs to move a kilogram, on average.',
    how: 'Total logistics cost divided by gross weight, averaged over the orders that carry both. Orders missing either are left out rather than counted as zero.',
    differs: 'An average of per-order rates, not total cost divided by total weight — so a single small, expensive shipment does not disappear into a large one.',
  },
  countries: {
    what: 'How many destination countries these shipments went to.',
    how: 'Distinct origin/destination countries on the orders in the period.',
  },
  orderTypes: {
    what: 'The orders in this period, split into export, local and not stated.',
    how: 'Counted in the window on the date you chose above.',
    differs: 'Local reads zero in every period because local orders carry no date at all — not because there is no local business. The basis line says how many exist outside every window.',
  },
  packages: {
    what: 'How many packages were packed in this period.',
    how: 'Packages whose chosen date — packed, or ready-for-dispatch — falls in the window. Counted per PACKAGE; the list shows how many orders they belong to.',
    differs: 'Shipments counts ORDERS. One order routinely carries several packages.',
  },
  packed: {
    what: 'Packages that have finished packing.',
    how: 'Packages at status "Packed" within the period.',
  },
  packingCost: {
    what: 'What packing these shipments cost.',
    how: 'Actual packing cost summed across the packages in the period.',
    differs: 'Savings against the budgeted cost cannot be computed while no actual cost is recorded — it is reported as unavailable rather than as a confident zero.',
  },
  jobs: {
    what: 'How many trucking jobs ran in this period.',
    how: 'Jobs whose execution date (or arrival at works, if you switch the filter) falls in the window. Inbound, outbound and intra-factory moves all count.',
    differs: 'Shipments counts sea/air ORDERS. A single export order can generate several road jobs.',
  },
  jobsDelivered: {
    what: 'Trucking jobs where every vehicle has been delivered.',
    how: 'A job is Delivered only when all of its trucks are; while any is still moving it is In Progress.',
    differs: 'Shipments’ Delivered is about the sea/air shipment reaching the customer, not about the trucks.',
  },
  freight: {
    what: 'What road movement cost in this period.',
    how: 'Actual freight summed across the trucking jobs in the window. Jobs with no freight recorded are counted as jobs but add nothing — the data note says how many.',
    differs: 'Intra-factory moves are included here and are a large share of the job count; filter by movement type to separate them.',
  },
  savings: {
    what: 'The gap between quoted and actual freight.',
    how: 'Quoted minus actual, summed over the jobs that carry both figures.',
    differs: 'Intra-factory jobs record only one freight figure, so they contribute nothing here by construction, not because they saved nothing.',
  },
}
