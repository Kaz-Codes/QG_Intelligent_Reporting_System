# For Muhtasham — three stale claims in `chatbot_backend/backend/metadata/schema.py`

Found while building step 7 of the imports batching work
(`docs/imports-batching-design.md`). **Not fixed here**, because
`chatbot_backend/` is a separate service with its own code and its own `.env`,
and nothing under it is loaded by the ERP app — a change there would not be
covered by any check the ERP side runs.

All three are prose claims the chatbot reasons from. None of them errors; each
just makes the assistant confidently give a wrong number.

---

## 1. "every group holds exactly ONE batch" — `schema.py:224–230`

> `batches_ever` counts every batch this order has EVER held … **As of this
> writing every group holds exactly ONE batch (batches_ever = 1 everywhere), so
> a question about "how many consignments" and "how many orders" have the same
> answer today** — see 'counting: rows versus things' below for what changes
> once that stops being true.

**This becomes false the first time anyone splits an order in production.**
Step 7 shipped `POST /consignments/{id}/batches`, so that is now reachable from
the normal workflow rather than being hypothetical.

The text is careful and already points at its own successor section, so the fix
is small: the sentence needs to stop asserting the state and start telling the
reader to check it. Something like *"an order may hold several batches; count
`consignments` rows for arrivals and `DISTINCT batch_group_id` for orders, and
never assume the two agree."*

**Why it matters more than it looks:** "how many consignments did we import last
month" is exactly the kind of question this assistant is asked, and under the
old sentence it will answer with a row count while describing it as orders, or
the reverse, with no way for the reader to tell.

---

## 2. "every order item mirrors exactly one shipment line" — `schema.py:241–245`

> The ORDER LINE … **As of this writing every order item mirrors exactly one
> shipment line (ordered_quantity = allocated_quantity = that line's quantity),
> so a per-line question on either table gives the same answer today.**

Also false from the first split, and this is the more dangerous of the two.
Once an order splits, `consignment_items.quantity` is **what one arrival
carried**, not what was ordered. A question like *"how much steel bar did we
order on LC 6222"* answered from `consignment_items.quantity` returns one
batch's share of it.

The correct mapping after step 7:

| Question | Column |
|---|---|
| what was ordered | `consignment_order_items.ordered_quantity` |
| how much is committed to batches | `consignment_order_items.allocated_quantity` |
| still to be shipped | `ordered_quantity - allocated_quantity` |
| what THIS arrival carried | `consignment_items.quantity` |

---

## 3. "the old columns are still kept in step" — `schema.py:~178–185`

> …at this writing, are still kept in step with their new home — but that stops
> the moment the migration's next phase lands…

**This is already false, and has been since step 6** (commit `e5e8096`), which
deleted `helpers.sync_batch_group`. The duplicated columns on `consignments` and
`consignment_items` are no longer written by anything.

Measured on a clone of production after driving the real create route:

```
consignments created THROUGH THE APP (id > 183):
  id=184  consignments.supplier_id=None        group.supplier_id=1
          consignments.currency=None           group.currency='USD'
          consignments.instrument_number=None  group.instrument_number='RACE-NOLOCK'

app-created lines with a non-null legacy consignment_items.unit_price: 0
```

So the columns are not stale-but-tracking; they are **frozen at whatever the
Excel loader last wrote, and NULL on everything created since**. A query reading
`consignments.supplier_id` today returns nothing for every record entered
through the ERP.

The surrounding instruction — *"ALWAYS join through the group/order-item tables
… never read the old column directly"* — is right and needs no change. Only the
"still kept in step" clause is wrong, and it is the clause most likely to make a
future reader think reading the old column is merely suboptimal rather than
broken.

---

## How to exercise a change here

`chatbot_backend` is not covered by the ERP's `import app.main` check — CLAUDE.md
says so explicitly, and a chatbot change that breaks on import sails past it.
The package root is `chatbot_backend/`, so `backend.*` imports resolve only from
inside that directory, on the shared ERP venv:

```
cd chatbot_backend
../venv/Scripts/python.exe -c "from backend.metadata import schema; print(len(schema.__doc__ or ''))"
```

Then ask the assistant the two questions above — *"how many consignments arrived
last month"* and *"how much did we order on LC ___"* — against a scratch
database carrying a split order. One can be built with:

```
DB_NAME=scratch_x python -m uvicorn app.main:app --port 8011
DB_NAME=scratch_x python -m tests.batch_fixture
```
