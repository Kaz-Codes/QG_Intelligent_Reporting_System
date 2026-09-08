# Imports batching — design

**Status: proposal. Nothing in this document is built.** No code, migration or
scaffold was written for it. Approve, reject or amend it and I will implement
from it.

---

## Changelog — revision 2

Amended against `docs/imports-batching-requirements.md`, now written to disk,
and against your six follow-up points.

| What moved | Why |
|---|---|
| **§0.1 rewritten** | The requirements file now exists. Its Open Items A are reconciled against your decisions table in §0.3. |
| **§0.3 new** | A1/A2/A6/A7/A8 are answered and consistent. **A3 is answered in a way that contradicts its own stated instinct** — see §3.5. A4 is changed materially by the requirements body. |
| **§0.4 new** | The requirements introduce a **consignment number (`177`) that is not the payment reference (`lc6222`)**. Revision 1 conflated them. This is the largest single correction here and it moves §3.4, §4.1 and §4.3. |
| **§3.1 restated** | The `(source, source_ref)` dedupe argument is **withdrawn** — you are right that keying it to the batch id dissolves it. The conclusion survives on the remaining grounds; §3.1 now argues those. |
| **§3.3 resolved** | Revision 1 asked which fields are LC-level. The requirements settle it, and the list is longer than my four. §3.8 answers your "stored on the group vs entered once on batch 1" distinction, which are not the same decision. |
| **§3.4 rewritten** | Consignment number vs payment reference (§0.4), and the `mode + number` display form. |
| **§3.5 reversed** | I now recommend **permanent suffixes**, not `RANK()` renumbering. Your A3 instinct was right and the decisions table is wrong for the reason you name. Case against, and the cost, both stated. Your call. |
| **§3.7 new** | **The item allocation model** — the gap you identified. Order-item table, the per-order vs per-batch field split, and the effect on `recompute_derived()`, `apply_item_master_values()` and `_import_snapshot()`. |
| **§4 rewritten** | The migration now implements the sharing §3.3 argues for, including `payments`. Revision 1's design and migration genuinely disagreed; you caught it. §4.6 also **withdraws revision 1's reversibility claim**, which was true of the additive migration and is not true of this one. |
| **§6 Q1 amended** | The requirements ask for a **per-item basis checkbox**, so both formulas coexist. Revision 1 framed it as "pick one". My recommendation to add a separate per-unit weight field stands and is now confirmed by the requirements. |
| **§6 B3, B4 new** | Both answered. B3 plainly: a plain CHECK constraint cannot express it, and I say what does instead. |
| **§7 re-ranked** | Three new entries: the fields moving two levels down, the trucking snapshot's meaning change, and the hand-written downgrade. |
| **§8 replaced** | Four of revision 1's seven questions are answered by the requirements. Three new ones take their place. |

Nothing from revision 1 was dropped because it was inconvenient; where an
argument is withdrawn (§3.1) or a claim corrected (§4.6) it is marked as such
rather than quietly removed.

---

## 0. Read first

### 0.1 The requirements file now exists

At revision 1 it did not — there was no `docs/` directory and nothing in the
repository mentioned batching. It is now at
`docs/imports-batching-requirements.md`, verbatim from your message. It is the
document of record; where this design and that file disagree, that file wins
unless I have explicitly argued otherwise and marked it.

Its final section, "Prompt to use with this document", is historical and
superseded. Stored, ignored.

### 0.2 Operators are already batching, in a free-text field

`consignment_items.batch_no` is not empty and is not noise:

| | |
|---|---|
| Item lines total | 455 |
| Lines with a non-blank `batch_no` | 59 |
| Distinct values | 4 — `B1`, `B2`, `B3`, `B4` |
| Consignments carrying more than one distinct value | **15** |

Fifteen consignments already record two or more batches, in a per-item text
column, because the schema gave them nowhere else to put it. That is the
feature you are asking for, being done by hand.

This bears on your finding 6 and on the migration; positions in §3.6 and §4.5.

### 0.3 Open Items A, reconciled against your decisions table

Per your instruction the decisions table wins. Where they disagree, I say so.

| | Requirements file asks | Decisions table says | Verdict |
|---|---|---|---|
| **A1** | Does a suffix ever appear with one batch? | Stays `177`, no suffix, ever | **Agree.** The requirements body says the same. Settled. |
| **A2** | Does `177-2` exist immediately? | Exists the moment `177-1` is created | **Agree.** Settled. §3.7 says what it holds. |
| **A3** | *"My instinct is that numbers should stay fixed once assigned, since they appear in emails and documents"* | Remaining batches **renumber ascending** | **CONFLICT.** The table wins by your rule, but your own A3 instinct is the correct one, for exactly the reason your Step 4 raises. I recommend reversing the table — §3.5. |
| **A4** | Unit price per what? | *(not covered)* | **Open**, and narrowed by the requirements body — §6 Q1, §8 question 2. |
| **A5** | What is "required vs ETA"? | *(not covered)* | **Answered** — two implementations, finding 4 and §6 Q2. |
| **A6** | Is a locked earlier batch permanently read-only? | Display state only; editable from its own screen | **Agree.** Settled. |
| **A7** | Do job / MO / reference numbers exist? | Already exist; surface only | **Agree, and confirmed in code** — all three are columns on `ConsignmentItem`. They move to the order-item row under §3.7. |
| **A8** | Which country list? | ISO 3166 | **Agree.** Settled. |

One real conflict (A3), one genuinely open business question (A4).

### 0.4 The consignment number is not the payment reference

This is the correction I most want you to check, because revision 1 got it wrong
and everything downstream of it moved.

The requirements numbering table has **two columns**:

| Situation | Consignment number | Payment reference |
|---|---|---|
| One batch | `177` | `lc6222` |
| Two batches | `177-1`, `177-2` | `lc6222` on both |

`177` and `lc6222` are different values. Revision 1 assumed the suffix hung off
`consignment_reference()` — which returns `instrument_number or IMP-{id}` —
producing `lc6222-1`. That is not what is being asked for.

**Three consequences:**

1. **A consignment number has to be introduced.** There is no such column today
   (finding 1), and it is not the LC number.
2. **The payment reference display changes independently.** The requirements
   want **mode + number concatenated** — `lc6222`, and in the list `lc-78889`.
   That is a change to `consignment_reference()` on its own merits, batching or
   not.
3. **"Existing displayed numbers must not change" needs re-reading.** Today the
   list shows `instrument_number or IMP-{id}` — it shows *no* consignment
   number. Introducing `177` gives every existing consignment a number it has
   never had, which is a change by any reading.

**I have not resolved 3, because I cannot tell what `177` is.** With 183 rows in
the table it reads like an ordinal or a database id. It is either (a) the
existing `consignments.id`, in which case nothing changes and the migration is
free; (b) a new sequential number per group, in which case 183 rows get numbers
they did not have; or (c) a number the business already uses on paper that the
system has never held, in which case it must be keyed in and back-filled by
hand.

The two documents genuinely do not settle this and I am not guessing at it.
§8 question 1.

---

## 1. How consignments are structured today

### 1.1 Models — `app/imports/models.py`

**`Consignment` (header).** One row per payment reference:

- *Identity and parties* — `id` (PK, and the only identifier there is),
  `branch_id`, `supplier_id`, `works` (free text), `clearing_agent_id`,
  `origin`, `currency`, `consignment_type`, `incoterm`
- *Demand dates* — `po_date`, `requisition_date`, `required_date`
- *Shipping* — `mode_of_shipment`, `cargo_readiness_date`, `etd`, `eta`,
  `eta_works`, `loading_port_id`, `delivery_port_id`
- *Payment* — `payment_instrument`, `instrument_number`,
  `opening_or_retirement_date`
- *Money* — `exchange_rate`, `rate_booked_on`, `rate_source`, and the two
  **stored** derived totals `foreign_total`, `pkr_total`
- *Status* — `current_status`, `effective_date`, `remarks`
- *Clearance* — `gd_number`, `gd_filing_date`, `free_days_allowed`,
  `gate_out_date`, `demurrage_or_detention_paid`, `container_detention`
- *Hand-off* — `sent_to_logistics_at`, `sent_to_trucking_at`
- *State* — `record_state`, `is_locked`, `is_deleted`, `deleted_at`,
  `deleted_by_id`, `created_by_id`

**There is no consignment-number column.** Finding 1 confirmed, and per §0.4
more consequential than revision 1 treated it.

**`ConsignmentItem` (line).** `id`, `consignment_id`, item identity (`item_id`,
`item_code`, `item_name`, `placeholder_name`, `specification`, `hs_code`),
commercial fields (`quantity`, `unit_price`, `unit_of_measurement`),
`eta_works`, `batch_no`, `requisition_type` plus its conditional fields
(`reference_number`, `job_number`, `mo_number`, `description`), physical fields
(`net_weight`, `gross_weight`, `length`, `width`, `height`), landed cost (`elc`,
`alc`, four audit columns, `variance_absolute`, `variance_percentage`),
`is_deleted` / `deleted_at`.

**`Payment`** — `id`, `consignment_id`, `retirement_date`, `value`,
`payment_exchange_rate`, `bank_charges`, `status`, `bank_reference`,
`is_deleted`, `deleted_at`. **There is exactly one payment row in the entire
database**, against one consignment. That number decides how cheap the payments
migration is (§4.4).

`EtaRevisionHistory`, `StatusUpdateHistory` and `ConsignmentChangeHistory` are
the three history tables.

### 1.2 The three state flags, and how they interact

| Flag | Set by | Cleared by | Effect |
|---|---|---|---|
| `record_state` (`draft` / `submitted`) | `POST /{id}/submit`, only if `submission_errors()` is empty | never (one-way) | Gates nothing by itself |
| `is_locked` | the update route, when status reaches `Arrived at Works` | `POST /{id}/reopen`, **admin only** | update/submit return **423** |
| `is_deleted` | `DELETE /{id}` | `POST /undo-delete/{id}` | Hidden from lists unless `include_deleted` |

The closed test is **two-part**, `app/imports/helpers.py:739`:

```python
def is_closed(consignment):
    return (consignment.current_status == Status.ARRIVED_AT_WORKS.value
            and consignment.record_state == "submitted")
```

A draft may sit at "Arrived at Works" and remain editable. Submitting never
locks; only closing does.

**Live distribution (179 live consignments, 4 soft-deleted):**

| | |
|---|---|
| `record_state = submitted` | 148 |
| `record_state = draft` | 31 |
| `is_locked = true` | **142** |

**142 of 179 — 79% — are locked.** That number decides how batching has to
behave; it recurs in §3.5, §3.8 and §7.

### 1.3 A latent bug worth surfacing now

`submission_errors()` requires `works`. **`works` is NULL on all 179 live
consignments** — the two non-null values are on soft-deleted rows.

Yet 148 of 179 are `submitted`, because the loader wrote `record_state` at the
database level and the submit route never ran on them. **The consequence: not
one loaded consignment can be re-submitted through the app today.** Reopen a
locked consignment, edit it, submit, and you get "Works is required" on a field
the UI barely surfaces and the data has never held.

Pre-existing, not caused by batching, but batching multiplies it — every new
batch inherits the requirement. The requirements' "Works becomes a dropdown
populated from branches" fixes it as a side effect, provided the backfill in
§7 item 8 ships with it.

### 1.4 Serializers, helpers, routes

`serializers.py` emits plain dicts, generates `system_remarks` from ETA and
status history at read time, and calls `submission_errors()` on **every read**
to fill `missing_fields` (`serializers.py:135`, via `_submission_errors` at
`:69–74`). That detail is the structural answer to B4 — §6.

`helpers.py` holds the logic. The pieces batching touches:

- `consignment_reference()` (`:913`) — the canonical display identity,
  `instrument_number or f"IMP-{id}"`
- `fetch_consignments_page()` (`:156`) — the list query and its filters
- `recompute_derived()` (`:862`), `apply_item_master_values()` (`:818`)
- `submission_errors()` (`:917`), `is_closed()` (`:739`)
- The diff machinery: `updated_fields` (`:370`), `new_items_to_add` (`:399`),
  `delete_missing` (`:430`), `updated_items` (`:452`),
  `add_in_consignment_change_history` (`:544`), `revert` (`:648`),
  `revert_local_fields` (`:680`), `add_or_delete` (`:689`),
  `revert_old_values` (`:709`)

Routes are one file per endpoint, self-registering on a shared router.

### 1.5 The wizard

Six steps — `Step1Consignment`, `Step2Finance`, `Step3Shipping`,
`Step4Payments`, `Step5StatusRemarks`, `Step6Clearance` — plus `fields.tsx`.

`ImportsStatusWizard.tsx` holds `consignmentId`, `recordState`, `isLocked`,
`originalStatus` in React state, refreshed on every save. `saveDraft()` (`:204`)
branches on `consignmentId`: absent → `createConsignment`, present →
`updateConsignmentApi`; then `syncItemBackendIds` / `syncPaymentBackendIds`
attach the new ids so the next save updates rather than duplicates.

---

## 2. The fourteen findings

**1. No consignment-number column. CONFIRMED**, and per §0.4 more consequential
than revision 1 said. `importsMap.ts:243`, `:540` — `systemId: String(c.id)`;
interface at `:72`.

**2. `source_ref` is the primary key. CONFIRMED, with a nuance.**
`cross_module.py:176` sets `ref = str(consignment.id)`, used at `:180` and
`:276`. Nothing *stores* a display number, but `:182` renders the raw PK to a
human:

```python
"label": f"Import {ref} — {consignment.supplier.name ...}"
```

Two other display identities exist: `dashboard/imports/calculations.py:350` and
`:842` both render `instrument_number or f"IMP-{id}"` as `reference` —
`consignment_reference()`'s rule, reimplemented twice.

**Three display identities today**, and the requirements add a fourth concept
(the consignment number, §0.4). Unifying them is a precondition — §3.4.

**3, 5, 6. CONFIRMED structurally**, with the correction to 6 in §0.2 —
`batch_no` holds live data, not nothing.

**4. Required-vs-ETA is implemented twice. CONFIRMED, line corrected.**
`schema.ts:550` `requiredVsEtaDelay`; `importsMap.ts:317` `requiredDelayDays`.
The list consumes the second at `ImportsStatusList.tsx:23`, `:324`, `:325`,
`:327`. Step 1 consumes the first at `Step1Consignment.tsx:212`, rendered at
**310–314, not 308**.

**7. Header-field consumers. CONFIRMED — 24 call sites**, and the requirements
make this far larger than revision 1 implied: `branch`, `requisition_date` and
`required_date` are listed as **per item**, so all 24 read a field that is
moving down a level. §3.7 and §7 item 2.

- `app/imports/helpers.py:201`, `:920`
- `app/imports/serializers.py:100`, `:101`
- `app/dashboard/imports/helpers.py:43`, `:125`, `:149`, `:208`
- `app/dashboard/imports/calculations.py:631`, `:768`
- `app/dashboard/whole/helpers.py:71`, `:169`, `:821`, `:823`
- `app/dashboard/whole/references.py:89`, `:501`, `:503`, `:521`, `:533`,
  `:629`, `:657`
- `app/reports/helpers.py:165`, `:167`
- **`app/masters/helpers.py:164`** — the Branch master's "used" count, which the
  brief missed

**8. `works`. CONFIRMED, and simpler than the question.** NULL on every live
consignment, so a Branch-backed dropdown migrates zero values. CLAUDE.md already
records it as "a vestige — NULL on every loaded row". The obstacle is §1.3.

**9. Consignment row counts. CONFIRMED, but the count is 14, not 17.** Full list
in §3.2; three of the grep hits count items and history rows.

**10. No insurance or addenda on imports. CONFIRMED — and now a requirement.**
`insurance` exists only on `LogisticsConsignment` (`app/logistics/models.py:236`)
and its report serializer. Nothing named "addendum" exists anywhere. The
requirements' Step 4 asks for both: an insurance amount, and **an unbounded
"Add addendum" list** — which needs a new child table, not two more columns.

**11. The wizard creates an empty consignment. CONFIRMED.** `saveDraft()`
(`:204`) POSTs whenever `consignmentId` is absent — no dirty check, no content
check — called from `:253`, `:276`, `:297`. `create_consignment.py:64` then
fires `notify_created`. This is why 31 drafts exist, and the requirements
explicitly forbid it ("no draft should be created").

**12. The Excel export folds item lines. CONFIRMED.**
`export_consignments.py:38` `"; ".join(...)`, `:39` `" + ".join(...)` — one row
per consignment. The requirements demand the opposite ("one item = one row",
"every field entered anywhere must appear as a column") **plus two exclusions
that do not exist today** — drafts and deleted rows.

**13. Chatbot metadata hard-codes consignment joins. CONFIRMED.**
`business_terms.py:454`, `:489`–`:490`, `:504`, `:534`, plus `schema.py`,
`data_profile.json`, `learned_terms.json`. Separate service, separate deploy,
not exercised by `import app.main`.

**14. The four skill agents do not exist. CONFIRMED.** `.claude/skills/` holds
only `ui-ux-pro-max`. This document is my analysis, not four agents' output.

---

## 3. The data model decision

### The recommendation, unchanged

**Separate consignment rows per batch, linked by a group table** — B1 answered.
The requirements reinforce it: *"one batch = one consignment"*, and *"each batch
behaves as its own row with its own details; only the payment reference is
shared"*.

### 3.1 Why — restated without the dedupe argument

You asked me to drop the `(source, source_ref)` argument and say whether the
conclusion survives.

**The dedupe argument is withdrawn.** You are right: under batch children you
would key `source_ref` to the batch id and the problem dissolves. It was the
easy argument, not the strong one.

One qualification, offered as a cost and not as a rescue: `cross_module.py`
takes `Consignment` objects throughout, and the 1,370 existing trucking jobs
store header ids in `source_ref`. Re-keying to a batch id is a migration of its
own over those rows. That is a cost of the children model, not a defect in it,
and it does not carry the decision.

**The conclusion survives, on three independent grounds.**

**First, and decisive: per-batch state already exists, and cannot be cheaply
rebuilt.** The requirements and your decisions table both demand that each batch
have its own status, its own clearance, its own remarks, its own lock ("display
state only; every batch stays editable from its own screen") and therefore its
own edit history. Under separate rows a batch gets `record_state`, `is_locked`,
`is_deleted`, `ConsignmentChangeHistory`, `revert()` and `submission_errors()`
**for free, from tested code**. Under batch children every one of those is a
single column or a single chain on the shared header: locking batch 1 locks
batch 2; batch 1 cannot be submitted while batch 2 is still being keyed;
reverting batch 2 rewrites header fields batch 1 depends on.

The children model can only satisfy the requirements by duplicating
`record_state`, `is_locked`, `is_deleted`, a change-history table, a revert
path, a submit route and `submission_errors()` onto the batch table. **At that
point the batch table is a consignment** — built second, sharing none of the
first one's tested code. That is the nine functions of diff-and-revert machinery
in §1.4, re-implemented at a new nesting level.

**Second: the requirements want per-batch value, and separate rows give it for
free.** *"The batch's own value, not the whole consignment's."* Under separate
rows `recompute_derived()` already computes exactly that, because it sums the
rows attached to the consignment it is handed. Under children the stored
`foreign_total` / `pkr_total` are whole-LC figures matching no batch screen, so
either the function grows batch awareness or each screen computes its own — a
second money basis, which is the failure CLAUDE.md documents at length under
"One metric, one definition".

**Third: every line-based consumer keeps working.** Reports query the *line*
table for imports and join back (`app/reports/helpers.py`); the dashboards date
value by `ConsignmentItem.eta_works`; `_import_snapshot()` iterates
`consignment.items`. Under separate rows each batch has real `ConsignmentItem`
rows, so all of that is unchanged. Under children the line's owner is a batch,
not a consignment, and every one of those joins moves.

**What the requirements strengthen for the children model**, stated fairly:
"Finance entered once on batch 1", "Steps 1 and 2 already filled", "batch 1's
route locked above" all describe a parent/child mental model. My answer is that
**the group table is the parent** — separate rows plus a group *is* a
parent/child model. The only question is whether the child is a full consignment
or a reduced batch record, and "one batch = one consignment" answers it.

**Honest cost, unchanged:** consignment counts change meaning at 14 sites
(§3.2), plus the per-order/per-batch split in §3.7. Both are payable. The
children model's cost is not.

### 3.2 Impact on the five areas you named

**List query.** Nearly free. `fetch_consignments_page()` already returns one row
per `Consignment` = one row per batch, which is what the requirements want. The
pagination contract holds because `func.count(Consignment.id)`
(`helpers.py:270`) counts the rows the page returns. Under children a fan-out
would return 1 for a page showing 2 and paging would break.

*Added:* an index on `batch_group_id`; the group's number and batch label in the
serialized row; the blue "pending allocation" flag (§3.7).

**Dashboard counts — the real cost.** Fourteen sites:

| File | Lines |
|---|---|
| `app/dashboard/imports/helpers.py` | 73, 78 |
| `app/dashboard/whole/helpers.py` | 264, 292, 310, 350, 556, 575, 792, 860, 863 |
| `app/dashboard/whole/references.py` | 518 |
| `app/imports/helpers.py` | 270 |
| `app/masters/helpers.py` | 250 |

(`whole/helpers.py:270`, `whole/references.py:652`, `imports/helpers.py:313`
count items and history rows and are unaffected.)

An LC split in two counts as **2** where today it counts as 1. Each of the 14
needs a recorded decision: *how many LCs* (count distinct `batch_group_id`) or
*how many arrivals* (count rows)?

My default per site: **arrival-shaped figures count rows** (in-process by stage,
status splits, delay counts — a late batch is a late arrival regardless of its
siblings); **commercial-shaped figures count groups** (the Branch master's
"used" counts at `masters/helpers.py:164` and `:250`). A judgement per site, not
a rule applied blind, and the largest single line item in the build.

Given CLAUDE.md's history of two screens disagreeing on one metric, the
group-vs-row choice goes into `tests/check_dashboard_consistency.py` in the same
change.

**`cross_module.py` `source_ref`.** No change required — each batch is a
`Consignment` with its own id, `sent_to_trucking_at`, queue entry and reverse
lookup. One cosmetic edit: `:182`'s `f"Import {ref} — ..."` should render the
consignment number, not a primary key (§3.4). `_import_snapshot()` does change,
but for the reason in §3.7, not this one.

**`foreign_total` / `pkr_total`.** Each batch carries the totals for its own
allocated lines. `recompute_derived()` changes only in where it reads
`unit_price` from and in the new basis branch (§3.7, §6 Q1) — not in its shape.
A whole-LC total becomes `SUM ... GROUP BY batch_group_id`, additive.

**Change history and revert.** Untouched. Every batch gets its own history chain
and `revert()` because it is a `Consignment`. The largest saving in the
comparison.

### 3.3 What is LC-level — settled by the requirements

Revision 1 asked you which fields are shared and proposed four. The requirements
answer it, and the list is longer. From "What is shared, what is per-batch, what
is per-item":

**Shared across all batches** — supplier, origin, currency, consignment type,
incoterm, payment reference and payment mode.

**Entered once, on batch 1** — the whole of Step 2 (Finance) and Step 4
(Payments). Step 2 carries `exchange_rate`, `rate_booked_on`, `rate_source`,
`works` and the unit prices.

**Per batch** — Step 3 (shipping route and schedule), clearance, status and
remarks.

**Per item** — branch, requisition date, required date, weight.

Revision 1's §8 question 4 is therefore closed, including the exchange rate I
flagged as least certain: it is LC-level, edited on batch 1. I am not re-asking
it.

**Two things the requirements do not cover, and I am not inventing:**

- `po_date` is removed from Step 1 and not placed anywhere. I read that as
  deleted, not moved. §8 question 6.
- `clearing_agent_id`, `mode_of_shipment`, `loading_port_id` and
  `delivery_port_id` are named in none of the four lists. They are Step 3
  fields, so I have treated them as **per batch** — a different port or agent
  per shipment is normal. §8 question 7.

### 3.4 Display identity — three today, four concepts needed

Per §0.4 the requirements need **two** values shown together, where the code has
**three** competing implementations of one.

**Target state — one function each, both in `helpers.py`:**

```
consignment_number(consignment)   ->  "177"  or  "177-1"
payment_reference(consignment)    ->  "lc6222"    (mode + number, concatenated)
```

`consignment_reference()` retires into these two. The two dashboard copies
(`calculations.py:350`, `:842`) and `cross_module.py:182` import them rather
than reimplement the rule.

**Fixing that duplication is a precondition of this work, not a nice-to-have.**
With three implementations, a suffix added to one produces `177-2` on the list
and `177` in a notification about it — exactly what
`consignment_reference()`'s own comment was written to prevent: *"a notification
naming a consignment differently from the screen the reader then opens is a
notification they cannot act on."*

**The suffix rule** (revised — §3.5):

- Group has only ever held **one** batch → no suffix. `177`.
- Group has ever held **two or more** → `177-{batch_sequence}`.

**What `177` itself is remains open** — §0.4, §8 question 1.

### 3.5 Numbering permanence — I now recommend reversing the decisions table

Your Step 4 raises the case I had not. Under a `RANK()` over live batches, a
group that has held `177-1` and `177-2` reverts to a plain `177` the moment one
is deleted, and a supplier holding paperwork for `177-1` finds no such
consignment.

That is a real failure, and it is worse than you put it. It is not only the
revert-to-`177` case: under renumbering, deleting `177-2` of three makes the old
`177-3` **become** `177-2`. A number that has already gone out on an invoice now
identifies a *different shipment*. That is worse than a number resolving to
nothing — it resolves to the wrong thing, silently, and both parties believe
they agree.

Your A3 instinct was right, for exactly this reason. The decisions table went
the other way, and I recommend reversing it.

**Recommended rule — the suffix is the batch's own immutable
`batch_sequence`:**

- `batch_sequence` is assigned at creation, **never reused, never changed**.
- A group that has only ever held one batch displays no suffix.
- A group that has ever held two or more displays `{number}-{batch_sequence}`,
  permanently, for every batch in it.

Delete `177-2` of three and you are left with `177-1` and `177-3`. A gap — and
the gap is the point: no number ever moves, and no number is ever reused.
"Has ever held two or more" needs no new column in principle, because **nothing
in this system is hard-deleted**, so the soft-deleted rows are still there to
count.

**The case against, which you asked for:**

1. **Gaps read as data loss.** An operator seeing `177-1` and `177-3` asks where
   `177-2` went. *Mitigation:* show deleted batches in the expanded view, struck
   through. Cheap, and a better answer than hiding the gap.
2. **An early mistake is permanent.** A batch created and deleted in the same
   minute, before anything went out on paper, burns a number for ever.
   *Counter:* that costs one cosmetic gap; the alternative costs a number
   resolving to the wrong shipment.
3. **It contradicts a decision you told me not to reopen.** True. You reopened
   it; I am answering; the call is yours.

**What it costs in the rank computation — it is cheaper, not dearer.**

The `RANK()` design needs a window function over the group partition on every
list read, and paginating over a window function is awkward. The permanent rule
needs only `batch_sequence` (a column read) plus one boolean per group. Carry
`batches_ever` on the group row — an integer incremented on batch creation and
**never decremented** — and the display is:

```
suffix if group.batches_ever > 1 else no suffix
```

No window function, no read of soft-deleted rows at list time, and the list
query keeps the plain `func.count` pagination §3.2 depends on.

**Either way, renumbering never writes to a row**, which matters because 142 of
179 consignments are locked. Had the suffix been stored per row, deleting a
batch would need UPDATEs against locked siblings, and the 423 would either block
the delete or force a lock bypass. The permanent rule removes even the
temptation.

### 3.6 What happens to `batch_no`

Given §0.2 — 59 lines, 15 multi-batch consignments — **do not drop the column
and do not hide it in the same change**, even though the requirements remove it
from the item rows.

1. Keep `batch_no` and keep it visible. It is the only record of how those 15
   were split.
2. Ship batching. Add a read-only report listing the 15 so operators split them
   deliberately.
3. Hide the field once those are converted; drop the column a release later.

Migrating the 15 automatically is possible and I have **not** proposed it —
§4.5.

### 3.7 The item allocation model

This is the gap you identified, and it is the second half of the data model.

#### The question

Under separate rows, batch 2 is its own `Consignment` with its own
`ConsignmentItem` rows. So when the buyer ordered 250 kg and 100 kg sits on
batch 1 and 150 kg on batch 2, **nothing holds the 250**.

#### The three candidates

**(a) An order-item table paralleling the batch group.** One row per *ordered*
item on the LC, holding the per-order facts. Each batch's `ConsignmentItem`
gains `order_item_id`, and its `quantity` becomes the *allocated* quantity.

**(b) An `ordered_quantity` column carried on every split line.** Batch 1's line
says `ordered=250, quantity=100`; batch 2's says `ordered=250, quantity=150`.

**(c) Allocation rows separate from item lines.** An `allocations` table
(`order_item_id`, `consignment_id`, `quantity`); batches have no
`ConsignmentItem` rows of their own.

#### Recommendation: (a)

**Against (b):** it is the drift problem I rejected for header fields in §3.3,
one level down. 250 is repeated on every line; edit it on batch 1 only and "what
was actually ordered" becomes unanswerable, with no row that is authoritative.
It also has nowhere to put the fields the requirements call *per item* — branch,
requisition date, required date, weight — which are per-order facts, not
per-shipment ones, and would be duplicated and driftable in exactly the same
way.

**Against (c):** it is the cleanest normalisation and has the largest blast
radius. Removing `ConsignmentItem` from batches breaks every line-based consumer
at once: reports query the line table for imports (`app/reports/helpers.py`),
the dashboards date value by `ConsignmentItem.eta_works`, `_import_snapshot()`
iterates `consignment.items`, and the export is being moved to one row per line.
That is the third pillar of §3.1 knocked out for a normalisation gain.

**(a) keeps `consignment.items` populated per batch**, so every line-based
consumer keeps working unchanged, while giving one authoritative home for
per-order facts.

#### The field split

The rule I applied: **a fact about what was ordered goes on the order item; a
fact about what happened to a particular shipment goes on the batch line.**

**`consignment_order_items` — per order (one row per item on the LC)**

| | |
|---|---|
| Identity | `item_id`, `item_code`, `item_name`, `placeholder_name`, `specification`, `hs_code` |
| Quantity | `ordered_quantity`, `allocated_quantity` (denormalised, §6 B3), `unit_of_measurement` |
| Money | `unit_price`, `price_basis`, `unit_weight` (§6 Q1) |
| Demand | `branch_id`, `requisition_date`, `required_date` — the requirements' *per item* list |
| Requisition | `requisition_type` + `reference_number`, `job_number`, `mo_number`, `description` |

**`consignment_items` — per batch (what this shipment carried)**

| | |
|---|---|
| Links | `consignment_id` (the batch), `order_item_id` |
| Quantity | `quantity` — now the **allocated** quantity |
| Arrival | `eta_works` — batches arrive separately, so this is per batch and stays |
| Landed cost | `elc`, `alc`, four audit columns, `variance_absolute`, `variance_percentage` |
| Physical | `net_weight`, `gross_weight`, `length`, `width`, `height` |
| Legacy | `batch_no` (§3.6) |
| State | `is_deleted`, `deleted_at` |

**On your ELC/ALC question specifically — they are per batch, and they stay.**
You are right that an ALC entered against batch 1 is not the whole item's landed
cost, and that is precisely why it belongs on the batch: landed cost is
*incurred per arrival*. Duty, freight, clearance and demurrage attach to a
shipment, not to a purchase order. Two batches of one item legitimately land at
different costs. The order-level figure, if anyone ever wants one, is a
quantity-weighted sum across batches — derived, not stored, and nothing asks for
it today. The four audit columns follow the figures they audit.

`net_weight` / `gross_weight` stay per batch for the same reason: they describe
what physically moved. The new `unit_weight` (§6 Q1) is a per-order fact and
goes on the order item.

#### Outstanding, and what batch 2 holds

```
outstanding = order_item.ordered_quantity
            - SUM(batch line quantity across all live batches in the group)
```

Your decisions table says `177-2` exists the moment `177-1` is created. Under
(a) that is coherent and cheap: when the user allocates 100 of 250 to batch 1, a
second `Consignment` row is created in the same group and given a
`ConsignmentItem` for the remaining 150, pointing at the same `order_item_id`.
Outstanding is then 0 and the group is fully allocated.

If the user allocates 100 and leaves the rest **pending** rather than creating
batch 2, outstanding is 150 and the group carries the requirements' **blue
highlight**. Both states are expressible; which one the "Create batch" action
produces is a UI decision, and the requirements describe the first ("the
unallocated items are automatically placed into `177-2`").

A batch holding only the pending remainder is a real `Consignment` row in
`draft`, with a real value — not provisional. That answers A2's second half.

#### What it does to the three functions you named

**`recompute_derived()` (`helpers.py:862`).** Two changes, neither structural.
It reads `item.unit_price` off the line today; `unit_price` moves to the order
item, so it reads through `item.order_item` — which means create, update and
revert must `selectinload(ConsignmentItem.order_item)` or pay an N+1 on every
save. And the basis branch from §6 Q1 lands here:

```
by quantity  ->  line.quantity * order_item.unit_price
by weight    ->  line.quantity * order_item.unit_weight * order_item.unit_price
```

Its shape is otherwise unchanged — and usefully, because it sums the lines
attached to the consignment it is given, **each batch automatically gets its own
value**, which is exactly what the list requires.

**`apply_item_master_values()` (`helpers.py:818`).** It writes `item_name` and
`specification` from the master, keyed on `item_code`. All three columns move to
the order item, so the function moves with them: it takes a group rather than a
consignment, and runs once per group instead of once per batch. That is a
simplification — today it re-runs its query on every batch save and would
otherwise rewrite the same values *n* times.

**`_import_snapshot()` (`cross_module.py:106`).** It reads `item.item_name`,
`item.specification`, `item.quantity`, `item.net_weight`, `item.gross_weight`,
`item.length/width/height`. Three of those move to the order item, so it joins.

**But the important change is semantic, and the requirements file warns about it
in its own closing paragraph:** *"the trucking hand-off takes a point-in-time
snapshot including item quantities and weights — so changing what an item's
quantity means will affect it."*

Under (a), `item.quantity` in the snapshot becomes **the quantity allocated to
that batch**, not the quantity ordered. For trucking that is *more* correct — a
truck carries what arrived in that shipment, and today it is handed the whole
order's quantity regardless. The risk is that the 1,370 existing trucking jobs
carry stored snapshots built under the old meaning. Those are frozen JSON and do
not change retroactively, so nothing breaks; but a job created after this change
means something subtly different from one created before, with nothing in the
data saying which. §7 item 4.

### 3.8 "Stored on the group" vs "entered once on batch 1"

You are right that these are different decisions, and the requirements only
specify the second.

**(i) Store on the group.** One physical row. Drift is impossible because there
is only one value. Editing the field means editing the group.

**(ii) Store on every batch row; the UI makes batch 1 the only editable one.**
Drift is possible; keeping the copies aligned needs a propagation write to every
sibling on every save.

**I am implementing (i)** for every field in the "shared" and "entered once on
batch 1" lists — supplier, origin, currency, consignment type, incoterm, payment
instrument and number, exchange rate, rate booked on, rate source, works, and
the unit prices (the last via the order-item table, §3.7, which is the same
principle applied to lines).

**Three reasons, in order of weight:**

1. **(ii) is a UI convention protecting a data invariant.** CLAUDE.md's own
   history is a list of invariants that were conventions until they were not:
   the two dead-stock definitions, the two runway formulas, the two procurement
   defaults. A rule enforced only by which control is disabled survives exactly
   until one code path writes the field without going through that control — the
   loaders, a revert, a migration, a script.

2. **(ii) collides with the lock, and 142 of 179 consignments are locked.**
   Editing the exchange rate on batch 1 under (ii) requires writing batch 2. If
   batch 2 has reached "Arrived at Works" and been submitted, that write is a
   423. The edit then either fails for a reason the user cannot act on, or the
   propagation quietly bypasses the lock. Under (i) there is nothing to
   propagate.

3. **(ii) multiplies the change-history problem.** A single rate edit becomes
   *n* `ConsignmentChangeHistory` rows across *n* batches, and reverting one of
   them puts the group back into the drift state the scheme exists to prevent.

The cost of (i) is that every read of a shared field is a join, and
`fetch_consignment` / `fetch_consignments_page` must `joinedload` the group or
pay an N+1. That is one line in each, and it is the cheaper problem.

---

## 4. The migration

One Alembic revision. Revision 1's migration did not implement what revision 1's
design argued for; you caught it, and this section is rewritten.

### 4.1 Schema — groups and the shared fields

```
create table consignment_batch_groups (
    id                  serial primary key,

    -- identity
    consignment_number  ...        -- §8 question 1; type depends on the answer
    batches_ever        integer not null server_default '1',      -- §3.5

    -- shared across all batches (§3.3)
    supplier_id         integer references suppliers(id),
    origin              varchar,
    currency            varchar,
    consignment_type    varchar,
    incoterm            varchar,
    payment_instrument  varchar,
    instrument_number   varchar,

    -- entered once on batch 1: Step 2 Finance (§3.3, §3.8)
    exchange_rate       numeric(12,6),
    rate_booked_on      date,
    rate_source         varchar,
    works_branch_id     integer references branches(id),          -- §7 item 8

    -- Step 4 Payments, LC-level (§4.4)
    insurance_amount    numeric(20,2),

    created_at, updated_at, is_deleted, deleted_at,
    deleted_by_id, created_by_id
)

alter table consignments
    add column batch_group_id integer references consignment_batch_groups(id),
    add column batch_sequence integer not null server_default '1'

alter table consignments
    drop column supplier_id, origin, currency, consignment_type, incoterm,
                payment_instrument, instrument_number,
                exchange_rate, rate_booked_on, rate_source, works

create index ix_consignments_batch_group_id on consignments (batch_group_id)
create unique index uq_consignments_group_sequence
    on consignments (batch_group_id, batch_sequence)
```

`server_default` on `batch_sequence` and `batches_ever` is not optional — the
loaders insert through raw psycopg2, where a Python-side `default=` never runs
(CLAUDE.md, "Server-side defaults for loader-written flags").

A dedicated group table rather than a self-referential FK to the founding
consignment, for one reason: **deleting the founding batch must not orphan the
group.** A self-reference makes batch 1 structurally special, and your rules say
every batch is equal and any may be deleted.

### 4.2 Schema — order items and allocation

```
create table consignment_order_items (
    id                  serial primary key,
    batch_group_id      integer not null references consignment_batch_groups(id),

    item_id             integer references items(id),
    item_code           varchar,
    item_name           varchar,
    placeholder_name    varchar,
    specification       varchar,
    hs_code             varchar,

    ordered_quantity    numeric(14,3) not null,
    allocated_quantity  numeric(14,3) not null server_default '0',
    unit_of_measurement varchar,

    unit_price          numeric(18,4),
    price_basis         varchar not null server_default 'quantity',   -- §6 Q1
    unit_weight         numeric(14,3),                                -- §6 Q1

    branch_id           integer references branches(id),
    requisition_date    date,
    required_date       date,

    requisition_type    varchar,
    reference_number    varchar,
    job_number          varchar,
    mo_number           varchar,
    description         varchar,

    created_at, updated_at, is_deleted, deleted_at,

    constraint ck_allocation_within_order
        check (allocated_quantity <= ordered_quantity)                -- §6 B3
)

alter table consignment_items
    add column order_item_id integer references consignment_order_items(id)

alter table consignment_items
    drop column item_id, item_code, item_name, placeholder_name, specification,
                hs_code, unit_price, unit_of_measurement,
                requisition_type, reference_number, job_number, mo_number,
                description

create index ix_consignment_order_items_group on consignment_order_items (batch_group_id)
create index ix_consignment_items_order_item on consignment_items (order_item_id)
```

The **drops** in §4.1 and §4.2 are the part to review hardest. They are what
makes this migration destructive rather than additive, and they are why §4.6
says what it says about reversibility.

### 4.3 Data migration

For each of the **183** consignment rows — all 179 live *and* all 4 soft-deleted;
excluding the deleted would break undo-delete:

1. Insert one `consignment_batch_groups` row, copying the eleven shared columns
   off the consignment before they are dropped.
2. Set `batch_group_id`, `batch_sequence = 1`, `batches_ever = 1`.
3. For each of that consignment's item lines — **455 across the table** — insert
   one `consignment_order_items` row, copying the per-order columns off the
   line, with `ordered_quantity = quantity` and `allocated_quantity = quantity`:
   the whole order is allocated to the single batch, which is exactly what those
   rows mean today.
4. Point the line's `order_item_id` at it.
5. Then, and only then, drop the columns.

Every group has one member, so by the §3.4 rule **every existing consignment
displays with no suffix** — subject to §0.4, the open question of what the
number itself is.

`batch_group_id` and `order_item_id` get `NOT NULL` in the same revision, after
the backfill, so no window exists in which a consignment has no group or a line
has no order item.

### 4.4 Payments

You are right that this was unresolved. `Payment.consignment_id` points at what
is now a batch row, while the requirements put payments once per consignment on
batch 1. As written, two batches of one LC could each carry a full payment
history.

```
alter table payments
    add column batch_group_id integer references consignment_batch_groups(id)

update payments p
   set batch_group_id = c.batch_group_id
  from consignments c
 where c.id = p.consignment_id

alter table payments
    alter column batch_group_id set not null,
    drop column consignment_id
```

**This costs almost nothing: there is exactly one payment row in the entire
database**, against one consignment. The migration is real, but the data it
moves is a single row — worth knowing before anyone worries about it.

The new addenda table from finding 10 hangs off the group for the same reason:

```
create table payment_addenda (
    id              serial primary key,
    batch_group_id  integer not null references consignment_batch_groups(id),
    ...
    created_at, updated_at, is_deleted, deleted_at
)
```

and `insurance_amount` is a column on `consignment_batch_groups` (§4.1) —
LC-level, like the rest of Step 4.

### 4.5 What the migration deliberately does NOT do

**It does not split the 15 multi-batch consignments** from §0.2.

It could — group the lines by `batch_no`, create a batch per distinct value,
move the lines. I am not proposing it:

1. It would restate `foreign_total` and `pkr_total` on 15 consignments by
   splitting them across new rows. CLAUDE.md rule 4 exists so a later change
   cannot restate a printed report, and this would do exactly that inside a
   migration, where nobody reviews the arithmetic.
2. `B1`–`B4` are free text an operator typed. Whether `B1` on one consignment
   means the same as `B1` on another is a business question, and CLAUDE.md is
   explicit that business rules are not to be invented.
3. At the 79% rate, roughly twelve of the fifteen are locked. A migration
   restructuring locked consignments bypasses the lock silently.

The §3.6 report lets operators do it deliberately, on screen, with the totals
visibly recomputing. Slower and correct.

### 4.6 Down-revision, and whether it is honestly reversible

`down_revision` is the current head; the real hash goes into the revision when
it is written.

**Revision 1 said "reversible until the first batch exists". That was true of
revision 1's additive migration. It is not true of this one, and I would rather
correct it than let it stand.**

This migration **drops twenty-four columns** — eleven from `consignments`,
twelve from `consignment_items`, one from `payments`. A `downgrade()` can
recreate them and copy the values back out of the group and order-item rows, and
for a database that has never held a real batch that is a genuine round trip.
So:

- **Immediately after upgrade, before any batch is created: reversible** — but
  by a hand-written `downgrade()` that copies data back, not by dropping what
  was added. That code has to be written and tested, and the normal path will
  never exercise it. Assume it is the least-tested code in the change.

- **After real batches exist: not reversible in the sense that matters.** The
  rows survive, but a group of three batches downgrades into three unlinked
  consignments with the shared fields copied onto each — indistinguishable from
  three duplicate LC entries — and the order items collapse back onto lines,
  losing which allocation belonged to which shipment. There is no automatic way
  back, because the structure that would rebuild it is what is being dropped.

**Recommendation, strengthened from revision 1:** deploy the schema behind a
feature flag with the batching UI disabled, so the reversible window covers the
risky deploy. Given that the downgrade path is hand-written and effectively
untested, take a database backup immediately before `alembic upgrade head` and
say so in the deploy note. That is not boilerplate caution — it is the honest
consequence of a migration that drops twenty-four columns.

---

## 5. Conflicts and downstream consumers

### 5.1 Direct conflicts with existing rules

| Conflict | Detail |
|---|---|
| **CLAUDE.md is a contract** | The working agreement says the doc is written first, then the code. Batching changes the imports section, `cross_module.py`'s description, the list-filter contract, the migration notes, and rules 1, 2 and 11. Same PR. |
| **`func.count(Consignment.id)` semantics** | 14 sites, §3.2. |
| **Rules 1 and 2 change shape** | Rule 1 says the line holds item, quantity, price and requisition details; rule 2 says "requisition details belong to the ITEM". Under §3.7 they belong to the *order* item. Both need rewriting, not extending. |
| **Rule 11 is reaffirmed, not changed** | "ELC and ALC are manual, per-item, never calculated" — they stay on the batch line (§3.7), which is per item *per shipment*. Worth stating explicitly so the next reader does not move them to the order item for tidiness. |
| **`is_closed()` is per-row** | Correct as-is, but "is this LC closed?" becomes a new question (all live batches closed). Nothing asks it today; something will. |
| **The `works` submit rule** | §1.3. Already broken; batching multiplies it; the dropdown fixes it if the backfill ships. |

### 5.2 Every downstream consumer

**Logistics.** `GET /logistics/import-fob-jobs` lists consignments with
`sent_to_logistics_at`. Each batch carries its own, so the list is per batch —
correct, no code change, but row labels must go through the §3.4 functions or
logistics sees two rows with one name.

**Trucking.** `/open-requests` and both `/{id}/trucking-jobs` need no functional
change (§3.2). `_import_snapshot()` does change, per §3.7 — a join, plus the
semantic shift in what `quantity` means.

**Dashboards.** The 14 count sites plus the 24 header-field consumers in finding
7 — and the second group is now the larger problem, because `branch_id`,
`requisition_date` and `required_date` move from the header to the *order item*
(§3.3, §3.7), two levels down. Every one of those 24 joins changes;
`whole/references.py` has seven and `whole/helpers.py` four. The **line-based**
money figures are unaffected: a line still belongs to exactly one batch, and
value still sums over lines.

**Reports.** `app/reports/helpers.py` already queries the line table for imports
and joins back, so a report row stays per line. `_line_value_pkr` must read
`unit_price` through the order item and honour `price_basis`. Date filters at
`:165`/`:167` move from `Consignment.requisition_date` to the order item.

**Notifications.** `notify_created` fires per consignment, so creating batch 2
raises a create event — right in principle, but it interacts badly with finding
11: a wizard that creates empty rows would now create empty *batches*. Fixing
finding 11 must ship in the same release, and the requirements demand it anyway.

**Loading scripts.** `load_all` and `reload_changed` both drop and rebuild the
consignment family through raw psycopg2. Both must populate the two new tables
and the FKs explicitly (no Python defaults run), and `etl_common.bump_sequence`
must be called for `consignment_batch_groups` and `consignment_order_items` —
the omission CLAUDE.md records as the cause of the Masters screen 500s.
`backfill_import_demand_dates` groups by payment reference, which is now a group
attribute, and must be re-checked. `post_load.py` gains checks for a NULL
`batch_group_id`, a NULL `order_item_id`, and an `allocated_quantity` that
disagrees with the sum of its lines (§6 B3).

**Chatbot metadata.** `business_terms.py` (`:454`, `:489`–`:490`, `:504`,
`:534`), `schema.py`, `data_profile.json`. **Separate service, separate deploy.**
Its generated SQL will silently double-count any batched LC, and its
`consignments.branch_id` join guidance points at a column that will no longer
exist. The consumer most likely to be forgotten, because nothing in the ERP's
own verification touches it.

**Excel export.** Finding 12, and the requirements go further than "unfold it":
every field from all steps as a column, drafts and deleted rows excluded.

**Masters.** `masters/helpers.py:164` and `:250` — the Branch "used" count, now
counting through the order item.

---

## 6. Questions answered

### Q1 — the unit price basis *(amended: the requirements change this)*

**Which reading does the code support?** `quantity × unit_price`, and only that.
`recompute_derived()` (`helpers.py:862`) computes the line total as quantity
times unit price; weight is not in the calculation anywhere.

**What does `unit_price` mean today?** Price for one unit of the line's
`unit_of_measurement`, in the consignment's currency. Populated on 407 of 455
lines.

**What the requirements change.** Revision 1 framed this as "pick one formula".
The requirements do not — Step 2 asks for **a checkbox beside each item**
choosing its basis:

- **By quantity** (current): `quantity × unit price`
- **By weight**: `quantity × weight × unit price`

So both formulas coexist, chosen per line. That is a `price_basis` column on the
order item (§4.2), a branch in `recompute_derived()` (§3.7), and a mirrored
branch in the frontend's value display.

**Is a new per-unit weight field needed? Yes — and the requirements confirm it.**
`quantity × weight × unit_price` is only coherent if `weight` is *per unit*. The
existing `net_weight` is documented as the opposite, `models.py:483–487`:

> `net_weight` is the line's total for its whole quantity (not a per-unit
> figure) — mirrors `LogisticsItem`'s `gross_weight` convention.

Under that definition the formula multiplies quantity in twice. Both
`net_weight` and `gross_weight` are **0 of 455 populated**, so redefining
`net_weight` would migrate no data — I still recommend against it, because
silently changing what a field means, when its own comment says the opposite and
a sibling module follows the documented convention, is precisely the class of
bug CLAUDE.md's "One metric, one definition" section is built from. **Add
`unit_weight` on the order item and leave `net_weight` alone.** The requirements
call it "Weight per item (optional)", which is the same field.

**What must the label become?** It has to be dynamic, because one column now
carries two meanings:

- basis = quantity → **"Unit Price (per {unit_of_measurement})"**
- basis = weight → **"Unit Price (per {weight unit})"**

**A4 is still open, and narrower than it was.** Not "is the price per kilogram" —
the checkbox settles that it is, under the weight basis — but **what the weight
unit is**. `net_weight` is documented as kg; nothing states that `unit_weight`
is. If some items are priced per tonne or per pound, one column cannot carry it
and a `weight_unit` field is needed. §8 question 2.

### Q2 — Required vs ETA

**Is it read-only and computed?** Yes, in both implementations. Neither is
stored, written or submitted.

**Does anything else depend on either?** No — and I checked the backend
specifically, because a server-side delay figure would make removing the
frontend one a data change rather than a display change. It does not.
`app/dashboard/whole/helpers.py:821–823` and `references.py:501–503` compute
delay independently in SQL against `Consignment.required_date` and `eta_works`,
with a `DELAY_GRACE_DAYS` grace period the frontend implementations do not have.
**The two frontend functions have no consumers other than the two render sites
in finding 4.**

That grace-period difference matters on its own: the list column and the
dashboard's Delayed tile can legitimately disagree about the same consignment
today.

**Should the list column go too?** The requirements answer half of this — the
main list drops requisition date and required date, moving them to the expanded
per-item view. They do not mention the delay column.

**My recommendation: keep the delay column, remove the Step 1 one.** They are
not the same feature twice:

- In the list, delay is *comparative*. It sorts (`ImportsStatusList.tsx:325`)
  and tells you which of forty consignments to look at first.
- In Step 1 it is a number beside two fields the user is mid-way through typing,
  changing as they type, that they cannot act on and cannot sort. Noise during
  data entry.

Two caveats on keeping it:

1. `required_date` is populated on only **97 of 179** consignments, so the column
   is blank on 46% of rows — and under §3.7 it moves to the order item, so a
   consignment with three items can carry three different required dates and the
   column needs a rule (earliest, presumably). That is new. §8 question 3.
2. If it stays, it should adopt `DELAY_GRACE_DAYS` so the list and the Delayed
   tile stop disagreeing.

Deleting `schema.ts:550` and keeping `importsMap.ts:317` also resolves finding 4
outright — one implementation, one consumer.

### B3 — how allocation is enforced

**Allocated quantity across all batches must never exceed the ordered quantity.**

**A plain CHECK constraint cannot express it, and I want to say that without
hedging.** A CHECK sees one row. The quantities being summed live on
`consignment_items` rows attached to *different* `consignments` rows, and the
limit lives on a third table. SQL has no cross-row CHECK, and no exclusion
constraint expresses a SUM.

Two things could enforce it in the database and I am proposing neither as the
primary mechanism:

- **A trigger.** Postgres does this correctly. But there is not one trigger
  anywhere in this schema, and CLAUDE.md's stated model is that business logic
  lives in models and helpers. Introducing the codebase's only trigger for this
  one rule puts logic somewhere no future reader will look for it.
- **A materialised view with a unique constraint.** Contorted, and it moves the
  failure to refresh time rather than write time.

**What I propose instead — two layers, neither of them the client:**

**Layer 1, the real enforcement: the server, with a row lock.** Batch create and
update take `SELECT ... FOR UPDATE` on the order-item row before writing, then
check the sum. **The lock is not optional** — without it two users saving two
batches concurrently both read `allocated = 100`, both write, and both succeed.
This is the layer that returns a readable 422 naming the item and the overage.

**Layer 2, the backstop: `allocated_quantity` denormalised on the order item,
with `CHECK (allocated_quantity <= ordered_quantity)`** (§4.2). The sum is
maintained on the parent row in the same transaction, where a CHECK *can* see
it. This catches any path that forgets layer 1 — including the loaders, which
bypass the ORM entirely and are exactly the kind of code that forgets.

**The honest weakness of layer 2: the denormalised column can drift** from the
actual sum of its lines. Nothing in the constraint proves it matches. That is
why §5.2 adds a `post_load.py` check comparing `allocated_quantity` against
`SUM(quantity)` per order item — the same conditional-repair pattern CLAUDE.md
already uses for columns that have silently arrived empty.

So: **not client-only, not database-only.** Server-enforced with a lock, a
database constraint as a backstop, and a load-time check on the backstop.

### B4 — keeping `schema.ts` and `submission_errors()` in agreement

This is worse than the question assumes. There are **three** encodings, not two,
and one divergence is already documented in the code:

1. `app/imports/helpers.py::submission_errors()` — authoritative.
2. `schema.ts:388` `consignmentSubmitSchema` — the zod submit schema. It carries
   **one rule the backend does not enforce**: `gateOutDate < eta`.
3. `schema.ts` `submitRequirements()` — drives the wizard banner and the disabled
   Submit button. Its own comment (`:650`) says it **mirrors the backend, not the
   schema above it**, precisely because deriving the banner from the schema would
   disable Submit over something nothing actually refuses.

So the codebase has already hit this problem, solved it once, and written the
divergence down rather than resolving it.

**The structural answer already exists and is under-used: the server publishes
its own verdict on every read.** `serializers.py:135` returns `missing_fields`,
computed by `submission_errors()` (`serializers.py:69–74`), on every GET. That
is a shared source of truth over the wire. The frontend duplication exists only
to avoid a round-trip while the user types.

**What I propose, in order of preference:**

1. **Render the banner from `missing_fields` wherever a saved record exists.**
   After the first save — which is every state except a brand-new unsaved draft —
   the wizard already has the server's own list and does not need to predict it.
   `submitRequirements()` shrinks to covering the unsaved case only. This removes
   most of the duplication rather than policing it.

2. **A fixture-based agreement test for what remains.** A small set of
   consignment shapes as JSON, checked into the repo, each with its expected
   error list. `tests/test_submission_rules.py` already asserts the backend
   against fixtures; a frontend test asserts `submitRequirements()` against **the
   same file**. Divergence fails a test rather than reaching a user. **This is
   the enforceable convention you asked for — a check that runs, not an
   intention.**

3. **A code-review rule that is cheap because it is mechanical:** any PR touching
   `submission_errors()` must touch the shared fixture file. Greppable in review,
   and it does not depend on anyone remembering the rule.

**One line for review:** *"`submission_errors()` is authoritative; the frontend
may only predict it, never extend it; every rule the frontend adds beyond it must
be documented at its definition, as `consignmentSubmitSchema`'s `gateOutDate`
rule already is."*

**What I cannot honestly claim:** nothing short of generating both from one
source — a shared JSON rule description, or generating TypeScript types from the
Pydantic schemas — makes divergence structurally impossible. That is a larger
piece of work than this change and I am not proposing it here. Options 1 and 2
together shrink the surface and make the remainder fail loudly, which is the
cheapest honest answer.

---

## 7. What breaks existing data, ranked

Severity is *what it costs if it goes wrong in production*, not likelihood.

### 1 — CRITICAL: dashboard counts change meaning silently

**What.** 14 sites (§3.2). The moment one LC is batched, every consignment count
increments by one, with no error and no visible symptom.

**Why worst.** Silent, everywhere, and it corrupts the figures management reads.
CLAUDE.md is largely a record of this exact failure mode — two screens
disagreeing, *"and neither number was wrong for its own formula, which is what
makes that class of bug expensive: both screens looked right."*

**Mitigation.** Decide group-vs-row per site, record the decision in the code,
assert each in `tests/check_dashboard_consistency.py`. Ship the schema and the
count decisions together — never the schema alone.

### 2 — CRITICAL: 24 consumers read fields that move two levels down

**What.** Finding 7. `branch_id`, `requisition_date` and `required_date` are
*per item* in the requirements, so under §3.7 they leave the header for the
order-item table. Twenty-four call sites join to a column that will not exist.

**Why critical rather than merely large.** These fail loudly at the boundary — a
missing column is an error, not a wrong number — but the *aggregation* changes
silently. A consignment with three items and three different branches currently
contributes to one branch; afterwards it contributes to three. The Branch
master's "used" count, every branch-grouped dashboard and every branch reference
list change meaning with no error anywhere.

**Mitigation.** Treat it as its own workstream, not as a rename. Each of the 24
needs a stated aggregation rule — which branch does a *consignment* belong to
when its items disagree? My default is that branch-grouped figures group by
item, not by consignment, which is more correct and changes every branch total
in the app. That needs your agreement before it ships. §8 question 3.

### 3 — CRITICAL: chatbot answers go wrong with nothing to notice

**What.** `business_terms.py` gives explicit `consignments.branch_id -> branches`
join guidance at `:454` and `:489`–`:490`, against a column that is moving.
Batched LCs also double-count. Separate service, separate deploy, not covered by
`import app.main`.

**Why.** A wrong dashboard number gets challenged. A confident wrong sentence
from an assistant gets believed.

**Mitigation.** Update the metadata in the same PR though it deploys separately;
verify by importing `backend.*` from inside `chatbot_backend/` per CLAUDE.md.
Add batching as an explicit term.

### 4 — HIGH: the trucking snapshot changes meaning, silently, for new jobs only

**What.** §3.7. `_import_snapshot()`'s `quantity` becomes the batch's allocated
quantity rather than the whole order's. The requirements file flags this itself.

**Why.** The 1,370 existing jobs hold frozen JSON built under the old meaning.
Nothing breaks and nothing errors — but a job created after the change means
something different from one created before, with nothing in the data saying
which. Anyone comparing them is comparing two different quantities.

**Mitigation.** Stamp a `snapshot_version` into the JSON at write time so the two
populations are distinguishable, and record in CLAUDE.md what each version
means. Cheap now, impossible retrospectively.

### 5 — HIGH: a hand-written, effectively untested downgrade

**What.** §4.6. The migration drops twenty-four columns, so `downgrade()` must
copy data back rather than drop what it added.

**Mitigation.** Feature flag so the reversible window covers the deploy; a backup
immediately before `upgrade head`, stated in the deploy note; and exercise
`downgrade()` once against a scratch copy before it is trusted — never against
the live database, per CLAUDE.md's test-safety rule.

### 6 — HIGH: the 142 locked consignments

**What.** 79% of live consignments are locked; update and submit return 423, and
only an admin reopens. Any operation writing to a sibling row hits that wall.

**Mitigation.** §3.5 (numbering writes nothing) and §3.8 (shared fields stored
once, so nothing propagates) — both were chosen partly for this. **The remaining
question is yours:** can a batch be added to a group whose other batches are
locked? Operationally it must be — a second shipment arriving after the first has
landed is the normal case — but it is a customs and finance call. §8 question 4.

### 7 — MEDIUM: empty batches, multiplied

**What.** Finding 11 — the wizard creates a row on the first Next, with a
notification. 31 drafts exist because of it. Under batching this creates empty
*batches* inside real LCs, visible to everyone as `177-2`.

**Mitigation.** Fix finding 11 in the same release; the requirements demand it
("no draft should be created"). Defer the create until the first meaningful field
is set, and gate `notify_created` on non-empty content.

### 8 — MEDIUM: the works dropdown cannot be submitted against

**What.** §1.3. NULL on 179 of 179, required by `submission_errors()`.

**Mitigation.** The requirements' Branch-backed dropdown plus a backfill copying
`branch_id` into the new `works_branch_id`. CLAUDE.md already states Works and
Branch are the same thing to the business, so this is a correction, not a change.

### 9 — MEDIUM: `batch_no` becomes two sources of truth

**What.** 59 lines carry a hand-typed batch marker that a real batch column will
now contradict.

**Mitigation.** §3.6 — keep, report, convert deliberately, drop later.

### 10 — LOW: the export

**What.** Finding 12, plus two exclusions that do not exist today (drafts,
deleted) and a requirement that every field appear as a column.

**Mitigation.** Independently shippable, and worth shipping first as a way of
enumerating every field before the model moves under it.

### 11 — LOW: loader inserts

**What.** Raw psycopg2 inserts need the new FKs and `bump_sequence` on two new
tables; `allocated_quantity` can drift (§6 B3).

**Mitigation.** `server_default`s (§4.1, §4.2), plus `post_load.py` checks for
NULL `batch_group_id`, NULL `order_item_id` and a drifted `allocated_quantity`.
All cheap, all fail loudly.

---

## 8. What I need from you before building

Revision 1 asked seven questions; the requirements file answers four (the
LC-level field list, the works decision, and both numbering behaviours). These
are what remain, plus three the requirements introduced.

1. **What is `177`?** (§0.4.) The existing `consignments.id`, a new sequential
   number per group, or a number the business already uses on paper that the
   system has never held? This decides whether "existing displayed numbers must
   not change" is satisfied for free or needs a back-fill by hand. **The two
   documents do not settle it and I have not guessed.**

2. **What unit is `unit_weight` in?** (§6 Q1.) The checkbox settles that the
   weight basis prices per weight unit; it does not say which. If everything is
   kg, one column is enough. If anything is priced per tonne or per pound, a
   `weight_unit` field is needed and the label follows it.

3. **When a consignment's items disagree, what does the consignment show?**
   (§7 item 2, §6 Q2.) Branch, requisition date and required date become
   per-item. A consignment with three items can have three branches and three
   required dates. Which branch does a branch-grouped dashboard count it under —
   or does it count once per item? My default is per item, which is more correct
   and changes every branch total in the app.

4. **Can a batch be added to a group whose siblings are locked?** (§7 item 6.)
   I believe yes; it is a customs and finance question.

5. **Numbering permanence — do you accept the reversal?** (§3.5.) I recommend
   permanent suffixes over renumbering, against your own decisions table and in
   line with your A3 instinct. The case against and the cost are both stated.
   Your call, and it is cheap to change now and expensive later.

6. **Where does `po_date` go?** (§3.3.) The requirements remove it from Step 1
   and do not place it anywhere. I read that as deleted. Confirm, because it is a
   column with data in it.

7. **Are `clearing_agent_id`, `mode_of_shipment`, `loading_port_id` and
   `delivery_port_id` per batch?** (§3.3.) Named in none of the four lists. They
   are Step 3 fields and a different port or agent per shipment is normal, so I
   have assumed per batch. Confirm.

---

## 9. Build order, if approved

Not a commitment — the sequence I would follow, so you can see the shape.

1. **Unify the display identities** into `consignment_number()` and
   `payment_reference()` (§3.4), and change the payment reference to mode +
   number. No schema change, independently shippable, and it makes the batching
   change smaller.
2. **Fix finding 11** (no empty draft) and **finding 12** (export: one row per
   line, every field, drafts and deleted excluded). Both independent, and the
   export forces a full field inventory before the model moves.
3. **The Alembic revision** (§4), behind a feature flag with the UI disabled —
   the reversible window (§4.6). Backup first.
4. **The 24 header-field consumers** (§7 item 2) with their stated aggregation
   rules, and **the 14 count decisions** (§3.2) with their consistency
   assertions. The largest piece, and the one to do while the flag is off.
5. **Backend:** group and order-item models, allocation with the row lock
   (§6 B3), batch creation, numbering (§3.5).
6. **Frontend:** the Step 3 allocation screen, list rows and blue highlight,
   expanded per-item view, the `SearchableSelect`-backed country (ISO 3166) and
   works dropdowns, the per-item price-basis checkbox.
7. **Payments:** the group move (§4.4), insurance, the addenda table.
8. **Chatbot metadata**, verified by importing `backend.*` from inside
   `chatbot_backend/`.
9. **CLAUDE.md**, same PR — including rules 1, 2 and 11 (§5.1).
10. **The §3.6 conversion report** for the 15 existing multi-batch consignments.
