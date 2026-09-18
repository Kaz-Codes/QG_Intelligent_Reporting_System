import { z } from 'zod'

/**
 * Imports Status — consignment data contract.
 *
 * Two rules shape this file, and both come from how the business actually works:
 *
 * 1. HEADER vs LINES. A consignment carries many items. Supplier, currency and
 *    payment instrument belong to the shipment; requisition details, quantity,
 *    pricing and landed cost belong to each item. Flattening these was the
 *    single biggest structural mistake to avoid.
 *
 * 2. DRAFT vs SUBMIT. Almost every field can be filled later — an operator logs
 *    a consignment before prices, ETAs or GD numbers exist. So the base schema
 *    is permissive and `submitSchema` adds the real requirements. The wizard
 *    validates against the draft schema; only Submit uses the strict one.
 *
 * History is recorded as events, never as overwritten fields or generated text.
 * That is what makes slippage and stage-ageing reportable later.
 */

/* ------------------------------------------------------------------ */
/* Enumerations                                                        */
/* ------------------------------------------------------------------ */

/** Ordered. The list view groups these into six stages and the order drives
 *  stage-ageing, so do not reorder without changing both. */
export const CONSIGNMENT_STATUSES = [
  'TT/LC in Process',
  'Under Production',
  'Ready Awaiting Sailing',
  'In Transit',
  'Arrived at Port',
  'Under Custom Clearance',
  'Under Examination',
  'Under Assessment',
  /** Unstuffing the container, after assessment and before the goods move on. */
  'Under De-Stuffing',
  'Arrived at QFL',
  'On Road',
  'Arrived at Works',
  /** Terminal, but NOT an arrival — the import never completes. Last because
   *  it is an exit, not a later stage. Unlike 'Arrived at Works' it does not
   *  lock the record. */
  'Order Cancelled',
] as const
export type ConsignmentStatus = (typeof CONSIGNMENT_STATUSES)[number]

/** "Arrived at Works" closes a consignment (once submitted) — hidden from the
 *  list by default. */
export const CLOSED_STATUS: ConsignmentStatus = 'Arrived at Works'

/** The other terminal status. It has no lock of its own (nothing to reopen),
 *  but it's treated the same as a truly-closed "Arrived at Works" record for
 *  the Closed stage/column — see helpers.py's is_truly_closed on the backend. */
export const CANCELLED_STATUS: ConsignmentStatus = 'Order Cancelled'

export const REQUISITION_TYPES = ['store', 'engineering', 'others'] as const
export type RequisitionType = (typeof REQUISITION_TYPES)[number]

export const CONSIGNMENT_TYPES = ['efs', 'regular'] as const
/** Feeds Trucking Status's Import-FOB request derivation directly —
 *  see deriveFromImportsFob() in lib/truckingStatusData.ts, which checks
 *  incoterm === 'FOB'. Kept short: only the terms that actually change who
 *  arranges freight, not the full ICC list. */
export const INCOTERMS = ['FOB', 'CIF', 'CFR', 'EXW', 'DAP'] as const
export const PAYMENT_INSTRUMENTS = ['LC', 'Adv', 'DP', 'CAD'] as const
export type PaymentInstrument = (typeof PAYMENT_INSTRUMENTS)[number]

// Matches app.enums.ModeOfShipment exactly (backend Optional[ModeOfShipment] —
// values must be one of these four verbatim or a save 422s). Widened from a
// generic 'Sea'/'Air' pair, which the backend has no equivalent for.
export const SHIPMENT_MODES = ['Sea freight FCL', 'Sea freight LCL', 'Air freight', 'Land/courier'] as const
export const PAYMENT_STATUSES = ['Paid', 'Unpaid'] as const

// Matches app.enums.RateSource exactly — where the booked exchange rate came
// from, needed to reconcile against a bank advice later. Was free text; a
// fixed vocabulary here so a save can't 422 on an untyped value.
export const RATE_SOURCES = ['Bank LC opening rate', 'Bank TT rate', 'SBP inter bank', 'Contract/agreed rate'] as const

// Matches app.enums.UnitOfMeasurement exactly. 'Ton (MT)' -> 'Ton', the two
// 'Sq./Cu. Metre' casings -> 'Sq./Cu. metre', and 'Millilitre' dropped — the
// backend enum has no equivalent for it.
export const UNITS_OF_MEASURE = [
  'Pcs', 'Set', 'Pair', 'Roll', 'Box', 'Carton', 'Drum', 'Pallet',
  'Kg', 'Gram', 'Ton', 'Lb',
  'Metre', 'Centimetre', 'Foot', 'Inch',
  'Sq. metre', 'Cu. metre', 'Litre',
] as const

/** Which extra fields each requisition type reveals. Defined once — the form,
 *  the validation and any future type all read from here. */
export const REQUISITION_FIELDS: Record<RequisitionType, Array<'referenceNo' | 'jobNo' | 'moNo' | 'othersDescription'>> = {
  store: ['referenceNo'],
  engineering: ['referenceNo', 'jobNo', 'moNo'],
  others: ['othersDescription'],
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

/** Number inputs hand back '' when cleared. Treat that as absent, not as 0 —
 *  an unpriced item and a zero-priced item are different things. */
const optionalNumber = z.preprocess(
  (v) => (v === '' || v === null || Number.isNaN(v) ? undefined : v),
  z.coerce.number().nonnegative().optional(),
)

const optionalDate = z.string().optional().or(z.literal(''))
const optionalText = z.string().optional().or(z.literal(''))

/* ------------------------------------------------------------------ */
/* Step 1 — Consignment                                                */
/* ------------------------------------------------------------------ */

/**
 * Requisition type, reference, job and MO numbers live HERE, on the item —
 * not on the consignment. One shipment can legitimately carry Store items and
 * Engineering items together, so a single header-level type would be wrong.
 */
export const consignmentItemSchema = z.object({
  id: z.string(),
  /** The real backend row id, once this line has been saved — undefined for a
   *  line the user just added in the wizard and never yet round-tripped.
   *  draftToPayload (lib/api/importsMap.ts) sends this as the line's `id` so
   *  the update route's diff engine treats it as "still exists" rather than
   *  as a new insert; omitted entirely for a genuinely new line. */
  backendId: z.number().optional(),

  // requisition (per item)
  requisitionType: z.enum(REQUISITION_TYPES).optional(),
  referenceNo: optionalText,
  jobNo: optionalText,
  moNo: optionalText,
  othersDescription: optionalText,

  /** WHICH ORDER LINE THIS BATCH LINE ALLOCATES AGAINST — the id the server
   *  needs to know that this line is a shipment of something the order already
   *  bought, rather than a new item on the order.
   *
   *  Read-only in the wizard and never typed. It comes back on every fetch and
   *  goes out on every save; the one thing that must not happen is it being
   *  dropped in between, which is what made adding an item to batch 2 raise the
   *  order's total by stealth (design §3.7b finding 3). */
  orderItemId: optionalNumber,
  /** What the ORDER bought for this line, across every batch. Shown on the
   *  allocation table beside what this batch carries; only sent when the
   *  operator changes it, since on an unsplit order the server keeps it in
   *  step with `quantity` by itself. */
  orderedQuantity: optionalNumber,

  // item
  itemId: optionalText,              // FK to item master once one exists
  itemName: z.string().default(''),
  /** A user-facing nickname / short label for the item (imports only). Purely
   *  a display aid shown alongside the real item name in the list; never
   *  required and NOT counted as a missing field when left blank. */
  placeholderName: optionalText,
  itemCode: z.string().default(''),
  specification: optionalText,
  quantity: optionalNumber,
  uom: optionalText,
  batchNo: optionalText,
  /** An item may classify differently by variant or origin, so this is a list
   *  on the master; the line records the one actually used. */
  hsCode: optionalText,

  // step 2 — pricing is per item
  /** HOW THIS LINE IS PRICED. `quantity` (the default) multiplies by
   *  `foreignUnitPrice`; `weight` multiplies by `unitWeight × weightUnitPrice`.
   *  Whichever is chosen, the other price is NOT READ — which is why the form
   *  hides it rather than leaving a number nothing multiplies. */
  priceBasis: z.enum(['quantity', 'weight']).default('quantity'),
  foreignUnitPrice: optionalNumber,
  /** Per kilogram, used only under the weight basis. */
  weightUnitPrice: optionalNumber,
  /** Kilograms PER UNIT — not the line's total, which is `netWeight`.
   *  Multiplying quantity by a total would count the quantity twice. */
  unitWeight: optionalNumber,

  // Weight & dimensions — optional at draft, but the imports team is expected
  // to fill these before an FOB consignment is handed to trucking, since the
  // truck load-out and freight rate depend on them. Surfaced as "expected"
  // (not hard-required) so an early draft isn't blocked.
  netWeight: optionalNumber,   // kg per item line (total for its quantity)
  grossWeight: optionalNumber, // kg incl. packaging
  length: optionalNumber,      // cm
  width: optionalNumber,       // cm
  height: optionalNumber,      // cm
})
export type ConsignmentItem = z.infer<typeof consignmentItemSchema>

export const consignmentStepSchema = z.object({
  /** The database id, as a string. A route target, not a label — see
   *  `consignmentNumber` below. Never edited and never posted back. */
  systemId: z.string().default(''),
  /** THE CONSIGNMENT NUMBER the wizard's step chips display: `177`, or
   *  `177-2` on a later batch. Server-owned and read-only here; it is absent
   *  from `draftToPayload` on purpose, because nothing in the browser gets to
   *  decide what a consignment is called. */
  consignmentNumber: z.string().default(''),
  branch: optionalText,
  supplier: optionalText,
  origin: optionalText,
  currency: optionalText,
  consignmentType: z.enum(CONSIGNMENT_TYPES).optional().or(z.literal('')),
  /** FOB feeds Trucking Status's cross-module request derivation — see
   *  deriveFromImportsFob() in lib/truckingStatusData.ts. */
  incoterm: z.enum(INCOTERMS).optional().or(z.literal('')),
  poDate: optionalDate,
  /** Date the requisition/indent was raised — the moment the need was first
   *  recorded, before a supplier or PO exists. Distinct from poDate: the gap
   *  between the two is procurement lead time, not shipping time. */
  requisitionDate: optionalDate,
  /** Date the business actually needs the goods on the floor. This is the
   *  figure delay is measured against — not a target the system enforces,
   *  just the number that makes "how late is this really" answerable. */
  requiredDate: optionalDate,
  items: z.array(consignmentItemSchema).default([]),
})

/* ------------------------------------------------------------------ */
/* Step 2 — Finance                                                    */
/* ------------------------------------------------------------------ */

/**
 * The consignment total is the sum of the item lines and is never keyed in.
 * The exchange rate is booked WITH its date and source: converting a stored
 * foreign value at a live rate means the same record shows a different PKR
 * figure every time it is opened, and no printed report can be reconciled.
 */
export const financeStepSchema = z.object({
  paymentInstrument: z.enum(PAYMENT_INSTRUMENTS).optional().or(z.literal('')),
  instrumentNo: optionalText,
  /** Retirement date for LC, opening date for everything else. */
  instrumentDate: optionalDate,
  // `works` IS GONE FROM THE DRAFT — step 8. It was free text on this step
  // that the server discards (RETIRED_PAYLOAD_FIELDS); Works is the order's
  // branch and Step 1's "Works / Branch" dropdown is the control for it.
  exchangeRate: optionalNumber,
  rateDate: optionalDate,
  rateSource: optionalText,
})

/** Instrument decides what a number and a payment are called. One place. */
export const INSTRUMENT_WORDING: Record<PaymentInstrument, {
  numberLabel: string
  dateLabel: string
  paymentNoun: string
  paymentDateLabel: string
  paymentValueLabel: string
}> = {
  LC: {
    numberLabel: 'LC number', dateLabel: 'Retirement date',
    paymentNoun: 'retirement',
    paymentDateLabel: 'Retirement date', paymentValueLabel: 'Retirement value',
  },
  Adv: {
    numberLabel: 'Advance payment reference', dateLabel: 'Opening date',
    paymentNoun: 'advance payment',
    paymentDateLabel: 'Advance payment date', paymentValueLabel: 'Advance payment value',
  },
  DP: {
    numberLabel: 'DP document number', dateLabel: 'Opening date',
    paymentNoun: 'payment',
    paymentDateLabel: 'Payment date', paymentValueLabel: 'Payment value',
  },
  CAD: {
    numberLabel: 'CAD document number', dateLabel: 'Opening date',
    paymentNoun: 'payment',
    paymentDateLabel: 'Payment date', paymentValueLabel: 'Payment value',
  },
}

/* ------------------------------------------------------------------ */
/* Step 3 — Shipping                                                   */
/* ------------------------------------------------------------------ */

/**
 * Every ETA change is appended here rather than overwriting `eta`. The
 * "1st ETA … 2nd ETA …" line shown in reports is GENERATED from this, and
 * slippage is current ETA minus the FIRST ETA ever promised.
 */
export const etaRevisionSchema = z.object({
  id: z.string(),
  from: z.string(),
  to: z.string(),
  reason: z.string().min(1, 'A reason is required when the ETA changes'),
  changedBy: z.string(),
  changedAt: z.string(),
})
export type EtaRevision = z.infer<typeof etaRevisionSchema>

export const shippingStepSchema = z.object({
  modeOfShipment: z.enum(SHIPMENT_MODES).optional().or(z.literal('')),
  portOfLoading: optionalText,
  /** The real FK, captured at selection time from the async port search —
   *  see SearchableSelect's onSelectOption in Step3Shipping. */
  portOfLoadingId: z.number().optional(),
  /** "Port of delivery" — matches the sheet this replaces, not "discharge". */
  portOfDelivery: optionalText,
  portOfDeliveryId: z.number().optional(),
  readinessDate: optionalDate,
  etd: optionalDate,
  eta: optionalDate,
  etaWorks: optionalDate,
  etaRevisions: z.array(etaRevisionSchema).default([]),
})

/* ------------------------------------------------------------------ */
/* Step 4 — Payments                                                   */
/* ------------------------------------------------------------------ */

/**
 * A repeating table, not single fields — partial settlement is the normal case.
 * Each payment carries its own rate: instalments months apart settle at
 * materially different rates, and a single consignment rate would misstate
 * what was actually paid. Blank falls back to the Step 2 rate.
 */
export const paymentSchema = z.object({
  id: z.string(),
  /** The real backend row id, once saved — see consignmentItemSchema.backendId. */
  backendId: z.number().optional(),
  date: optionalDate,
  value: optionalNumber,
  exchangeRate: optionalNumber,
  status: z.enum(PAYMENT_STATUSES).default('Unpaid'),
  reference: optionalText,
  /** Swift, negotiation and commission. A cost of the transaction, not a
   *  payment against the goods — excluded from the outstanding balance,
   *  carried into actual landed cost. */
  bankCharges: optionalNumber,
})
export type Payment = z.infer<typeof paymentSchema>

export const paymentsStepSchema = z.object({
  payments: z.array(paymentSchema).default([]),
  /** LC-level, entered beside the payments. Optional and often blank — an
   *  order can genuinely carry no insurance, which is why 0 and "not entered"
   *  stay distinguishable. */
  insuranceAmount: optionalNumber,
})

/* ------------------------------------------------------------------ */
/* Step 5 — Status & Remarks                                           */
/* ------------------------------------------------------------------ */

/** Logged as events so time-at-stage is answerable. Backwards moves are
 *  allowed — cargo does get sent back for re-examination — but stay visible. */
export const statusChangeSchema = z.object({
  id: z.string(),
  from: z.string().nullable(),
  to: z.enum(CONSIGNMENT_STATUSES),
  effectiveDate: z.string(),
  note: optionalText,
  changedBy: z.string(),
  changedAt: z.string(),
})
export type StatusChange = z.infer<typeof statusChangeSchema>

export const statusRemarksStepSchema = z.object({
  status: z.enum(CONSIGNMENT_STATUSES).optional().or(z.literal('')),
  statusHistory: z.array(statusChangeSchema).default([]),
  /** Generated from the ETA and status history. Read-only, regenerated on
   *  every change — never an editable field, or a user edit will wipe it. */
  systemRemarks: z.string().default(''),
  userRemarks: optionalText,
})

/* ------------------------------------------------------------------ */
/* Step 6 — Clearance                                                  */
/* ------------------------------------------------------------------ */

/**
 * Clearance time is measured from ACTUAL arrival — the date the status became
 * "Arrived at Port" in `statusHistory` — falling back to ETA only when that
 * status was never recorded. Free days and detention are billed from real
 * arrival, not from a prediction. Nobody types the date twice.
 */
export const clearanceStepSchema = z.object({
  clearingAgent: optionalText,
  gdNumber: optionalText,
  gdDate: optionalDate,
  freeDays: optionalNumber,
  gateOutDate: optionalDate,
  /** PKR. Carried into actual landed cost. */
  demurrageCost: optionalNumber,
  /** PKR. Container detention — separate from port demurrage. */
  containerDetention: optionalNumber,
})

/* ------------------------------------------------------------------ */
/* Whole consignment                                                   */
/* ------------------------------------------------------------------ */

export const DRAFT = 'draft'
export const SUBMITTED = 'submitted'

export const consignmentDraftSchema = consignmentStepSchema
  .extend(financeStepSchema.shape)
  .extend(shippingStepSchema.shape)
  .extend(paymentsStepSchema.shape)
  .extend(statusRemarksStepSchema.shape)
  .extend(clearanceStepSchema.shape)
  .extend({
    recordState: z.enum([DRAFT, SUBMITTED]).default(DRAFT),
    /** Nothing is ever hard-deleted — closed and removed records stay
     *  available to reports. */
    isDeleted: z.boolean().default(false),
    createdBy: optionalText,
    createdAt: optionalDate,
    updatedAt: optionalDate,
  })

export type ConsignmentDraft = z.infer<typeof consignmentDraftSchema>

/* ------------------------------------------------------------------ */
/* Defaults                                                            */
/* ------------------------------------------------------------------ */

export const emptyItem = (id: string): ConsignmentItem => ({
  id,
  backendId: undefined,
  // A line the operator has just added has no order line yet. On the founding
  // batch the server makes one; on a later batch it now refuses, which is the
  // point — a new item belongs to the ORDER, not to an arrival.
  orderItemId: undefined,
  orderedQuantity: undefined,
  requisitionType: undefined,
  referenceNo: '', jobNo: '', moNo: '', othersDescription: '',
  priceBasis: 'quantity', weightUnitPrice: undefined, unitWeight: undefined,
  itemId: '', itemName: '', placeholderName: '', itemCode: '', specification: '',
  quantity: undefined, uom: '', batchNo: '', hsCode: '',
  netWeight: undefined, grossWeight: undefined, length: undefined, width: undefined, height: undefined,
  foreignUnitPrice: undefined,
})

export const emptyPayment = (id: string): Payment => ({
  id, backendId: undefined, date: '', value: undefined, exchangeRate: undefined,
  status: 'Unpaid', reference: '', bankCharges: undefined,
})

export const DRAFT_DEFAULT_VALUES: ConsignmentDraft = {
  systemId: '', consignmentNumber: '',
  branch: '', supplier: '', origin: '', currency: '',
  consignmentType: '', incoterm: '', poDate: '', requisitionDate: '', requiredDate: '',
  items: [emptyItem('item-1')],

  paymentInstrument: '', instrumentNo: '', instrumentDate: '',
  exchangeRate: undefined, rateDate: '', rateSource: '',

  modeOfShipment: '', portOfLoading: '', portOfLoadingId: undefined,
  portOfDelivery: '', portOfDeliveryId: undefined,
  readinessDate: '', etd: '', eta: '', etaWorks: '', etaRevisions: [],

  payments: [], insuranceAmount: undefined,

  status: '', statusHistory: [], systemRemarks: '', userRemarks: '',

  clearingAgent: '', gdNumber: '', gdDate: '',
  freeDays: undefined, gateOutDate: '', demurrageCost: undefined, containerDetention: undefined,

  recordState: DRAFT,
  isDeleted: false,
  createdBy: '', createdAt: '', updatedAt: '',
}

/* ------------------------------------------------------------------ */
/* Wizard step definitions                                             */
/* ------------------------------------------------------------------ */

export interface WizardStepDef {
  step: number
  key: string
  label: string
  /** Passed to react-hook-form's `trigger()`. Naming an array field validates
   *  every row in it, which is what the item and payment steps need. */
  fields: (keyof ConsignmentDraft)[]
  /** True where the whole module is normally completed after arrival — these
   *  never gate progress and their pending banner says so explicitly. */
  optionalModule?: boolean
}

export const WIZARD_STEPS: WizardStepDef[] = [
  { step: 1, key: 'consignment', label: 'Consignment',
    fields: ['branch', 'supplier', 'origin', 'currency', 'consignmentType', 'incoterm', 'poDate', 'requisitionDate', 'requiredDate', 'items'] },
  { step: 2, key: 'finance', label: 'Finance',
    fields: ['paymentInstrument', 'instrumentNo', 'instrumentDate', 'exchangeRate', 'rateDate', 'rateSource', 'items'] },
  { step: 3, key: 'shipping', label: 'Shipping',
    fields: ['modeOfShipment', 'portOfLoading', 'portOfDelivery', 'readinessDate', 'etd', 'eta', 'etaWorks'] },
  { step: 4, key: 'payments', label: 'Payments',
    fields: ['payments'], optionalModule: true },
  { step: 5, key: 'status-remarks', label: 'Status & Remarks',
    fields: ['status', 'userRemarks'] },
  { step: 6, key: 'clearance', label: 'Clearance',
    fields: ['clearingAgent', 'gdNumber', 'gdDate', 'freeDays', 'gateOutDate', 'demurrageCost', 'containerDetention'], optionalModule: true },
]

export const stepByKey = (key: string) => WIZARD_STEPS.find((s) => s.key === key)
export const stepByNumber = (n: number) => WIZARD_STEPS.find((s) => s.step === n)

/* ------------------------------------------------------------------ */
/* Derived values — computed, never stored as typed input               */
/* ------------------------------------------------------------------ */

const days = (from?: string, to?: string) =>
  from && to ? Math.round((+new Date(to) - +new Date(from)) / 86_400_000) : undefined

/** What one unit of this line costs, whichever basis it is priced on.
 *
 *  MIRRORS `order_view.line_effective_unit_price`. It is a display aid — the
 *  stored total is the server's — but it has to agree, or Step 2 shows a total
 *  the save then contradicts. Returns undefined rather than 0 when a
 *  weight-priced line is missing an input, so the line drops out of the
 *  displayed total exactly as it drops out of the stored one. */
export const effectiveUnitPrice = (item: ConsignmentItem) => {
  if (item.priceBasis === 'weight') {
    if (item.unitWeight === undefined || item.weightUnitPrice === undefined) return undefined
    return item.unitWeight * item.weightUnitPrice
  }
  return item.foreignUnitPrice
}

export const lineTotal = (item: ConsignmentItem) => {
  const rate = effectiveUnitPrice(item)
  return item.quantity !== undefined && rate !== undefined
    ? item.quantity * rate
    : undefined
}

export const foreignTotal = (d: Pick<ConsignmentDraft, 'items'>) =>
  d.items.reduce((sum, i) => sum + (lineTotal(i) ?? 0), 0)

export const localTotal = (d: Pick<ConsignmentDraft, 'items' | 'exchangeRate'>) =>
  d.exchangeRate !== undefined ? foreignTotal(d) * d.exchangeRate : undefined

export const transitDays = (d: Pick<ConsignmentDraft, 'etd' | 'eta'>) => days(d.etd, d.eta)

/** Days between when the requisition was raised and the PO was actually
 *  placed — procurement lead time, separate from anything shipping-related. */
export const procurementLeadDays = (d: Pick<ConsignmentDraft, 'requisitionDate' | 'poDate'>) =>
  days(d.requisitionDate, d.poDate)

/**
 * How late (or early) the goods will actually land versus when they were
 * required. Positive = late, zero or negative = on time or ahead. Undefined
 * only when one of the two dates is missing — never coerced to 0, since "no
 * data" and "no delay" must stay visibly different everywhere this is shown.
 */
export const requiredVsEtaDelay = (d: Pick<ConsignmentDraft, 'requiredDate' | 'eta'>) =>
  days(d.requiredDate, d.eta)

/** Current ETA against the FIRST one ever promised — not the previous one. */
export const etaSlippage = (d: Pick<ConsignmentDraft, 'eta' | 'etaRevisions'>) =>
  d.etaRevisions.length ? days(d.etaRevisions[0].from, d.eta) : undefined

/** The day it actually berthed, from the status log. */
export const arrivedAtPortDate = (d: Pick<ConsignmentDraft, 'statusHistory'>) =>
  d.statusHistory.find((s) => s.to === 'Arrived at Port')?.effectiveDate

/** Actual arrival where known, ETA as an explicit fallback. */
export const clearanceBasis = (d: Pick<ConsignmentDraft, 'statusHistory' | 'eta'>) => {
  const actual = arrivedAtPortDate(d)
  return { date: actual ?? d.eta, kind: actual ? ('arrival' as const) : ('eta' as const) }
}

export const clearanceDays = (
  d: Pick<ConsignmentDraft, 'statusHistory' | 'eta' | 'gateOutDate'>,
) => days(clearanceBasis(d).date, d.gateOutDate)

export const paidTotal = (d: Pick<ConsignmentDraft, 'payments'>) =>
  d.payments.filter((p) => p.status === 'Paid').reduce((s, p) => s + (p.value ?? 0), 0)

export const unpaidTotal = (d: Pick<ConsignmentDraft, 'payments'>) =>
  d.payments.filter((p) => p.status !== 'Paid').reduce((s, p) => s + (p.value ?? 0), 0)

export const bankChargesTotal = (d: Pick<ConsignmentDraft, 'payments'>) =>
  d.payments.reduce((s, p) => s + (p.bankCharges ?? 0), 0)

/** Bank charges are deliberately excluded — they are a cost of the
 *  transaction, not a payment against the goods. */
export const outstandingBalance = (
  d: Pick<ConsignmentDraft, 'items' | 'payments'>,
) => foreignTotal(d) - paidTotal(d) - unpaidTotal(d)

/**
 * Total money spent bringing this consignment in, from figures already
 * captured elsewhere in the wizard — goods value (Finance, converted to PKR
 * at the booked rate), bank charges (Payments), and demurrage (Clearance).
 * The system deliberately does NOT try to be the definitive landed cost:
 * accounts carry duty, freight and agent fees it can't see. This is the
 * shipment's visible expenditure, shown for reference, never keyed in.
 */
export const totalExpenditure = (
  d: Pick<ConsignmentDraft, 'items' | 'exchangeRate' | 'payments' | 'demurrageCost'>,
) => {
  const goods = localTotal(d) ?? 0
  const bank = bankChargesTotal(d)
  const demurrage = d.demurrageCost ?? 0
  return { goods, bank, demurrage, total: goods + bank + demurrage }
}

/* ------------------------------------------------------------------ */
/* Per-item hints, while typing                                        */
/* ------------------------------------------------------------------ */

/**
 * The badge beside an item row in Step 1 listing what it still lacks.
 *
 * THIS SURVIVED THE RULE-SET REMOVAL DELIBERATELY, and it is worth saying why,
 * because everything around it went. `consignmentSubmitSchema`, `pendingFields`
 * and `submitRequirements` were all deleted with the backend's
 * `submission_errors()`: they existed to PREDICT a gate, and there is no gate
 * left to predict.
 *
 * This one is not a prediction. It is an input-layer affordance — a prompt next
 * to the field while somebody is filling it in — which is exactly where data
 * quality was moved TO. It blocks nothing and gates nothing.
 */
export const itemPendingFields = (item: ConsignmentItem): string[] => {
  const out: string[] = []
  if (!item.itemName) out.push('Item name')
  if (!item.itemCode) out.push('Item code')
  if (item.quantity === undefined) out.push('Quantity')
  if (!item.uom) out.push('Unit of measure')
  if (!item.hsCode) out.push('H.S. code')
  if (!item.batchNo) out.push('Batch no.')
  if (!item.requisitionType) {
    out.push('Requisition type')
  } else {
    const labels = { referenceNo: 'Reference no.', jobNo: 'Job no.', moNo: 'MO no.', othersDescription: 'Description' }
    REQUISITION_FIELDS[item.requisitionType].forEach((f) => {
      if (!item[f]) out.push(labels[f])
    })
  }
  return out
}

