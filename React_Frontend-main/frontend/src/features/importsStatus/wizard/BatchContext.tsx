import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { getBatches, getConsignment, type ApiConsignment, type ApiAllocationLine } from '@/lib/api/imports'

/**
 * What this consignment's ORDER looks like, for the steps that have to show
 * more than one batch.
 *
 * WHY A CONTEXT AND NOT PROPS. Step 3 needs the allocation and the siblings,
 * Steps 1/2 need the freeze state and whether this is the founding batch, and
 * the wizard header needs the sequence. Threading five values through
 * `WIZARD_STEPS` render props would put batching into the signature of every
 * step including the four that do not care.
 *
 * WHY IT FETCHES SIBLINGS ITSELF rather than taking them from the wizard's
 * record: the detail payload deliberately carries no siblings block (design
 * §3.7b — it would duplicate a list row's shape in a second place and go stale
 * against it). The allocation and the freeze DO come from the record, because
 * they are facts about this consignment's own order that the detail already
 * publishes.
 *
 * EVERYTHING HERE IS READ-ONLY. Creating a batch goes through
 * `createBatchApi`; this context is told to `refresh()` afterwards rather than
 * mutating a local copy, because the numbering of EVERY sibling can change on
 * a split and a locally-patched copy would show the old numbers.
 */

export interface BatchState {
  /** Per order line: what was bought, what every batch has taken, what is left.
   *  Empty until the record loads, and on a brand-new consignment. */
  allocation: ApiAllocationLine[]
  /** Every live batch of this order, itself included, in sequence order. */
  batches: ApiConsignment[]
  /** This batch's place in the order. 1 = the founding batch. */
  batchSequence: number | null
  /** True when the order holds more than one live batch. The wizard hides the
   *  order-level fields on a later batch from this, NOT from the freeze —
   *  those are different rules: shared fields are entered once on batch 1
   *  (requirements), the freeze only bites once a batch has CLOSED. */
  isSplit: boolean
  isFoundingBatch: boolean
  /** The order's freeze, straight off the detail payload. `hard` and `admin`
   *  are PAYLOAD KEYS, so a step can match them to its own inputs. */
  groupFrozen: {
    is_frozen: boolean
    frozen_by: { consignment_id: number; consignment_number: string | null } | null
    hard: string[]
    admin: string[]
  } | null
  loading: boolean
  refresh: () => void
}

const EMPTY: BatchState = {
  allocation: [], batches: [], batchSequence: null,
  isSplit: false, isFoundingBatch: true, groupFrozen: null,
  loading: false, refresh: () => {},
}

const BatchCtx = createContext<BatchState>(EMPTY)

export function BatchProvider(
  { record, reloadKey = 0, children }:
  { record: ApiConsignment | null; reloadKey?: number; children: ReactNode },
) {
  const [batches, setBatches] = useState<ApiConsignment[]>([])
  const [loading, setLoading] = useState(false)
  const id = record?.id ?? null

  // THE ALLOCATION IS RE-FETCHED, NOT TAKEN FROM THE PROP.
  //
  // It used to read `record.allocation` straight through, and creating a batch
  // then left the table showing the OLD outstanding quantity: `refresh()`
  // re-fetched the siblings but the allocation still came from the record the
  // wizard had loaded before the split. Measured in the browser - the database
  // said allocated 15040 / outstanding 0, and the screen said 40 outstanding,
  // with nothing to say which was right.
  //
  // Seeded from the prop so the first paint needs no extra round trip, then
  // owned here. It deliberately does NOT reload the wizard's form: re-running
  // `apiToDraft` would reset fields the operator has typed, and creating a
  // batch is not a reason to discard their route.
  const [detail, setDetail] = useState<ApiConsignment | null>(record)
  useEffect(() => { setDetail(record) }, [record])

  const refresh = useCallback(() => {
    if (id == null) { setBatches([]); return }
    setLoading(true)
    Promise.all([
      getBatches(id).catch(() => [] as ApiConsignment[]),
      // A failure here must not break the step - the route and schedule below
      // are the work, the allocation panel is context.
      getConsignment(id).catch(() => null),
    ])
      .then(([sibs, fresh]) => {
        setBatches(sibs)
        if (fresh) setDetail(fresh)
      })
      .finally(() => setLoading(false))
  }, [id])

  // REFRESHED AFTER EVERY SAVE, not only on mount.
  //
  // The allocation table shows SERVER state - ordered, allocated, outstanding -
  // and a save is what moves it. Without this, changing how much of an order
  // goes into this batch and pressing save left the table showing the figures
  // from before the save, which is the same stale-screen defect that shipped
  // and had to be fixed for the split. The wizard bumps `reloadKey`; the
  // provider has no way to observe a save otherwise, because it renders INSIDE
  // the component that performs one.
  useEffect(() => { refresh() }, [refresh, reloadKey])

  const live = batches.filter((b) => !b.is_deleted)

  return (
    <BatchCtx.Provider value={{
      allocation: detail?.allocation ?? [],
      batches: live,
      batchSequence: detail?.batch_sequence ?? null,
      // FROM THE FETCHED SIBLINGS, not from `batches_ever`. The two differ
      // after a delete — `batches_ever` never decrements, because the NUMBERS
      // are permanent (§3.5a/A3) — and what these screens ask is "how many
      // batches are there now", which is a different question from "how many
      // numbers have ever been issued".
      isSplit: live.length > 1,
      isFoundingBatch: (detail?.batch_sequence ?? 1) === 1,
      groupFrozen: detail?.group_frozen ?? null,
      loading,
      refresh,
    }}>
      {children}
    </BatchCtx.Provider>
  )
}

export function useBatchContext() {
  return useContext(BatchCtx)
}

/**
 * Is this payload key locked for this user right now, and why?
 *
 * THE TIER LISTS COME FROM THE SERVER — `group_frozen.hard` and `.admin` are
 * published as payload keys precisely so the front end never restates which
 * fields are in which tier. One rule, one place: if a field moves tier, this
 * code does not change.
 */
export function frozenReason(
  state: BatchState, key: string, isAdmin: boolean,
): string | null {
  const gf = state.groupFrozen
  if (!gf?.is_frozen) return null

  const where = gf.frozen_by?.consignment_number
    ? `batch ${gf.frozen_by.consignment_number} has arrived at works`
    : 'a batch on this order has arrived at works'

  if (gf.hard.includes(key)) {
    return `Settled — ${where}. Money has moved against it, so nobody can change it, including an admin.`
  }
  if (gf.admin.includes(key) && !isAdmin) {
    return `Settled — ${where}. An admin can still correct it.`
  }
  return null
}
