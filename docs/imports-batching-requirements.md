# Imports Module — Requirements for Batch-Based Consignments

## The core change

**Today:** one payment reference (LC number) = one consignment.

**Wanted:** one **batch** = one consignment. A single LC that arrives in two shipments becomes two consignments in the system, linked by the shared payment reference.

This is a change to what a consignment *is*, not a change to a screen. Nearly everything below follows from it.

### Numbering

| Situation | Consignment number shown | Payment reference shown below |
|---|---|---|
| All items in one batch | `177` | `lc6222` |
| Split into two batches | `177-1` and `177-2` | `lc6222` on both |
| Split into three | `177-1`, `177-2`, `177-3` | `lc6222` on all |

The payment reference is displayed as **payment mode + reference number** concatenated — an LC with reference 6222 shows as `lc6222`, and in the list view in the form `lc-78889`.

If the user allocates every item into the first batch, the consignment keeps the plain number `177` with no suffix — it is not treated as a partial consignment.

---

## What is shared, what is per-batch, what is per-item

This is the most important thing to get right, because it determines the data model.

### Shared across all batches of one consignment
Set once, identical on every batch, not re-entered:
- Supplier
- Origin / country of origin
- Currency
- Consignment type
- Incoterm
- Payment reference and payment mode

### Entered once, on the first batch only
Editable only on batch 1; read-only on later batches, which display the same values:
- **Step 2 — Finance** (the whole step)
- **Step 4 — Payments** (done once for the whole consignment)

### Per batch
Each batch has its own:
- **Step 3 — Shipping**: route and schedule
- **Clearance**
- **Status and remarks**

When viewing batch 2, the shipping step shows batch 1's route and schedule **locked above**, with batch 2's own section editable below. Batch 3 shows batches 1 and 2 locked, its own editable. Same pattern for clearance.

### Per item
These vary from item to item within the same consignment:
- Branch
- Requisition date
- Required date
- Weight (new, optional)

---

## Step 1 — Consignment

**Remove:**
- PO date
- "Required vs ETA"
- Batch number from the item rows (batching now happens in Step 3)

**Country of origin** becomes a searchable dropdown listing **every country in the world**, with type-to-filter — the user types "paki" and gets Pakistan rather than scrolling a long list. The project already has a `SearchableSelect` component built for supplier, ports, customer and transporter; this should use the same one so the behaviour matches the rest of the form.

**Item fields stay as they are** — item name, placeholder name, item code, HS code, specification, quantity, unit of measurement — **plus**:
- Weight per item (optional)

**Item-level fields** (can differ per item): branch, requisition date, required date.

---

## Step 2 — Finance

**Unit price basis.** Add a checkbox beside each item choosing how its value is calculated:
- **By quantity** (current behaviour): `quantity × unit price`
- **By weight**: `quantity × weight × unit price`

**Works field** becomes a dropdown, populated from the same list as branches.

---

## Step 3 — Shipping (the largest change)

This step becomes the place where batches are created.

**Item allocation view.** Show every item on the consignment with:
- Allocated quantity
- Outstanding quantity
- Always **quantity**, never weight
- Quantity displayed with its unit of measurement (e.g. `250 kg`)

**Creating a batch.** Below the item list, a "Create batch" action. When a batch is created:

1. The route and schedule section appears for that batch, with all the fields it has today
2. Below it, any items still awaiting allocation are shown
3. The user can create another batch for them, or leave them pending
4. The consignment number changes from `177` to `177-1`
5. The unallocated items are automatically placed into `177-2`

**Pending allocation.** If items remain unallocated, the list view shows that consignment with a **blue highlighted line**.

**Opening a later batch** (e.g. `177-2`):
- Steps 1 and 2 are already filled with that batch's respective quantities
- Finance values are the same as originally entered, and read-only
- Shipping shows batch 1's route and schedule locked, and batch 2's section editable

---

## Step 4 — Payments

**Done once per consignment, on batch 1 only.**

**What is fetched from Step 2 depends on payment mode:**
- **Advance**: fetch both the rates and the value
- **Any other mode**: fetch the consignment value only

**Add:**
- Insurance amount field
- Addenda — rather than fixed "1st addendum" and "2nd addendum" sections, an **"Add addendum" button** so any number can be added

---

## Clearance

Follows the same per-batch pattern as shipping: each batch has its own clearance, with earlier batches shown locked above.

---

## List view

**Main list — remove:**
- Requisition date
- Required date

(both move to the expanded per-item view)

**Main list — show:**
- Consignment number (`177` or `177-1`)
- Payment reference with mode concatenated (`lc-78889`)
- The **batch's own value**, not the whole consignment's
- Blue highlight when items are pending allocation

**Expanded view (single click) — show per item:**
- Job number
- MO number
- Reference number
- Weight
- Requisition date and required date
- Only the items belonging to that batch

Each batch behaves as its own row with its own details; only the payment reference is shared between them.

---

## Drafts and deletions

**Empty consignments.** If a user opens a new consignment and leaves it empty, no draft should be created. Nothing is saved until there is something to save.

**Excel export must exclude:**
- Deleted consignments
- Drafts

---

## Excel export

**One item = one row.** Every item gets its own row, carrying all of its consignment's and batch's details alongside it.

**Every field entered anywhere in the module must appear as a column** — all five steps, consignment-level, batch-level and item-level. Nothing entered in the UI should be missing from the export.

---

# Open items

Split by who decides. Section A are business questions only I can answer. Section B are technical decisions the developer should make after reading the code — but must **state explicitly** rather than choose silently.

---

## A. Questions for me to answer

**A1 — If everything is allocated in one batch, is it `177` or `177-1`?**
My requirement says it stays `177`. But if a user creates a batch containing everything, does it briefly become `177-1` and then revert? I need to say whether a suffix ever appears when there is only one batch.

**A2 — Does `177-2` exist the moment `177-1` is created?**
I said pending items are "allocated to 177-2 automatically". So it appears `177-2` is created immediately, holding the remainder. I need to confirm that, and say what `177-2` looks like in the list before anyone opens it — a real consignment with a value, or something provisional?

**A3 — What happens to numbering if a batch is deleted?**
If `177-2` is deleted, does `177-3` become `177-2`? My instinct is that numbers should stay fixed once assigned, since they appear in emails and documents. I should confirm.

**A4 — In the weight-based calculation, unit price is per what?**
`quantity × weight × unit price` implies the price is per kilogram, or per whatever the weight unit is. Confirming this changes the field label and how buyers enter it.

**A5 — What is "required vs ETA"?**
I named it for removal but did not describe it. I need to point at the actual field or column.

**A6 — Can an earlier batch be edited after it is locked?**
Batch 1 shows as locked when viewing batch 2. Does that mean permanently read-only, or read-only from that screen but still editable from its own? A shipment whose route changes after departure is a real situation.

**A7 — Do job number, MO number and reference number already exist?**
I want them in the expanded view. If they are not currently captured, I need to say which level they belong to — item, batch or consignment — and where they get entered.

**A8 — Which country list?**
All countries in the world, but there are several standard lists. Is ISO 3166 acceptable, or does the business use its own naming for particular countries?

---

## B. Decisions for the developer — state which you chose and why

**B1 — Are batches separate rows, or one consignment with batch children?**
The requirements point both ways. "One batch = one consignment" suggests separate rows; finance being shared and edited only on batch 1 suggests a parent with children. This determines the schema, the list query, and how values aggregate. Read the existing model first, choose, and explain the trade-off before writing code.

**B2 — How do the 179 existing consignments migrate?**
They were created under the old model and are live on a deployed server with real users. Propose a migration, confirm existing numbers do not change, and confirm nothing is lost. This needs an Alembic revision, not a hand-run data script.

**B3 — How is allocation enforced?**
Allocated quantity across all batches must never exceed the item's total quantity. Where is that enforced — client, server, or a database constraint? It should not be client-only.

**B4 — How are the two validation sites kept in agreement?**
`schema.ts` on the frontend and `submission_errors()` on the backend both encode submission rules, and neither knows about the other. This change touches both.

---

# Prompt to use with this document

> I need to restructure the imports module of an existing FastAPI + React ERP that is already deployed with live data — 179 consignments, 746 logistics orders and 1,370 trucking jobs on a Windows server.
>
> The attached document describes the change. The core of it: a consignment is currently one payment reference, and needs to become one batch, so a single LC arriving in two shipments becomes two linked consignments.
>
> Before proposing any implementation:
>
> 1. Read the existing imports module — models, serializers, helpers, routes, and the frontend wizard and schema — and tell me how consignments are structured today.
> 2. Answer the four questions in section B, stating which option you chose and the trade-off.
> 3. Tell me anything in the requirements that conflicts with how the system currently works, or with the logistics and trucking modules that consume imports data through `cross_module.py`.
> 4. Flag anything that would break existing data.
>
> Do not write code yet. I want the design agreed first, particularly the data model question, because it is expensive to undo once real batches exist.
>
> Context worth knowing: the database uses Alembic, so schema changes need a migration — `upgrade head` only, never `stamp`. The frontend's API URLs are compiled at build time. Validation is duplicated between `schema.ts` and `helpers.py`. The imports module feeds logistics and trucking through `cross_module.py`, and the trucking hand-off takes a point-in-time snapshot including item quantities and weights — so changing what an item's quantity means will affect it.
