import { z } from 'zod'

/**
 * One zod object per wizard step, merged into a single draft schema. The
 * wizard validates only the current step's fields via `trigger(fields)` on
 * each Next click (react-hook-form's documented multi-step pattern), so a
 * schema-level `required` on a later step's field never blocks an earlier
 * one — see wizard/LogisticsStatusWizard.tsx.
 *
 * Mirrors features/importsStatus/schema.ts. The one structural difference:
 * a Logistics order is Export | Local, and that choice drives conditional
 * fields across several steps (origin shape, IDM/export numbers, the
 * expenditure set, and the status list). Rather than scatter `if` checks in
 * templates, the order type lives on Step 1 and each step reads it from the
 * form context — same "single rules object per screen" convention the imports
 * module and CLAUDE.md call for.
 */

export const ORDER_TYPES = ['Export', 'Local'] as const
export type OrderType = (typeof ORDER_TYPES)[number]

// --- Step 1: Consignment / order details ---------------------------------
export const consignmentSchema = z
  .object({
    orderType: z.enum(ORDER_TYPES),
    // Origin is a country for exports, and city + province for local orders.
    // All three are kept on the draft; the form only requires the pair that
    // matches the current order type (enforced in superRefine below).
    originCountry: z.string().optional(),
    originCity: z.string().optional(),
    originProvince: z.string().optional(),
    customerName: z.string().min(1, 'Customer name is required'),
    itemDetail: z.string().min(1, 'Item detail is required'),
    quantity: z.number().positive('Quantity must be greater than 0'),
    netWeight: z.number().min(0, 'Net weight cannot be negative'),
    grossWeight: z.number().min(0, 'Gross weight cannot be negative'),
    // IDM is captured for every order. Export orders also carry an export no.
    idm: z.string().min(1, 'IDM is required'),
    exportNo: z.string().optional(),
    batchNo: z.string().optional(), // optional per spec
  })
  .superRefine((val, ctx) => {
    if (val.orderType === 'Export') {
      if (!val.originCountry?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['originCountry'], message: 'Country of origin is required for exports' })
      }
      if (!val.exportNo?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['exportNo'], message: 'Export no. is required for exports' })
      }
    } else {
      if (!val.originCity?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['originCity'], message: 'City is required for local orders' })
      }
      if (!val.originProvince?.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['originProvince'], message: 'Province is required for local orders' })
      }
    }
    if (val.grossWeight > 0 && val.netWeight > val.grossWeight) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: ['netWeight'], message: 'Net weight cannot exceed gross weight' })
    }
  })

// --- Step 2: Transportation -----------------------------------------------
export const transportationSchema = z.object({
  transporterName: z.string().optional(),
  vehicleType: z.string().optional(),
  gateOutDate: z.string().optional(), // ISO yyyy-mm-dd
  dispatchNoteDate: z.string().optional(),
  // delayDays is derived (gate out - dispatch note) and never keyed in.
  quotedFreight: z.number().min(0).optional(),
  actualFreight: z.number().min(0).optional(),
  // ratePerWeight is derived (actual freight / gross weight) and never keyed in.
  actualDeliveryDate: z.string().optional(),
  originFactory: z.string().optional(),
  destination: z.string().optional(),
})

// --- Step 3: Shipping ------------------------------------------------------
export const shippingSchema = z.object({
  containerCount: z.number().int().min(0).optional(),
  containerType: z.string().optional(),
  pol: z.string().optional(), // Port of Loading
  pod: z.string().optional(), // Port of Discharge
  shippingLine: z.string().optional(),
  clearingAgent: z.string().optional(),
  bookingNo: z.string().optional(),
  portInDate: z.string().optional(),
  etdSailingDate: z.string().optional(),
  croArrivalDate: z.string().optional(),
  actualArrivalDate: z.string().optional(),
  // arrivalDelayDays is derived (actual arrival - CRO arrival) and never keyed in.
})

// --- Step 4: Expenditures --------------------------------------------------
// The full export set; local orders only use packingCost + transportationCharges.
// Everything is optional here — costs land piecemeal, and the pending-info
// convention (imports module) surfaces what is still missing.
export const expendituresSchema = z.object({
  // shared
  packingCost: z.number().min(0).optional(),
  // local
  transportationCharges: z.number().min(0).optional(),
  // export-only
  insurance: z.number().min(0).optional(),
  truckingLhrToKhi: z.number().min(0).optional(),
  fumigationCost: z.number().min(0).optional(),
  lashing: z.number().min(0).optional(),
  qflCharges: z.number().min(0).optional(),
  qflContainerMovement: z.number().min(0).optional(),
  customClearanceCharges: z.number().min(0).optional(),
  portCharges: z.number().min(0).optional(),
  dhlCharges: z.number().min(0).optional(),
  seaAirFreight: z.number().min(0).optional(),
})

// --- Step 5: Status --------------------------------------------------------
export const statusSchema = z.object({
  status: z.string().min(1, 'Status is required'),
  remarks: z.string().optional(),
})

/**
 * The wizard needs one flat object for react-hook-form. `consignmentSchema`
 * is a ZodEffects (because of superRefine), which has no `.merge`, so the
 * draft is composed from the raw shapes and the cross-field refinement is
 * re-applied on top. Step-level validation still uses the per-step schemas
 * above via `safeParse` in the wizard.
 */
export const consignmentDraftSchema = z
  .object({
    orderType: z.enum(ORDER_TYPES),
    originCountry: z.string().optional(),
    originCity: z.string().optional(),
    originProvince: z.string().optional(),
    customerName: z.string().min(1, 'Customer name is required'),
    itemDetail: z.string().min(1, 'Item detail is required'),
    quantity: z.number().positive('Quantity must be greater than 0'),
    netWeight: z.number().min(0),
    grossWeight: z.number().min(0),
    idm: z.string().min(1, 'IDM is required'),
    exportNo: z.string().optional(),
    batchNo: z.string().optional(),
  })
  .merge(transportationSchema)
  .merge(shippingSchema)
  .merge(expendituresSchema)
  .merge(statusSchema)

export type LogisticsDraft = z.infer<typeof consignmentDraftSchema>

export const DRAFT_DEFAULT_VALUES: LogisticsDraft = {
  orderType: 'Export',
  originCountry: '',
  originCity: '',
  originProvince: '',
  customerName: '',
  itemDetail: '',
  quantity: 0,
  netWeight: 0,
  grossWeight: 0,
  idm: '',
  exportNo: '',
  batchNo: '',
  transporterName: '',
  vehicleType: '',
  gateOutDate: '',
  dispatchNoteDate: '',
  quotedFreight: 0,
  actualFreight: 0,
  actualDeliveryDate: '',
  originFactory: '',
  destination: '',
  containerCount: 0,
  containerType: '',
  pol: '',
  pod: '',
  shippingLine: '',
  clearingAgent: '',
  bookingNo: '',
  portInDate: '',
  etdSailingDate: '',
  croArrivalDate: '',
  actualArrivalDate: '',
  packingCost: 0,
  transportationCharges: 0,
  insurance: 0,
  truckingLhrToKhi: 0,
  fumigationCost: 0,
  lashing: 0,
  qflCharges: 0,
  qflContainerMovement: 0,
  customClearanceCharges: 0,
  portCharges: 0,
  dhlCharges: 0,
  seaAirFreight: 0,
  status: '',
  remarks: '',
}

export interface WizardStepDef {
  step: number
  key: string
  label: string
  fields: (keyof LogisticsDraft)[]
}

// Five steps per the Logistics spec: Order, Transportation, Shipping,
// Expenditures, Status. The `fields` arrays are what the wizard runs
// step-level validation against on each Next.
export const WIZARD_STEPS: WizardStepDef[] = [
  {
    step: 1,
    key: 'order',
    label: 'Order Details',
    fields: [
      'orderType', 'originCountry', 'originCity', 'originProvince', 'customerName',
      'itemDetail', 'quantity', 'netWeight', 'grossWeight', 'idm', 'exportNo', 'batchNo',
    ],
  },
  {
    step: 2,
    key: 'transportation',
    label: 'Transportation',
    fields: [
      'transporterName', 'vehicleType', 'gateOutDate', 'dispatchNoteDate',
      'quotedFreight', 'actualFreight', 'actualDeliveryDate', 'originFactory', 'destination',
    ],
  },
  {
    step: 3,
    key: 'shipping',
    label: 'Shipping',
    fields: [
      'containerCount', 'containerType', 'pol', 'pod', 'shippingLine', 'clearingAgent',
      'bookingNo', 'portInDate', 'etdSailingDate', 'croArrivalDate', 'actualArrivalDate',
    ],
  },
  {
    step: 4,
    key: 'expenditures',
    label: 'Expenditures',
    fields: [
      'packingCost', 'transportationCharges', 'insurance', 'truckingLhrToKhi', 'fumigationCost',
      'lashing', 'qflCharges', 'qflContainerMovement', 'customClearanceCharges', 'portCharges',
      'dhlCharges', 'seaAirFreight',
    ],
  },
  { step: 5, key: 'status', label: 'Status', fields: ['status', 'remarks'] },
]

// --- Status choices --------------------------------------------------------
// Ordered pipeline. Export orders run the full chain; local orders skip the
// sea legs and close at Delivered. Kept as one map so a step can offer only
// the statuses valid for the current order type.
export const EXPORT_STATUSES = [
  'Under Production',
  'Under Packing',
  'Transportation',
  'Under Shipping Arrangement',
  'At QFL',
  'At Port',
  'On Water',
  'Delivered',
] as const

export const LOCAL_STATUSES = [
  'Under Production',
  'Under Packing',
  'Transportation',
  'Delivered',
] as const

export function statusesFor(orderType: OrderType): readonly string[] {
  return orderType === 'Export' ? EXPORT_STATUSES : LOCAL_STATUSES
}

// --- Derived-value helpers (calculated, never keyed in) --------------------

/** Whole-day difference between two ISO dates (later - earlier). Null if either is missing. */
export function daysBetween(fromISO?: string, toISO?: string): number | null {
  if (!fromISO || !toISO) return null
  const a = new Date(fromISO).getTime()
  const b = new Date(toISO).getTime()
  if (Number.isNaN(a) || Number.isNaN(b)) return null
  return Math.round((b - a) / 86_400_000)
}

/** Actual freight per unit of gross weight. Null if either input is missing/zero. */
export function ratePerWeight(actualFreight?: number, grossWeight?: number): number | null {
  if (!actualFreight || !grossWeight) return null
  return actualFreight / grossWeight
}
