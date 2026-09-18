# Logistics Wizard — Step 1 Excel Import — Implementation Spec

## What this is, and what it explicitly is NOT

An **additional** way to fill Step 1 of the logistics wizard, alongside the
existing manual form — not a replacement for it. Every field stays exactly as
editable and manually-fillable as it is today. This feature only adds an
"Import file" control that pre-fills the same fields the user would otherwise
type in by hand.

**Scope: Step 1 of the logistics wizard only.** Nowhere else in the app.

---

## Decisions locked in (from the conversation that produced this spec)

- One Excel file = one MO, one order. Not a batch feature — there is no real
  batching on the backend yet (`nextBatchNoForMo`/`getMoGroupSummary` in
  `logisticsStatusData.ts` are frontend-only mock scaffolding for a future
  feature). `mo_no` stays nullable/non-unique in the schema — **no migration,
  no DB constraint change in this spec.**
- Because there's no real batching yet, "an order with this MO already
  exists" legitimately means "duplicate" right now — there's no valid case
  today where a second real order under the same MO should exist. **This
  will need to be revisited when real batching is designed** — leave an
  explicit comment saying so at the check itself (see Part 2), so whoever
  builds batching later doesn't have to rediscover this.
- Blank MO cell in the file → hard parse failure. Every other field may be
  blank — MO is the one exception, since the whole feature is keyed on it.
- Sanity check: if any row after the first has a **non-blank** MO that
  differs from the first row's Mo, fail the parse with a clear error (likely
  sign of two orders concatenated into one file) rather than silently using
  only the first row's value.
- On a rejected (duplicate) file: nothing was imported, the file input
  re-enables so the user can pick a different file.
- On a successful import: fields are populated and **stay fully editable**;
  the import control itself becomes permanently disabled for the rest of
  that wizard session (importing a second file into an in-progress order
  isn't supported — starting over means abandoning the draft, same as
  today).
- `Country` column, header exactly `"Country"`, maps to `originCountry`.
  Free text on both ends (the field is a plain `<Input>`, not a dropdown),
  so no enum-matching problem here, unlike Order Type/Department/Shipment
  Mode.

---

## The file format (read directly from the sample provided)

```
MO            | Order Type | Department | Shipment Mode | Customer Name | Mill              | Country | Job Number  | Item Detail | Quantity | Unit Weight | Planned RFD | Actual RFD
mo-1000091-1  | Export     | Sugar      | EFS            | Sonkor        | Sugar-Mill-190902 | ...     | 1234-0000-1 | Hammer      | 10       | 2           | 2025-02-10  | 2026-04-15
              |            |            |                |               |                   |         | 1234-0000-2 | Pinion      | 12       | 3.5         | 2025-02-11  | 2026-04-16
              |            |            |                |               |                   |         | 1234-0000-3 | Rod         | 7        | 2.78        | 2025-02-12  | 2026-04-17
```

**Two structural facts that must drive the parser, confirmed directly from
the sample file, not assumed:**

1. **Order-level columns (MO, Order Type, Department, Shipment Mode,
   Customer Name, Mill, Country) are only populated on the first data row.**
   Every row after that has them blank. The parser must **forward-fill**
   these six/seven columns from the first row — reading them per-row would
   give `null` for every item after the first.
2. **The header cell for Order Type is literally `"Order Type "` — with a
   trailing space**, confirmed by reading the actual file with `openpyxl`.
   A naive exact-string column lookup silently fails to find this column at
   all. **Every header cell must be trimmed (and I'd recommend
   case-normalized) before matching against expected column names** — this
   is not a hypothetical edge case, it's present in the real file.

### Column → field mapping

| File column (trimmed) | Level | Draft field | Matching rule |
|---|---|---|---|
| `MO` | Order | `moNo` | Required, non-blank (hard failure if blank) |
| `Order Type` | Order | `orderType` | Case-insensitive/trimmed match against `ORDER_TYPES` (`'Export' \| 'Local'`); no match → leave blank + warn, don't fail the whole import |
| `Department` | Order | `department` | Same rule, against `DEPARTMENTS` (`'Cement' \| 'Sugar' \| 'General'`) |
| `Shipment Mode` | Order | `shipmentMode` | Same rule, against `SHIPMENT_MODES` (`'EFS' \| 'Regular' \| 'Pending'`) |
| `Customer Name` | Order | `customerName` | Free text, no matching needed (field allows free text already) |
| `Mill` | Order | `mill` | Free text, optional |
| `Country` | Order | `originCountry` | Free text, optional. Maps regardless of `orderType` — if the row turns out to be `Local`, this value is simply not shown in the UI (Step 1 only renders `originCountry` for Export orders) but is harmless to have set |
| `Job Number` | Item (per row) | `items[i].jobNo` | Free text |
| `Item Detail` | Item (per row) | `items[i].itemDetail` | Free text |
| `Quantity` | Item (per row) | `items[i].quantity` | Numeric, blank allowed |
| `Unit Weight` | Item (per row) | `items[i].unitWeight` | Numeric, blank allowed |
| `Planned RFD` | Item (per row) | `items[i].plannedRfdDate` | Date → format as `YYYY-MM-DD` string for the `<input type="date">` |
| `Actual RFD` | Item (per row) | `items[i].actualRfdDate` | Same date handling |

**Not in the file, stays manual** (confirmed): `originCity`, `originProvince`
(Local orders only — no columns for these exist; a Local-order import simply
leaves them for the user to fill), `incoterm`, `totalPackages`,
`budgetedPackingCost` (per item), `customerNote`.

---

## Part 1 — Frontend: the parser module

### New file: `src/features/logisticsStatus/wizard/excelImport.ts`

```typescript
import * as XLSX from 'xlsx'
import { ORDER_TYPES, DEPARTMENTS, SHIPMENT_MODES } from '../schema'

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
  // With XLSX.read(..., { cellDates: true }), date cells already come back
  // as JS Date objects, not serial numbers — DO NOT hand-roll the
  // serial-number-to-date math; rely on cellDates and just format here.
  if (value instanceof Date) {
    const y = value.getFullYear()
    const m = String(value.getMonth() + 1).padStart(2, '0')
    const d = String(value.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  }
  return null   // a non-date value in a date column: treat as blank, not a crash
}

export async function parseLogisticsImportFile(file: File): Promise<ParsedLogisticsImport> {
  const buffer = await file.arrayBuffer()
  const workbook = XLSX.read(buffer, { type: 'array', cellDates: true })
  const sheet = workbook.Sheets[workbook.SheetNames[0]]
  if (!sheet) throw new ExcelImportError('The file has no readable sheet.')

  // header: 1 gives us the raw header row separately, so we can trim/validate
  // it BEFORE using sheet_to_json's header-keyed rows (which would silently
  // produce a key of "Order Type " with the trailing space intact otherwise).
  const rows = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, raw: false, defval: null })
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

  const items = dataRows.map((row) => {
    const r = row as unknown[]
    const quantityRaw = get(r, 'Quantity')
    const weightRaw = get(r, 'Unit Weight')
    return {
      jobNo: (get(r, 'Job Number') as string) || null,
      itemDetail: (get(r, 'Item Detail') as string) || null,
      quantity: quantityRaw != null && quantityRaw !== '' ? Number(quantityRaw) : null,
      unitWeight: weightRaw != null && weightRaw !== '' ? Number(weightRaw) : null,
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
```

### Edge cases in this module — go through every one

1. **`{ raw: false }` in `sheet_to_json`** turns numbers into their formatted
   string form in some cases — verify `Quantity`/`Unit Weight` still parse
   correctly as numbers via `Number(...)` after this; if `raw: false` causes
   thousand-separators or currency-like formatting to leak into the string
   (depends on the source cell's number format), switch to `raw: true` for
   the numeric columns specifically and keep `cellDates: true` for dates —
   don't assume `raw: false` is uniformly safe for numbers just because it
   was chosen for correct header-string reading.
2. **`cellDates: true` must be set on `XLSX.read`, not assumed.** Without it,
   date cells come back as raw Excel serial numbers (e.g. `45689`), not `Date`
   objects — `excelDateToIso` would then always return `null` for every date,
   silently dropping every RFD date without any error. This is the single
   most likely silent failure mode if this option is ever removed or
   forgotten in a refactor — worth a code comment saying exactly this.
3. **A completely blank row in the middle of the data** (someone left a gap
   in the spreadsheet) — the `.filter((r) => r.some(...))` line drops fully
   blank rows before processing; confirm this doesn't also drop a row that's
   blank except for, say, only a Quantity value with everything else
   genuinely empty (it shouldn't, since `.some()` only needs one non-null
   cell) — but test this specifically with a deliberately sparse row.
4. **Excel columns in a different order than `EXPECTED_COLUMNS`.** The
   `findIndex` lookup means column *order* in the file doesn't matter, only
   column *names* — confirm this is actually desired (I'd assume yes, more
   robust) rather than requiring a fixed column order.
5. **Extra columns in the file beyond the expected ones** — these are simply
   ignored (never referenced by `columnIndex`); confirm this is fine rather
   than something that should warn.
6. **A `Country` value present when `Order Type` resolves to `Local`.** Per
   the decision above, this is harmless — the value gets set on the draft
   regardless, but Step 1 doesn't render `originCountry` for Local orders, so
   it's simply unused in that case. Not an error condition.
7. **The file has a completely different first sheet than expected** (e.g. a
   workbook with multiple tabs, wrong one active) — this reads
   `workbook.SheetNames[0]` unconditionally. If this ever becomes a problem
   in practice, revisit; not handling multi-sheet files deliberately for
   this first version, per the "one file, one order" scope.

---

## Part 2 — Backend: the MO-existence check

### New file: `app/logistics/routes/check_mo.py`

```python
from fastapi import Request, HTTPException
from sqlalchemy import select
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_ADD_LOGISTICS
from app.database import SessionLocal
from app.logistics.models import LogisticsConsignment
from app.logistics.routes.router import router
import logging

logger = logging.getLogger(__name__)


#-----------------------------------------------------
# MO DUPLICATE CHECK — for the Step 1 Excel import feature only.
#
# "An order with this MO already exists" is being treated as a straight
# duplicate right now, because there is no real batching on the backend yet
# (mo_no is a nullable, non-unique grouping key with no batch concept behind
# it in this schema — see the comment on mo_no in models.py). ONE MO CURRENTLY
# MEANS ONE ORDER, BY CONVENTION, NOT BY CONSTRAINT.
#
# WHEN REAL BATCHING IS DESIGNED, THIS CHECK MUST CHANGE. At that point an
# existing MO will mean "this is batch 2" (a valid, expected case), not
# "duplicate" — this endpoint's meaning will need to be redefined (e.g. keyed
# on MO + batch number, or a content hash of the imported file) exactly the
# way imports' ConsignmentBatchGroup/ConsignmentOrderItem split handled the
# same shift. Do not carry this endpoint's current behavior forward
# unexamined once batching exists.
#-----------------------------------------------------

@router.get("/check-mo")
def check_mo(request: Request, mo_no: str):
    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_ADD_LOGISTICS, db)

        mo_no = mo_no.strip()
        if not mo_no:
            raise HTTPException(status_code=422, detail="mo_no is required")

        exists = db.execute(
            select(LogisticsConsignment.id)
            .where(LogisticsConsignment.mo_no == mo_no)
            .where(LogisticsConsignment.is_deleted == False)
            .limit(1)
        ).first() is not None

        return {"status_code": 200, "detail": "MO checked", "data": {"exists": exists}}

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        logger.exception("Unhandled error in app.logistics.routes.check_mo")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()
```

Register it in `app/logistics/routes/__init__.py` alongside the other route
imports (same pattern as every other route file in this module).

### Edge cases

1. **Case sensitivity / whitespace on `mo_no`.** The sample file's MO is
   lowercase (`mo-1000091-1`) — confirm whether MO comparison should be
   case-sensitive or not. I've written the check as an exact match after
   trimming only. If MOs are ever entered inconsistently in case
   (`MO-1000091-1` vs `mo-1000091-1`) elsewhere in the app, this check would
   miss a real duplicate — worth confirming whether MO values are
   normalized to a consistent case anywhere else in the system (e.g. on
   manual entry) before deciding whether to add `func.lower()` on both
   sides here.
2. **Soft-deleted orders.** `is_deleted == False` means a previously
   *deleted* order under this MO does **not** block a re-import — confirm
   this is the desired behavior (I'd assume yes: a deleted order isn't a
   "real" existing order anymore) rather than assumed without checking.
3. **This is a `GET` with a query param, not a `POST`.** It's a read-only
   check with no side effects, so `GET /logistics/check-mo?mo_no=...` is the
   right verb — don't make this a `POST` out of habit matching the other
   mutation routes in this file.
4. **Permission: `CAN_ADD_LOGISTICS`, not `CAN_VIEW_LOGISTICS`.** This check
   only matters to someone who's about to create an order, so it's gated on
   the *create* permission, consistent with `create_consignment.py`.

---

## Part 3 — Wiring it into Step 1

### Draft schema addition (`schema.ts`)

Add one internal-only, UI-state field to the draft — never referenced by
`draftToPayload` in `logisticsMap.ts`, so it never reaches the backend:

```typescript
// UI-only: true once a file has been successfully imported this session.
// NOT sent to the backend — see draftToPayload, which deliberately does not
// reference this field.
importedFromExcel: z.boolean().optional().default(false),
```

This lives in the same `useForm` instance the whole wizard shares
(`LogisticsStatusWizard.tsx`'s single `FormProvider`), so it persists
correctly if the user navigates to Step 2 and back to Step 1 — it does not
need a separate context or a manually-lifted piece of state.

### The import control in `Step1Order.tsx`

```tsx
const importedFromExcel = useWatch({ control, name: 'importedFromExcel' })
const [importState, setImportState] = useState<'idle' | 'loading' | 'error'>('idle')
const [importError, setImportError] = useState<string | null>(null)
const { replace: replaceItems } = useFieldArray({ control, name: 'items' })

async function handleFileSelected(file: File) {
  setImportState('loading')
  setImportError(null)
  try {
    const parsed = await parseLogisticsImportFile(file)

    const { data } = await apiFetch<{ data: { exists: boolean } }>(
      `/logistics/check-mo?mo_no=${encodeURIComponent(parsed.moNo)}`
    )
    if (data.exists) {
      setImportError(`MO ${parsed.moNo} already has an order — this looks like a duplicate file.`)
      setImportState('idle')   // re-enable — nothing was imported
      return
    }

    setValue('moNo', parsed.moNo)
    if (parsed.orderType) setValue('orderType', parsed.orderType as LogisticsDraft['orderType'])
    if (parsed.department) setValue('department', parsed.department as LogisticsDraft['department'])
    if (parsed.shipmentMode) setValue('shipmentMode', parsed.shipmentMode as LogisticsDraft['shipmentMode'])
    if (parsed.customerName) setValue('customerName', parsed.customerName)
    if (parsed.mill) setValue('mill', parsed.mill)
    if (parsed.originCountry) setValue('originCountry', parsed.originCountry)
    replaceItems(parsed.items.map((item, i) => ({
      ...emptyItem(`item-${Date.now()}-${i}`),
      jobNo: item.jobNo ?? '',
      itemDetail: item.itemDetail ?? '',
      quantity: item.quantity ?? undefined,
      unitWeight: item.unitWeight ?? undefined,
      plannedRfdDate: item.plannedRfdDate ?? '',
      actualRfdDate: item.actualRfdDate ?? '',
      // budgetedPackingCost intentionally left at emptyItem's default —
      // manual entry, per the file format (not present in the import).
    })))

    setValue('importedFromExcel', true)   // permanently disables the control below
    if (parsed.warnings.length > 0) setImportError(parsed.warnings.join(' '))
    setImportState('idle')
  } catch (err) {
    setImportError(err instanceof ExcelImportError ? err.message : 'Could not read this file.')
    setImportState('idle')   // re-enable — nothing was imported, this was a parse failure
  }
}
```

```tsx
<div className="flex items-center gap-3">
  <input
    type="file"
    accept=".xlsx,.xls"
    id="logistics-import-file"
    className="hidden"
    disabled={importState === 'loading' || importedFromExcel}
    onChange={(e) => {
      const file = e.target.files?.[0]
      e.target.value = ''   // allow re-selecting the same filename after an error
      if (file) handleFileSelected(file)
    }}
  />
  <label
    htmlFor="logistics-import-file"
    className={`rounded-lg border border-line px-3 py-1.5 text-xs ${
      importState === 'loading' || importedFromExcel
        ? 'cursor-not-allowed opacity-50'
        : 'cursor-pointer hover:border-muted'
    }`}
  >
    {importState === 'loading' ? 'Reading file…' : importedFromExcel ? 'Imported' : 'Import file'}
  </label>
  {importError && <p className="text-xs text-risk">{importError}</p>}
</div>
```

### Edge cases

1. **`e.target.value = ''` after every selection** — without this, selecting
   the *same* filename twice in a row (e.g. retrying after fixing a rejected
   file, but the corrected file happens to have the same name) doesn't fire
   `onChange` at all, since the browser sees no change in the input's value.
   This is a real, common gotcha with file inputs — must be present.
2. **`importedFromExcel` is checked via the shared form state, not local
   component state** — confirm this actually survives a Step 1 → Step 2 →
   Step 1 round trip in the wizard (it should, since the `FormProvider`
   instance is shared) by testing it directly, not just reasoning about it.
3. **Warnings vs. hard errors share one `importError` state slot** — a
   warning (unmatched enum value) still lets the import succeed and the
   control still disables, but the message area is reused for both. Confirm
   this doesn't confuse "the import failed" with "the import succeeded with
   caveats" — consider visually distinguishing them (e.g. different color/
   icon) if this reads ambiguously in practice.
4. **`replaceItems` fully replaces the item array** — if the user had
   already manually added items before importing (unlikely given the button
   is presumably used first, but not enforced), those manually-entered items
   are discarded. Confirm this is acceptable — it follows from "one file
   describes the whole order's items," but is worth being explicit about
   rather than assumed to be obviously fine.
5. **Numeric fields (`quantity`, `unitWeight`) set to `undefined` when
   blank**, not `0` or `null` — confirm this matches whatever the manual-entry
   form already does for an empty number input (react-hook-form typically
   treats an empty number input as `undefined` or `NaN` depending on
   register options; match whatever `emptyItem()` already produces for a
   never-touched item, don't introduce a new blank-representation
   convention).
6. **The file's own disposal** — nothing further is needed here beyond not
   retaining a reference to `file` past `handleFileSelected`'s own scope,
   which the code above already does (no state variable holds onto `File`).
   Confirm no other code path (e.g. a debug log, a Sentry breadcrumb) ends up
   holding a reference to the raw file or its parsed byte buffer longer than
   necessary.

---

## Testing / validation

1. **Parser unit tests** against the actual sample file (and copies of it
   with deliberate defects): blank MO on row 1 (must fail), a later row with
   a different non-blank MO (must fail with the specific error message), a
   trailing-space header exactly as in the real file (must still parse), an
   unrecognized Department value (must warn, not fail, and leave that field
   blank), a blank Quantity/Unit Weight cell (must parse as blank, not fail
   or default to 0), a Planned/Actual RFD date cell (must come through as a
   correct `YYYY-MM-DD` string, verified against the exact dates in the
   sample: `2025-02-10`, `2026-04-15`, etc.).
2. **`check-mo` endpoint tested directly**: existing non-deleted MO → `exists:
   true`; existing but soft-deleted MO → `exists: false`; unknown MO →
   `exists: false`; missing `mo_no` param → 422; without `CAN_ADD_LOGISTICS`
   → 403 (or whatever this app's authorize() returns for a missing
   permission — match the existing convention).
3. **End-to-end**: import the real sample file into a fresh wizard session,
   confirm every field lands exactly where expected, confirm
   `budgetedPackingCost` and `totalPackages` are untouched (still blank, per
   the format), confirm the import control disables afterward, confirm all
   fields remain editable, confirm submitting the order afterward doesn't
   send `importedFromExcel` to the backend (check the actual network request
   payload).
4. **Re-import the same file into a second, brand-new wizard session** —
   confirm the `check-mo` call now returns `exists: true` and the second
   import is rejected with the file input re-enabled, not stuck disabled.
5. **Multi-tab / session note**: this feature has no interaction with the
   idle-timeout or dashboard-performance work done earlier — no shared code
   paths — no cross-feature regression risk expected, but worth a quick
   smoke test of Step 1 generally after this ships, given how many other
   changes have landed in this codebase recently.

---

## Definition of done

- [ ] `excelImport.ts` created, matches the exact column set and forward-fill
      behavior confirmed against the real sample file.
- [ ] `cellDates: true` present in the `XLSX.read` call — verified dates
      parse correctly, not silently dropped.
- [ ] Blank-MO-on-first-row and mismatched-later-MO both produce clear,
      specific error messages, not generic failures.
- [ ] `check-mo` endpoint added, gated on `CAN_ADD_LOGISTICS`, with the
      "revisit when batching exists" comment in place.
- [ ] `importedFromExcel` field added to the draft schema, confirmed absent
      from the actual network payload on submit.
- [ ] Import control: loading state while parsing/checking, re-enables on
      any failure (parse error or duplicate), permanently disables only on
      success.
- [ ] File input's `value` reset after every selection (same-filename
      re-select works).
- [ ] All fields populated by import remain fully editable afterward.
- [ ] Manual entry (no import at all) continues to work completely
      unchanged — this feature adds a path, it doesn't alter the existing
      one.
- [ ] Real sample file imports end-to-end correctly, verified field-by-field
      against its actual contents.
