/**
 * Change-history types shared by all three status modules
 * (Imports / Logistics / Trucking), plus the mock engine the two that are not
 * yet wired still run on.
 *
 * IMPORTS IS WIRED to the real endpoints
 * (GET /consignments/change-history/{id}, PUT /consignments/revert-update/{id}/{hid});
 * see lib/api/importsChangeHistoryMap.ts for the mapper, which is the worked
 * example logistics/trucking should follow. The translation it performs:
 *
 *   backend `history.fields`            -> entry.sections[].fields
 *   backend `history.items` (updated)   -> entry.collections[].updated
 *   backend `history.new_items`         -> entry.collections[].added
 *   backend `history.deleted_items`     -> entry.collections[].removed
 *   is_reverted / reverted_by / reverted_at / is_revert -> same names, camelCased
 *
 * LOGISTICS AND TRUCKING are still mock: buildMockHistory below, fed by
 * lib/{logistics,trucking}ChangeHistory.ts. Those endpoints already exist and
 * mirror imports one-for-one, so wiring them is a mapper swap, not a redesign.
 */

export interface FieldDiff {
  field: string
  label: string
  oldValue: string
  newValue: string
}

export interface HistorySection {
  key: string
  label: string
  fields: FieldDiff[]
}

/** One line-item (item/package/vehicle/payment/...) that existed before AND
 *  after this change, with only the fields that actually differ. */
export interface ChildDiffRow {
  id: string
  label: string
  changes: FieldDiff[]
}

/** A line-item this change added or removed — shown as a one-line summary,
 *  not a field-by-field diff (there's nothing to diff against). */
export interface ChildSummaryRow {
  id: string
  label: string
  summary: string
}

export interface ChildCollectionDiff {
  key: string
  label: string
  updated: ChildDiffRow[]
  added: ChildSummaryRow[]
  removed: ChildSummaryRow[]
}

export interface ChangeHistoryEntry {
  id: string
  recordId: string
  changeType: 'Update' | 'Delete'
  changedBy: string
  changedById: string
  changedAt: string // ISO datetime
  isReverted: boolean
  revertedBy?: string
  revertedAt?: string
  /** True when this row IS the result of a revert action (a "put it back"
   *  entry), as opposed to an original edit. */
  isRevert: boolean
  sections: HistorySection[]
  collections: ChildCollectionDiff[]
}

/** Whether *anything* changed in this entry — an entry with only reverted
 *  fields filtered out could otherwise render an empty card. */
export function hasVisibleChanges(entry: ChangeHistoryEntry): boolean {
  return (
    entry.sections.some((s) => s.fields.length > 0) ||
    entry.collections.some((c) => c.updated.length || c.added.length || c.removed.length)
  )
}

/**
 * The backend's own rule: undo is strictly last-in-first-out. Only the single
 * newest, not-yet-reverted entry for a record may be reverted; reverting any
 * other one 400s server-side. Mirrored here so the mock UI never offers a
 * button that (once wired) would fail.
 *
 * Only sound over the WHOLE list. The wired imports screen is paginated, so it
 * asks the backend which entry is revertable instead of using this — the
 * newest active entry can sit on a later page when everything on this one has
 * been reverted.
 */
export function isRevertable(entries: ChangeHistoryEntry[], entry: ChangeHistoryEntry): boolean {
  if (entry.isReverted) return false
  const newestActive = entries.find((e) => !e.isReverted)
  return newestActive?.id === entry.id
}

//-----------------------------------------------------
// SEEDED RNG — same tiny generator used by lib/importsStatusData.ts, so the
// mock history is deterministic across reloads without any external deps.
//-----------------------------------------------------

export function mulberry32(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Turn a string id into a stable numeric seed, so "the same record always
 *  generates the same history" without a lookup table. */
export function seedFrom(text: string): number {
  let h = 0
  for (let i = 0; i < text.length; i++) h = (Math.imul(h, 31) + text.charCodeAt(i)) | 0
  return h || 1
}

const STAFF = ['A. Rehman', 'S. Fatima', 'M. Tariq', 'H. Baig', 'N. Qureshi'] as const

export interface FieldSpec {
  key: string
  label: string
  kind: 'text' | 'date' | 'number' | 'money'
  /** For 'text' fields drawn from a fixed vocabulary (status, instrument, ...). */
  options?: readonly string[]
}

export interface SectionSpec {
  key: string
  label: string
  fields: FieldSpec[]
}

export interface CollectionSpec {
  key: string
  label: string
  /** How one row is identified in the summary line, e.g. "Item 2". */
  rowNoun: string
  fields: FieldSpec[]
}

function randomValue(rng: () => number, spec: FieldSpec): string {
  if (spec.kind === 'date') {
    const base = new Date('2026-01-01').getTime()
    const d = new Date(base + Math.floor(rng() * 200) * 86_400_000)
    return d.toISOString().slice(0, 10)
  }
  if (spec.kind === 'number') return String(Math.floor(rng() * 500) + 1)
  if (spec.kind === 'money') return String(Math.floor(rng() * 50_000) + 500)
  if (spec.options?.length) return spec.options[Math.floor(rng() * spec.options.length)]
  return `Value ${Math.floor(rng() * 900) + 100}`
}

/** One {old,new} pair for a field — guaranteed different, since a "change" to
 *  the same value isn't a change. */
function randomFieldDiff(rng: () => number, spec: FieldSpec): FieldDiff {
  let oldValue = randomValue(rng, spec)
  let newValue = randomValue(rng, spec)
  let guard = 0
  while (newValue === oldValue && guard++ < 5) newValue = randomValue(rng, spec)
  return { field: spec.key, label: spec.label, oldValue, newValue }
}

/**
 * Builds a deterministic list of mock change-history entries for one record,
 * newest first (matching how the real endpoint orders them). `sections` and
 * `collections` describe the field vocabulary for one module (imports /
 * logistics / trucking); each call picks a random subset per entry so no two
 * entries look identical.
 */
export function buildMockHistory(
  recordId: string,
  sections: SectionSpec[],
  collections: CollectionSpec[],
): ChangeHistoryEntry[] {
  const rng = mulberry32(seedFrom(recordId))
  const entryCount = Math.floor(rng() * 5) // 0–4 entries; many records have none

  const entries: ChangeHistoryEntry[] = []
  let cursor = new Date('2026-08-01T09:00:00Z').getTime() - entryCount * 3 * 86_400_000

  for (let i = 0; i < entryCount; i++) {
    cursor += Math.floor(rng() * 3 + 1) * 86_400_000
    const changedBy = STAFF[Math.floor(rng() * STAFF.length)]

    const entrySections: HistorySection[] = sections.map((s) => {
      const touched = s.fields.filter(() => rng() < 0.35)
      return { key: s.key, label: s.label, fields: touched.map((f) => randomFieldDiff(rng, f)) }
    })

    const entryCollections: ChildCollectionDiff[] = collections.map((c) => {
      const updated: ChildDiffRow[] = []
      const added: ChildSummaryRow[] = []
      const removed: ChildSummaryRow[] = []

      // At most one row touched per collection per entry — keeps the mock
      // readable rather than rewriting the whole item table every time.
      const roll = rng()
      if (roll < 0.18) {
        const rowLabel = `${c.rowNoun} ${Math.floor(rng() * 3) + 1}`
        const touched = c.fields.filter(() => rng() < 0.5)
        if (touched.length) {
          updated.push({
            id: `${recordId}-${c.key}-${i}`,
            label: rowLabel,
            changes: touched.map((f) => randomFieldDiff(rng, f)),
          })
        }
      } else if (roll < 0.26) {
        added.push({
          id: `${recordId}-${c.key}-add-${i}`,
          label: `${c.rowNoun} ${Math.floor(rng() * 3) + 3}`,
          summary: randomValue(rng, c.fields[0]),
        })
      } else if (roll < 0.32) {
        removed.push({
          id: `${recordId}-${c.key}-rm-${i}`,
          label: `${c.rowNoun} ${Math.floor(rng() * 3) + 1}`,
          summary: randomValue(rng, c.fields[0]),
        })
      }

      return { key: c.key, label: c.label, updated, added, removed }
    })

    entries.push({
      id: `${recordId}-h${i}`,
      recordId,
      changeType: 'Update',
      changedBy,
      changedById: changedBy,
      changedAt: new Date(cursor).toISOString(),
      isReverted: false,
      isRevert: false,
      sections: entrySections,
      collections: entryCollections,
    })
  }

  // Only entries that actually changed something are worth showing.
  const withChanges = entries.filter(hasVisibleChanges)

  // Seed a plausible revert: at most one, never the newest (mirrors the real
  // rule — the newest is always the revertable one, not one already reverted).
  if (withChanges.length > 1 && rng() < 0.3) {
    const idx = 1 + Math.floor(rng() * (withChanges.length - 1))
    const target = withChanges[idx]
    target.isReverted = true
    target.revertedBy = STAFF[Math.floor(rng() * STAFF.length)]
    target.revertedAt = new Date(+new Date(target.changedAt) + 86_400_000).toISOString()
  }

  // Newest first, matching fetch_all_consignment_history's ordering.
  return withChanges.slice().reverse()
}
