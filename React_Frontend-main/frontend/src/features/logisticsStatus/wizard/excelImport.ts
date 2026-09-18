import { ORDER_TYPES, DEPARTMENTS, SHIPMENT_MODES } from '../schema'

/**
 * Step 1 Excel import — an ADDITIONAL way to fill the logistics wizard's
 * first step, alongside the existing manual form. See
 * logistics-excel-import-spec.md at the repo root for the full spec this
 * implements. Scope: Step 1 only, nowhere else in the app.
 *
 * One file = one MO, one order — there is no real batching on the backend
 * yet (mo_no is a nullable, non-unique grouping key), so "this MO already
 * exists" is treated as a straight duplicate by the check-mo endpoint this
 * module's caller uses. Revisit when real batching is designed.
 */

const EXPECTED_COLUMNS = [
  'MO', 'Order Type', 'Department', 'Shipment Mode', 'Customer Name', 'Mill',
  'Country', 'Job Number', 'Item Detail', 'Quantity', 'Unit Weight',
  'Planned RFD', 'Actual RFD',
] as const

export interface ParsedLogisticsImport {
  moNo: string
  orderType: string | null      // null = present in file but unmatched, warn
  department: string | null
  shipmentMode: string | null
  customerName: string | null
  mill: string | null
  originCountry: string | null
  items: Array<{
    jobNo: string | null
    itemDetail: string | null
    quantity: number | null
    unitWeight: number | null
    plannedRfdDate: string | null   // YYYY-MM-DD
    actualRfdDate: string | null
  }>
  warnings: string[]   // "Department 'Sugra' didn't match any known department"
}

export class ExcelImportError extends Error {}

function normalizeHeader(raw: unknown): string {
  return String(raw ?? '').trim()
}

function matchEnum(value: unknown, options: readonly string[]): { matched: string | null; raw: string } {
  const raw = String(value ?? '').trim()
  if (!raw) return { matched: null, raw }
  const found = options.find((o) => o.toLowerCase() === raw.toLowerCase())
  return { matched: found ?? null, raw }
}

function excelDateToIso(value: unknown): string | null {
  if (value == null || value === '') return null
  // With `raw: true` (see the sheet_to_json call below) + `cellDates: true`
  // on XLSX.read, a real date cell comes back as a JS Date object — DO NOT
  // hand-roll the serial-number-to-date math; rely on cellDates and just
  // format here.
  //
  // THIS FUNCTION DEPENDS ON `raw: true`, NOT JUST `cellDates: true`. Verified
  // directly against this workbook shape: with `raw: false` (which an
  // earlier draft of this parser used, to get trimmed string headers), a
  // date cell comes back as a FORMATTED STRING ("2/10/25"), not a Date
  // instance, even with cellDates:true set — so `value instanceof Date`
  // below would be false for every row and every RFD date would silently
  // come back null. Header trimming does not need raw:false either — text
  // cells return their string value under `raw: true` too, only numbers and
  // dates are affected by the flag. If this function ever starts returning
  // null for every date, check that `raw: true` is still set below first.
  if (value instanceof Date) {
    const y = value.getFullYear()
    const m = String(value.getMonth() + 1).padStart(2, '0')
    const d = String(value.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return null   // a non-date value in a date column: treat as blank, not a crash
}

/** A numeric cell under `raw: true` is already a JS number in the normal
 *  case; guards against a stray text value ("N/A", a trailing unit) landing
 *  in a numeric column, which `Number(...)` would otherwise turn into NaN
 *  and propagate into the draft as a broken number. */
function parseNumericCell(value: unknown): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

export async function parseLogisticsImportFile(file: File): Promise<ParsedLogisticsImport> {
  // Loaded lazily (matches AssistantDataTable's export code) — 'xlsx' is a
  // ~400KB dependency and this feature is used rarely, on one wizard step;
  // a static import here would pull it into the main bundle for every user
  // on every page load instead of only when someone actually imports a file.
  const XLSX = await import('xlsx')
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array', cellDates: true })
  const sheet = workbook.Sheets[workbook.SheetNames[0]]
  if (!sheet) throw new ExcelImportError('The file has no readable sheet.')

  // `raw: true` so numbers stay JS numbers and date cells stay Date objects
  // (see excelDateToIso above for why `raw: false` silently breaks dates).
  // Header trimming below works fine under raw:true too — text cells are
  // unaffected by the flag, only numbers/dates are.
  const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, raw: true, defval: null })
  if (rows.length < 2) throw new ExcelImportError('The file has no data rows.')

  const headerRow = (rows[0] as unknown[]).map(normalizeHeader)
  const columnIndex: Record<string, number> = {}
  for (const expected of EXPECTED_COLUMNS) {
    const idx = headerRow.findIndex((h) => h.toLowerCase() === expected.toLowerCase())
    if (idx === -1) throw new ExcelImportError(`Expected column "${expected}" was not found in the file.`)
    columnIndex[expected] = idx
  }

  const dataRows = rows.slice(1).filter((r) => (r as unknown[]).some((c) => c != null && c !== ''))
  if (dataRows.length === 0) throw new ExcelImportError('The file has a header but no data rows.')

  const get = (row: unknown[], col: (typeof EXPECTED_COLUMNS)[number]) => row[columnIndex[col]]

  // Forward-fill: order-level columns only carry a value on the first row.
  const firstRow = dataRows[0] as unknown[]
  const moNo = String(get(firstRow, 'MO') ?? '').trim()
  if (!moNo) throw new ExcelImportError('MO is blank on the first row — MO is required to import a file.')

  // Sanity check: any LATER row with a non-blank, DIFFERENT MO means this
  // file likely bundles more than one order. Fail loudly rather than
  // silently keeping only the first MO and dropping a conflicting one.
  for (let i = 1; i < dataRows.length; i++) {
    const laterMo = String(get(dataRows[i] as unknown[], 'MO') ?? '').trim()
    if (laterMo && laterMo !== moNo) {
      throw new ExcelImportError(
        `Row ${i + 2} has a different MO ("${laterMo}") than the first row ("${moNo}"). ` +
        `This importer expects one MO per file.`
      )
    }
  }

  const warnings: string[] = []
  const orderTypeMatch = matchEnum(get(firstRow, 'Order Type'), ORDER_TYPES)
  const departmentMatch = matchEnum(get(firstRow, 'Department'), DEPARTMENTS)
  const shipmentModeMatch = matchEnum(get(firstRow, 'Shipment Mode'), SHIPMENT_MODES)
  if (orderTypeMatch.raw && !orderTypeMatch.matched) warnings.push(`Order Type "${orderTypeMatch.raw}" didn't match a known order type — left blank.`)
  if (departmentMatch.raw && !departmentMatch.matched) warnings.push(`Department "${departmentMatch.raw}" didn't match a known department — left blank.`)
  if (shipmentModeMatch.raw && !shipmentModeMatch.matched) warnings.push(`Shipment Mode "${shipmentModeMatch.raw}" didn't match a known shipment mode — left blank.`)

  const items = dataRows.map((row, i) => {
    const r = row as unknown[]
    const quantityRaw = get(r, 'Quantity')
    const weightRaw = get(r, 'Unit Weight')
    const quantity = parseNumericCell(quantityRaw)
    const unitWeight = parseNumericCell(weightRaw)
    if (quantityRaw != null && quantityRaw !== '' && quantity === null) {
      warnings.push(`Row ${i + 2}: Quantity "${String(quantityRaw)}" isn't a number — left blank.`)
    }
    if (weightRaw != null && weightRaw !== '' && unitWeight === null) {
      warnings.push(`Row ${i + 2}: Unit Weight "${String(weightRaw)}" isn't a number — left blank.`)
    }
    return {
      jobNo: (get(r, 'Job Number') as string) || null,
      itemDetail: (get(r, 'Item Detail') as string) || null,
      quantity,
      unitWeight,
      plannedRfdDate: excelDateToIso(get(r, 'Planned RFD')),
      actualRfdDate: excelDateToIso(get(r, 'Actual RFD')),
    }
  })

  return {
    moNo,
    orderType: orderTypeMatch.matched,
    department: departmentMatch.matched,
    shipmentMode: shipmentModeMatch.matched,
    customerName: (get(firstRow, 'Customer Name') as string) || null,
    mill: (get(firstRow, 'Mill') as string) || null,
    originCountry: (get(firstRow, 'Country') as string) || null,
    items,
    warnings,
  }
}
