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
  'Arrived at QFL',
  'On Road',
  'Arrived at Works',
] as const
export type ConsignmentStatus = (typeof CONSIGNMENT_STATUSES)[number]

/** "Arrived at Works" closes a consignment — hidden from the list by default. */
export const CLOSED_STATUS: ConsignmentStatus = 'Arrived at Works'

export const REQUISITION_TYPES = ['store', 'engineering', 'others'] as const
export type RequisitionType = (typeof REQUISITION_TYPES)[number]

export const CONSIGNMENT_TYPES = ['efs', 'regular'] as const
export const PAYMENT_INSTRUMENTS = ['LC', 'Adv', 'DP', 'CAD'] as const
export type PaymentInstrument = (typeof PAYMENT_INSTRUMENTS)[number]

export const SHIPMENT_MODES = ['Sea', 'Air'] as const
export const PAYMENT_STATUSES = ['Paid', 'Unpaid'] as const

export const UNITS_OF_MEASURE = [
  'Pcs', 'Set', 'Pair', 'Roll', 'Box', 'Carton', 'Drum', 'Pallet',
  'Kg', 'Gram', 'Ton (MT)', 'Lb',
  'Metre', 'Centimetre', 'Foot', 'Inch',
  'Sq. Metre', 'Cu. Metre', 'Litre', 'Millilitre',
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

  // requisition (per item)
  requisitionType: z.enum(REQUISITION_TYPES).optional(),
  referenceNo: optionalText,
  jobNo: optionalText,
  moNo: optionalText,
  othersDescription: optionalText,

  // item
  itemId: optionalText,              // FK to item master once one exists
  itemName: z.string().default(''),
  itemCode: z.string().default(''),
  specification: optionalText,
  quantity: optionalNumber,
  uom: optionalText,
  batchNo: optionalText,
  /** An item may classify differently by variant or origin, so this is a list
   *  on the master; the line records the one actually used. */
  hsCode: optionalText,

  // step 2 — pricing is per item, since line values drive landed cost later
  foreignUnitPrice: optionalNumber,

  // step 7 — manual, in PKR, never calculated
  elcPkr: optionalNumber,
  alcPkr: optionalNumber,
  elcEnteredBy: optionalText,
  elcEnteredAt: optionalDate,
  alcEnteredBy: optionalText,
  alcEnteredAt: optionalDate,
})
export type ConsignmentItem = z.infer<typeof consignmentItemSchema>

export const consignmentStepSchema = z.object({
  /** Internal ID, generated on creation and never edited (e.g. QC-2026-0148). */
  systemId: z.string().default(''),
  branch: optionalText,
  supplier: optionalText,
  origin: optionalText,
  currency: optionalText,
  consignmentType: z.enum(CONSIGNMENT_TYPES).optional().or(z.literal('')),
  poDate: optionalDate,
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
  works: optionalText,
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
  /** "Port of delivery" — matches the sheet this replaces, not "discharge". */
  portOfDelivery: optionalText,
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
/* Submit-time rules                                                   */
/* ------------------------------------------------------------------ */

/**
 * Everything the draft lets slide, enforced here. Deliberately NOT required:
 * payments (a consignment can sit part-paid for months), the whole clearance
 * module (completed after landing), and landed cost (finalised by accounts
 * long after arrival).
 */
export const consignmentSubmitSchema = consignmentDraftSchema.superRefine((v, ctx) => {
  const need = (path: (string | number)[], message: string) =>
    ctx.addIssue({ code: z.ZodIssueCode.custom, path, message })

  if (!v.branch) need(['branch'], 'Branch is required')
  if (!v.supplier) need(['supplier'], 'Supplier is required')
  if (!v.origin) need(['origin'], 'Country of origin is required')
  if (!v.currency) need(['currency'], 'Currency is required')

  if (v.items.length === 0) {
    need(['items'], 'Add at least one item')
  }

  v.items.forEach((item, i) => {
    if (!item.itemName) need(['items', i, 'itemName'], 'Item name is required')
    if (!item.itemCode) need(['items', i, 'itemCode'], 'Item code is required')
    if (item.quantity === undefined) need(['items', i, 'quantity'], 'Quantity is required')
    if (!item.uom) need(['items', i, 'uom'], 'Unit of measure is required')

    if (!item.requisitionType) {
      need(['items', i, 'requisitionType'], 'Requisition type is required')
    } else {
      // conditional requirements read from the same map the form uses
      REQUISITION_FIELDS[item.requisitionType].forEach((f) => {
        if (!item[f]) {
          need(['items', i, f], `${f} is required for a ${item.requisitionType} item`)
        }
      })
    }
  })

  if (!v.paymentInstrument) need(['paymentInstrument'], 'Payment instrument is required')
  if (!v.instrumentNo) need(['instrumentNo'], 'Instrument number is required')
  if (!v.works) need(['works'], 'Works is required')
  if (v.exchangeRate === undefined) need(['exchangeRate'], 'Exchange rate is required')
  if (!v.rateDate) need(['rateDate'], 'The date the rate was booked is required')

  if (!v.status) need(['status'], 'Status is required')

  if (v.etd && v.eta && new Date(v.eta) < new Date(v.etd)) {
    need(['eta'], 'ETA cannot be before ETD')
  }
  if (v.gateOutDate && v.eta && new Date(v.gateOutDate) < new Date(v.eta)) {
    need(['gateOutDate'], 'Gate out cannot be before arrival')
  }
})

/* ------------------------------------------------------------------ */
/* Defaults                                                            */
/* ------------------------------------------------------------------ */

export const emptyItem = (id: string): ConsignmentItem => ({
  id,
  requisitionType: undefined,
  referenceNo: '', jobNo: '', moNo: '', othersDescription: '',
  itemId: '', itemName: '', itemCode: '', specification: '',
  quantity: undefined, uom: '', batchNo: '', hsCode: '',
  foreignUnitPrice: undefined,
  elcPkr: undefined, alcPkr: undefined,
  elcEnteredBy: '', elcEnteredAt: '', alcEnteredBy: '', alcEnteredAt: '',
})

export const emptyPayment = (id: string): Payment => ({
  id, date: '', value: undefined, exchangeRate: undefined,
  status: 'Unpaid', reference: '', bankCharges: undefined,
})

export const DRAFT_DEFAULT_VALUES: ConsignmentDraft = {
  systemId: '',
  branch: '', supplier: '', origin: '', currency: '',
  consignmentType: '', poDate: '',
  items: [emptyItem('item-1')],

  paymentInstrument: '', instrumentNo: '', instrumentDate: '', works: '',
  exchangeRate: undefined, rateDate: '', rateSource: '',

  modeOfShipment: '', portOfLoading: '', portOfDelivery: '',
  readinessDate: '', etd: '', eta: '', etaWorks: '', etaRevisions: [],

  payments: [],

  status: '', statusHistory: [], systemRemarks: '', userRemarks: '',

  clearingAgent: '', gdNumber: '', gdDate: '',
  freeDays: undefined, gateOutDate: '', demurrageCost: undefined,

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
    fields: ['branch', 'supplier', 'origin', 'currency', 'consignmentType', 'poDate', 'items'] },
  { step: 2, key: 'finance', label: 'Finance',
    fields: ['paymentInstrument', 'instrumentNo', 'instrumentDate', 'works', 'exchangeRate', 'rateDate', 'rateSource', 'items'] },
  { step: 3, key: 'shipping', label: 'Shipping',
    fields: ['modeOfShipment', 'portOfLoading', 'portOfDelivery', 'readinessDate', 'etd', 'eta', 'etaWorks'] },
  { step: 4, key: 'payments', label: 'Payments',
    fields: ['payments'], optionalModule: true },
  { step: 5, key: 'status-remarks', label: 'Status & Remarks',
    fields: ['status', 'userRemarks'] },
  { step: 6, key: 'clearance', label: 'Clearance',
    fields: ['clearingAgent', 'gdNumber', 'gdDate', 'freeDays', 'gateOutDate', 'demurrageCost'], optionalModule: true },
  { step: 7, key: 'landed-cost', label: 'Landed Cost',
    fields: ['items'], optionalModule: true },
]

export const stepByKey = (key: string) => WIZARD_STEPS.find((s) => s.key === key)
export const stepByNumber = (n: number) => WIZARD_STEPS.find((s) => s.step === n)

/* ------------------------------------------------------------------ */
/* Derived values — computed, never stored as typed input               */
/* ------------------------------------------------------------------ */

const days = (from?: string, to?: string) =>
  from && to ? Math.round((+new Date(to) - +new Date(from)) / 86_400_000) : undefined

export const lineTotal = (item: ConsignmentItem) =>
  item.quantity !== undefined && item.foreignUnitPrice !== undefined
    ? item.quantity * item.foreignUnitPrice
    : undefined

export const foreignTotal = (d: Pick<ConsignmentDraft, 'items'>) =>
  d.items.reduce((sum, i) => sum + (lineTotal(i) ?? 0), 0)

export const localTotal = (d: Pick<ConsignmentDraft, 'items' | 'exchangeRate'>) =>
  d.exchangeRate !== undefined ? foreignTotal(d) * d.exchangeRate : undefined

export const transitDays = (d: Pick<ConsignmentDraft, 'etd' | 'eta'>) => days(d.etd, d.eta)

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

export const elcTotal = (d: Pick<ConsignmentDraft, 'items'>) =>
  d.items.reduce((s, i) => s + (i.elcPkr ?? 0), 0)

export const alcTotal = (d: Pick<ConsignmentDraft, 'items'>) =>
  d.items.reduce((s, i) => s + (i.alcPkr ?? 0), 0)

/** Absolute and percentage — reports use the percentage. */
export const landedCostVariance = (d: Pick<ConsignmentDraft, 'items'>) => {
  const elc = elcTotal(d)
  const alc = alcTotal(d)
  if (!elc || !alc) return undefined
  return { absolute: alc - elc, percent: ((alc - elc) / elc) * 100 }
}

/** The figure supplier comparison reports key on, since quantities differ
 *  between shipments. */
export const alcPerUnit = (item: ConsignmentItem) =>
  item.alcPkr !== undefined && item.quantity ? item.alcPkr / item.quantity : undefined

/* ------------------------------------------------------------------ */
/* Pending information                                                 */
/* ------------------------------------------------------------------ */

/**
 * Drives the per-item badges, the per-step banners and the list view's
 * "fields missing" flag. One implementation so a field added later surfaces
 * everywhere at once, and every gap is named rather than left blank.
 */
export const pendingFields = (d: ConsignmentDraft): string[] => {
  const out: string[] = []
  const parsed = consignmentSubmitSchema.safeParse(d)
  if (!parsed.success) {
    for (const issue of parsed.error.issues) out.push(issue.message)
  }
  return [...new Set(out)]
}

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
