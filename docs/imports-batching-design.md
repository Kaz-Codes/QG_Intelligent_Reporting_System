# Imports batching — design

**Status: approved; PHASE 1, STEP 2b AND STEP 6 ARE BUILT.** Alembic revision
`a1c4f27b93de` (revision A — expand), the model changes it needs, the minimum
create logic, the loaders and the `post_load` checks are written and verified
against a scratch database. **Step 2b** (submission rules removed, closing
decoupled from submitting — §3.10) shipped as its own PR ahead of step 6.

**Step 6 is now BUILT** (revision 8 below). The 14 attributes are off
`Consignment` and the 13 off `ConsignmentItem`; every read path, both revert
paths and the write path are repointed at the order and the order line. The
COLUMNS are still in the database — Revision B drops them — so the gap §4.7 is
about is still open, and everything §4.7 says about it still applies.

**Everything from §9 step 7 onward is still a proposal.** One consequence of
step 6 needs reading before step 7 starts: with `sync_batch_group` deleted, ANY
batch of an order can now rewrite that order's commercial terms through an
ordinary `PUT`, and nothing governs which one may. That is §3.8's intended
behaviour and §3.9's freeze is what constrains it — see revision 8.

---

## Changelog — revision 8 (step 6 BUILT)

**Step 6 shipped in two commits**: the two part-3 misses (`cross_module.py`'s
eager load, the imports dashboard's `supplier_id`) plus an unrelated `.env`
fix, then the attribute removal, the write-path inversion and both revert
paths. `sync_batch_group` is deleted.

| What moved | Why |
|---|---|
| **Status + §9 step 6 — BUILT, not decided** | Both still said "decided, not yet built". |
| **§4.6 — Revision B needs a step this document never had, and it is in ANOTHER TEAM'S FILE** | `ALTER TABLE consignments DROP COLUMN supplier_id` fails: `view v_import_shafts depends on column supplier_id`. Asking `pg_depend` properly found a second, `v_item_demand_picture`. Between them they read seven moved columns, neither is in `Base.metadata` (so no check this project has can see them), and both are defined in `chatbot_backend/database/semantic_views.sql`. **Worse, this is live now, not at Revision B**: the views read the ORPHANED copies, which step 6 stopped maintaining — three consignments on a scratch database already answer `China` where the group says otherwise. See §4.6. |
| **§4.7 — a SIXTH instance of the mapper mechanism, and it cost data** | `serialize_items` used `serialize_many`, which walks the mapper, so the thirteen moved item fields stopped being emitted. The client posted the draft back without them, the schema defaulted them to `None`, and the update diff wrote NULL over stored prices. Order items 40, 41 and 42 were measurably wiped. It arrived *after* the rule below was written, which is the strongest argument for the rule. |
| **A near relative, same shape, different mechanism: a moved column named without a join** | `dashboard/whole/helpers._LINE_VALUE` named `ConsignmentOrderItem` in its SELECT list without joining it. SQLAlchemy adds it to the FROM as a second unconstrained source and every line pairs with every order item: Rs 120 **trillion** against the module's Rs 29bn. It raises nothing. It was only reachable at all because `Consignment.pkr_total` is NULL on every loaded row, so that branch of the `coalesce` is the one that runs — where a booked total exists the wrong figure is never read. |
| **§3.3 — `branch_id` FANS OUT to both destinations, on write and on revert** | It is the one payload key with two homes: the group's `works_branch_id` and every order line's own `branch_id`. The destination map allows a list and every destination is taken, never the first that matches. A fallback chain was considered and rejected — it would route a header key to the wrong table and *succeed*. |
| **§3.3 — the fan-out on REVERT overwrites per-item branches, and that is accepted for now** | Undoing a header `branch_id` change writes one value to every live order line, flattening any per-line difference. Harmless today because nothing sets a per-line branch and nothing aggregates on it (§3.3's recorded gap); it becomes wrong at step 8, when per-item branches become enterable. Named here so step 8 does not have to rediscover it. |
| **§4.3 — CORRECTION: the 3 branch-less order items are NOT the COALESCE rows** | Two are genuinely branch-less consignments (134 and 137, which carry no branch at all) and one is a test record. §4.3's two blank-quantity rows (451 and 460) are present and correct in the dump at `ordered_quantity = 0.000`. The two sets were conflated in an earlier reading; they are unrelated. |
| **§4.7 — CORRECTION: the reference count of "219" was scanner-limited** | The scanner missed `reports/serializers.py`, which reaches the fields through a `ci.` alias rather than the model name. The figure was never the point — the point is that the number came from a tool whose blind spot nobody checked, and a repoint driven off that list alone would have left a module behind. |
| **The `apply_item_master_values` catch was LUCK, and should be recorded as luck** | A bulk regex repoint turned a WRITE into `line_item_name(item) = master.name` — an accessor call on the left of an assignment. It was caught because Python cannot parse that, not because anything looked for it. The same regex over a plain attribute would have produced valid code that wrote to the wrong row. There is no method here to be pleased with. |
| **`check_dashboard_consistency` compared two money figures with an exact `==`** | And passed — because no consignment in the loaded data carries a stored `pkr_total`, so both screens took the line path and matched bit for bit. The Overview prefers the stored total (Numeric 20,2) and the module re-sums the lines, so they differ by half a paisa the moment anything is saved through the app. An assertion that only holds while a column is empty everywhere is not asserting what it claims to. Now compared to the rupee, with the rounding it allows printed. |
| **The revert probe's "21 real pre-migration history rows" DID NOT EXIST** | `consignment_change_history` is empty in both dumps; nothing on the dev box has ever been edited. The 21 rows were left behind by earlier runs of the probes themselves in a database that was not rebuilt between them, and read back as though found. Two of them were the probe's own "unroutable key must raise" fixture, so a second run failed inside the code under test. The suite now seeds its history through the real routes and says so. |

---

## The two rules step 6 produced

**Seven instances of two mechanisms** turned up while building this — five of
one and two of the other. They are written as **two rules** rather than seven
anecdotes, because the anecdotes are the same bug in different clothes and the
next one will not look like any of them either.

**Five of the seven were found by RUNNING the code, not by reading it.** Of the
other two, one was predicted in revision 6 and one was found by re-reading the
same file immediately after — it would not have been noticed on its own.

That is not modesty. Every one of the five was in a file that had already been
read carefully, more than once, by someone looking specifically for this class
of problem. The rules below are worth having precisely because reading does not
reliably produce them.

*(The tally was **five instances, four of them run-found** when this rule was
first written. `serialize_items` — the one that destroyed data — turned up
afterwards, which is the strongest argument for the rule there is. The counts
above are the current ones; see the stale-counts warning that governs every
other figure in this document.)*

### Rule 1 — a mapper-derived field list silently changes scope when the mapper changes

Code that builds its field list from `inspect(obj).mapper.column_attrs` or
`{c.key for c in Model.__mapper__.column_attrs}` is asking *"what columns does
this model have right now"*. Move a column to another table and the answer
changes, the code keeps running, and it now covers a smaller set. **Nothing
raises, because nothing was ever named.**

The five:

1. **`revert_local_fields`** — walked the mapper and skipped any history key not
   in it. After the move, `supplier_id` and `exchange_rate` match nothing and
   the undo reports success without restoring them. *(Predicted, in revision 6,
   by reading — the only one of the seven that was predicted at all.)*
2. **`revert_old_values`** — the same bug one level down, for ITEM history, and
   with no loud failure at all. *(Found by reading, in revision 7 — but only
   because instance 1 had already been found and the file was re-read looking
   for its twin. Counted as read-found; it would not have been noticed alone.)*
3. **`add_in_consignment_change_history`** — records only mapper-known fields,
   so group changes were applied and never written to history: an edit that
   could not be undone, with nothing saying so.
4. **`updated_items` / `serialize_many` in the update diff** — narrowed the
   comparison, producing a `KeyError` on a key the payload had and the mapper
   did not.
5. **`serialize_items` in the RESPONSE** — the expensive one. Thirteen keys
   quietly absent from every item payload; the client posts the draft back
   without them; `None` against a stored `7650.0000` reads as a change; the
   update writes the NULL. **Real values destroyed on a normal save.**

**What to do about it, concretely:** where a field list crosses a boundary — a
payload, a history row, a serialized response — name the fields explicitly, or
derive them from something that spans both tables. `item_current_values` is the
shape that works: one definition of the flattening, shared by the serializer
and the diff, so what goes out and what comes back cannot disagree.

**The tell:** if moving a column changes what a function covers without
changing a single line of it, that function is mapper-derived and is in scope
for every schema change, for ever.

### Rule 2 — a name that is right on one side of a boundary and wrong on the other fails silently in BOTH directions

Two instances, and they are mirror images:

1. **The history key / column mismatch.** Change history recorded the
   DESTINATION column name (`works_branch_id`) while revert routes on the
   PAYLOAD key (`branch_id`). The key matched no destination, revert raised,
   and **the entire undo failed** — not just that field. Invisible in review
   because ten of the eleven group fields have identical key and column names;
   `branch_id` is the only one where the two spellings differ, so the code
   looks correct everywhere you check it.
2. **The group `setattr` no-op.** Applying a payload key straight onto a group
   with `setattr(group, "branch_id", value)` creates a Python attribute on the
   instance, writes nothing to the database, and reports success. The opposite
   failure from the same cause: instance 1 was loud about the wrong thing,
   instance 2 was silent about the right one.

**What to do about it, concretely:** translate at the boundary, in one place,
and make the translation total. `PAYLOAD_TO_GROUP` and its inverse are the
translation; `apply_group_updates` is the only thing allowed to write a group
from a payload key; an unroutable key raises and names itself. The rule is that
**a key is either routed or refused — never quietly accepted.**

**The tell:** any place two vocabularies meet and *mostly* agree. The nine
fields that match are what hide the tenth.

---

## Changelog — revision 7 (step 6 decided, not yet built)

**This revision converts proposals into decisions.** §3.2 previously said "each
of the 14 needs a recorded decision"; it now records them. §3.3 previously
grouped the 24 consumers; it now says what each group becomes and how. Three
entries below are corrections to this document rather than new decisions.

| What moved | Why |
|---|---|
| **§3.2 — the 14 counts are DECIDED, per site** | Twelve count rows, one (masters) splits three ways: supplier and branch count GROUPS, clearing agent counts ROWS. Recorded in the table there with the reason for each, and to be written into the code rather than a commit message. |
| **§3.2 — #3 and #9 publish BOTH units** | `imports_period_value` and `imports_population` keep counting rows on the tile (they must, to stay reconcilable with their buckets and their value) and additionally publish the group count. CLAUDE.md's reference rule already requires both units rather than one silently; this is an added field, not a changed one. |
| **§3.3 — the four consumer groups are DECIDED**, with the mechanics | Branch → `group.works_branch_id` (10). `required_date` splits FOUR ways, not one — a shared correlated MIN (4), Python reads over loaded lines (3), two sites that gain a genuine per-line column (2), and the ranked drill-down (2). `requisition_date` → the order item, no aggregate (3), with the write path keeping the header key. |
| **§3.3 — a consequence recorded because it is a real gap** | `consignment_order_items.branch_id` is written, back-filled and displayed, and **nothing aggregates on it**. Every branch total in the app stays one-branch-per-order. Moving branch reporting onto the item is a deliberate separate change, not something to slip into this one. |
| **§4.7 — CORRECTION: it is 219 references across 19 files, not "around 116"** | And not 24. The 24 are the sites whose MEANING changes; the attribute removal also takes the `Consignment.branch` / `.supplier` / `ConsignmentItem.item` RELATIONSHIPS with their join columns, so every `.branch.name` read goes too. It also **inverts the write path**, which §4.7 never said. |
| **§4.7 — the revert routing is TWO paths, not one** | `revert_old_values` has the identical mapper-driven silent-skip bug for ITEM history and, unlike `revert_local_fields`, **no loud failure at all**. Item history rows carry `item_code`, `item_name`, `unit_price` — all of which stop matching `ConsignmentItem`. Route to `ConsignmentOrderItem` and raise on neither. |
| **§5.2 — CORRECTION: two stale claims** | It says the masters branch count goes "through the order item"; **§3.3 settled it on `group.works_branch_id`** and §5.2 was never updated. It also names `notify_created` but misses **`app/notifications/scanner.py:629`**, which reads `Consignment.instrument_number` and `payment_instrument` — both moving to the group. |
| **§9 step 2b — DONE**, and moved ahead of step 6 | It deletes `submission_errors()` outright, so repointing its branch/supplier rules in step 6 was work about to be thrown away. It also takes `imports/helpers.py:953` off the 24-consumer list. Four findings from building it are recorded at step 2b. |
| **The count assertions need data that does not exist yet** | Every group holds exactly one batch today, so rows and groups are numerically identical at all 14 sites and no HTTP-level assertion can tell a correct choice from a flipped one. Both halves are built: a pytest suite pinning each site's unit against the compiled SQL, and hand-built fixture rows in a scratch database for the reconciliation check. |
| **Sanity check: no dashboard puts a consignment count on a tile FACE** | Every KPI face across the five dashboards is money, a percentage or days; counts live in the sub-line. The only face-value counts are bar charts (by country/supplier/works, in-process by stage), all status- or attribute-shaped, where rows is the only coherent reading. The real "reads as an LC" risk is the reference LISTS — see §3.4's note. |

---

## Changelog — revision 6 (built)

What Phase 1 changed in this document. **Three of these are corrections to
decisions that turned out to be unimplementable or under-specified as written**,
found by building them rather than by re-reading.

| What moved | Why |
|---|---|
| **§4.1 — the circular foreign key is DEFERRABLE INITIALLY DEFERRED** | As written, §4.1 could never have run. `consignment_batch_groups.founding_consignment_id` and `consignments.batch_group_id` are both NOT NULL and point at each other, so **no insert order works** — all three were tried against the real schema and all three fail (§4.1). Deferring the check to COMMIT does not weaken it; it is what makes the pair insertable at all. |
| **§4.1 — `ix_consignments_batch_group_id` dropped** | `uq_consignments_group_sequence` is a unique index leading with the same column, so it already serves lookups by group and the FK check. The second index cost a write on every save and answered nothing. |
| **§4.3 — `ordered_quantity` back-fills as `COALESCE(quantity, 0)`** | Two lines in the database carry no quantity at all, and `ordered_quantity` is NOT NULL, so §4.3 as written aborts the migration. §4.3 names the two rows. |
| **§4.3 — where the order item's demand fields come from** | `branch_id`, `requisition_date` and `required_date` are header columns today with no copy on the line. §4.3 did not say where the back-fill reads them; it reads them from the consignment. |
| **§4.7 / §9 — the attribute removal moves to the step 6 PR** | It cannot ship with the migration. Removing `Consignment.supplier_id` / `branch_id` and `ConsignmentItem.item_id` removes the join columns for `Supplier.consignments`, `Branch.consignments` and `Item.consignment_items`, so mapper configuration fails and every query in the app 500s. Steps 5 and 6 cannot be separated without a broken tree between them. |
| **§9 step 7 — the minimum create logic moved forward into Phase 1** | `batch_group_id` is NOT NULL and nothing built a group, so the first person to open the wizard got a 500. Phase 1 now builds a group of one on create and an order line per shipment line; allocation, batch creation, numbering and the freeze stay at step 7. |
| **`create_all()` is now gated on `alembic_version`** | It ran on every service start against every database. On an Alembic-managed one that is a schema change behind the migration's back — and it is what turns "started the service before migrating" into a half-changed database the migration then refuses to touch. `main.py::schema_is_alembic_managed`; CLAUDE.md, "Database migrations". |
| **A create through the real ROUTE needed autoflush suppressed** | The helpers passed on their own and the route still 500'd. `consignment` is persistent by the time its collections are assigned (the group forced a flush), so `consignment.payments = ...` lazy-loads, a lazy load autoflushes, and the autoflush inserts the lines assigned a moment earlier while `order_item_id` is still NULL. Found only by driving the HTTP path. |
| **The verification command changed** | `python -c "import app.main"` **exits 0 on a tree whose mappers are broken** — `main.py` catches and logs the startup failure. Measured against the attribute removal above. It is now `python -c "import app.main; import sqlalchemy.orm as o; o.configure_mappers()"`, in CLAUDE.md and below. |

---

## EVERY COUNT IN THIS DOCUMENT IS STALE — read this before quoting one

**183 consignments, 455 item lines, 142 locked, 179 live / 4 soft-deleted, the
15 multi-batch consignments in §0.2, the two blank-quantity rows named in §4.3,
§4.9's zero, the 97-of-179 `required_date` coverage in §6 Q2 — all of it was
measured against ONE snapshot, and that snapshot no longer matches either
machine.**

| Where | State |
|---|---|
| This document's figures | a snapshot taken while revisions 1–5 were written |
| This dev machine | **178 consignments / 450 lines**, rebuilt by `create_all` + `load_all` on 9 Sep 2026, no `alembic_version` |
| Production | **191 consignments**, `alembic_version` `3142a00a5b31` |

**They are deliberately NOT re-measured yet**, because they will move again when
the workbooks are reloaded, and a number re-measured twice is no more trustworthy
than one measured once. They are marked instead. Treat every figure here as *"as
measured then"* — illustrative of shape and order of magnitude, never as a
current fact.

**Two of them are load-bearing and must be re-checked against PRODUCTION before
revision A runs there**, because they name specific rows rather than describing a
shape:

- **§4.3's `COALESCE(quantity, 0)`** exists for two blank lines (ids 451 and 460,
  on soft-deleted consignments 179 and 182). Different database, different ids —
  and if production has blank lines this document never saw, the COALESCE still
  covers them, but the claim *"confined to two rows that hold nothing at all"*
  stops being true and stops being reviewable.
- **§4.9's count of drafts already at "Arrived at Works" is ZERO**, which is what
  makes the migration's lock statement a no-op rather than a mass state change.
  On 191 consignments it may not be zero.

Add both to the deploy checklist for revision A. Neither blocks step 6, which
runs against a scratch database and changes no schema.

---

## A LIVE BUG, FOUND HERE, THAT IS NOT THIS PROJECT'S — 172 of 178 consignments cannot be saved

**Not a batching problem, not caused by any of this work, and older than all of
it.** Found while step 6 drove the real routes; recorded here because this is
where it surfaced and it needs its own change.

**A loaded consignment cannot be re-saved. The `PUT` 422s on a field the user
never touched.**

The detail route returns `mode_of_shipment: "Sea"`. The wizard posts the whole
draft back on every save (it must — the update route diffs items against the
payload). `ConsignmentSchema` types that field as `ModeOfShipment`, which holds
`Sea freight FCL / Sea freight LCL / Air freight / Land/courier`. `"Sea"` is
none of them, so the save is rejected. Reproduced end to end against a clone.

**Nothing on the front end normalises it.** `importsMap.apiToDraft` casts with
`as ConsignmentDraft['modeOfShipment']` — a compile-time assertion with no
runtime effect — and `draftToPayload` passes the raw string through
`strOrUndef`. CLAUDE.md's claim that the map gates *"enum values against the
backend sets so an unmapped value is omitted, not 422'd"* holds for
`consignment_type` alone (`CONSIGNMENT_TYPE_TO_API`); the other five fields have
no gate. The zod draft schema rejects the value too, so the wizard is
inconsistent with itself as well.

**Measured on this dev box's 178 live consignments** (production has 191 and
will differ):

| Column | Out of enum | Detail |
|---|---|---|
| `mode_of_shipment` | **171 of 178** | Not one stored value is valid. `Sea` (93), `By Sea` (37), `Air` (23), `By Air` (5), `LCL` (1), plus 12 rows holding container specs — `1 x 20' O/T`, `3 x 20' Std.` |
| `payment_instrument` | **87 of 178** | `Advance` (71), `FOC` (6), `Exp` (5), `TT` (3), `100%LC` (1), `Contract` (1). Valid: `LC` 64, `CAD` 17 |
| `currency` | 0 | all valid or NULL |
| `consignment_type` | 0 | all valid or NULL |
| `incoterm` | 0 | NULL on every row |
| `rate_source` | 0 | NULL on every row |
| `requisition_type` | 0 | NULL on all 450 lines |

**172 of 178 live consignments (96.6%) carry at least one such value.**

**It has gone unnoticed only because nobody has edited a loaded consignment
yet** — which is exactly the condition that is about to end.

**Deliberately NOT fixed in step 6, and it is not a one-line coercion.** Each
available fix is a decision somebody has to make:

- **Gate at `apiToDraft`** (drop what does not match): one line per field, and it
  blanks `mode_of_shipment` on 171 rows the moment anyone saves. Silent data
  loss dressed as a fix.
- **Normalise the data**: `Sea` → FCL or LCL is a business call and is not
  inferable; the 12 container-spec rows are not a shipment mode at all and
  belong in a different column.
- **Widen the enums**: `TT` is a real payment method the enum simply lacks;
  `FOC`, `Exp` and `Contract` need someone to say what they are. Adding a value
  is a one-line change by design (CLAUDE.md, "Enums"), but *which* values is the
  question.

All three touch data the business owns, so this stops here and goes back rather
than being resolved silently.

---

## Verifying this work

```
DB_NAME=<a scratch database> python -c "import app.main; import sqlalchemy.orm as o; o.configure_mappers(); print('ok')"
```

**Two things about that command, both learned the hard way.**

`configure_mappers()` is the part that matters. The bare import exits 0 when a
relationship has lost its join column, because `main.py` builds tables inside a
retry loop that catches whatever startup raises and writes it to the log. Every
phase after this one moves mapped attributes around, so a check that cannot see a
broken mapper is not a check.

`DB_NAME` matters too. The import runs `create_all`, which creates any table the
models have and the database does not — so running it after adding a model
applies half a migration to whatever database `.env` points at. Point it at a
scratch database whenever the change adds a table.

---

## Changelog — revision 5

**§8 is empty. The design is complete.**

| What moved | Why |
|---|---|
| **§8 closed** | The four Step 3 fields are all per batch, `clearing_agent_id` included — a per-batch field, not Tier 2. |
| **§1.2, §3.10 rewritten** | `is_closed()` becomes the one-part test: status alone. Submit sets `record_state` and nothing else. |
| **§3.10 — a correction that changes the work** | *"Remove the locking side effect from `submit_consignment.py:75-76`"* — **`submit_consignment.py:77` is the ONLY place `is_locked` is ever set to True in imports.** The update route only reads it (`:197`). So locking does not *move* to the status change; it has to be **written there**, or the closed lock ceases to exist. §3.10. |
| **§1.2 — a CLAUDE.md error** | CLAUDE.md rule 8 says `is_locked` "is set on that update" when status reaches Arrived at Works. **It is not.** No update route in any of the three modules sets it. All 142 locked rows were locked by the loader, never by the app. §1.2. |
| **§4.9 new — the count you asked for** | **Zero.** No draft is at "Arrived at Works", live or soft-deleted. The one-part and two-part tests agree on all 183 rows today. The migration still carries the lock statement, for the reason in §4.9. |
| **§3.10 — the dialog moves** | Onto the status change to Arrived at Works. Recorded: **it can warn about the lock but cannot name what is missing**, because `missing_fields` is gone. |
| **§5.1 expanded** | **The three-module divergence is written down** — imports alone gets the one-part test and no submission rules. Goes in CLAUDE.md in the same PR. `SubmitRequirements.tsx` stays; imports stops importing it. |
| **§7 item 6b rewritten** | The risk changes shape rather than disappearing — the irreversible act moves from submit to the status change, and loses the ability to say what is incomplete. |

---

## Changelog — revision 4

Your six answers applied. **Two of the premises turned out to be wrong**, both in
ways that reduce the work rather than increase it, and one confirmation came back
negative.

| What moved | Why |
|---|---|
| **§3.9 split into two tiers** | Hard freeze (valuation) and admin-overridable freeze (commercial), per answer 2. **The justification you asked me not to write down is not written down** — §3.9 records the commercial-fact reason instead. |
| **§3.3, §6 Q2 amended** | Requisition date moves to the item's own column in the report filters — no aggregate. §5.2 now states that **existing report row counts will change, correctly**, and why. **The third site takes the same move**; it is a serializer field, not a filter. |
| **§4.8 new** | `po_date` removed. **`procurementLeadDays()` is already dead code** — defined at `schema.ts:541` and called from nowhere. It does not die with the column; it died before it. Full consumer list, and the one thing worth keeping by another route. |
| **§3.10 new** | **Submission rules removed entirely.** Every consequence you listed, plus one you did not, which is the reason this section is long. |
| **§3.10 — the confirmation is NEGATIVE** | You asked me to confirm nothing in the submit path carries lock behaviour. **It does.** `submit_consignment.py:76` sets `is_locked`. Removing the gate makes an empty consignment at "Arrived at Works" instantly lockable by any user, admin-only to undo. §3.10 and §7 item 6. |
| **`missing_only` — premise corrected** | It is **not** driven by `submission_errors()`. `helpers.py:218` filters `record_state == 'draft'`, with a comment saying so, and CLAUDE.md documents it as "`missing_only` (= draft)". It keeps working unchanged. The problem is its *name*, not its source. §3.10. |
| **§6 B4 closed, not answered** | Recorded as dissolved by the decision rather than solved. |
| **§4.7 amended** | Old shared-field history keys are **routed to the group, not raised on** — answer 1. The ambiguity I was guarding against does not exist, because every pre-migration consignment is a group of one. |
| **§8** | Down to one item: the four Step 3 fields, now named. |

---

## Changelog — revision 3

Your eight answers applied. What changed, and the two things they opened.

| What moved | Why |
|---|---|
| **§0.3, §0.4 closed** | `177` is the founding consignment's id, so all 179 existing numbers stay correct with no back-fill. A4 is answered by answer 2. |
| **§3.5 accepted** | The suffix reversal is agreed. **The decisions table in §3.5 no longer says "renumber ascending"** — it now records permanent `batch_sequence` suffixes as the decision. |
| **§3.6 rewritten** | The 15 historical multi-batch consignments are **never converted**. No report, no conversion path, no later drop of `batch_no`. The column stops being written and stays readable. Build-order item 10 is deleted. |
| **§3.9 new** | **The finance freeze.** Your answer 4 opened a real hole — the group is not lockable, so a rate edit could restate a closed batch's stored `pkr_total`. The rule is written properly here rather than assumed, with what enforces it and where. **I recommend a wider freeze than you proposed, and exclude payments from it** — reasons in §3.9. |
| **§4 restructured** | **Two revisions, expand-and-contract**, per answer 7. §4.7 names what stops writes to the orphaned columns during the gap, and it is not what I would have guessed. |
| **§4.7 new, and it found a bug** | Removing the attributes from the model is a real control, because `updated_fields` and `revert_local_fields` both walk `mapper.column_attrs`. **The same fact breaks revert across the migration boundary, silently.** Not something you asked about; §4.7 and §7 item 5. |
| **§6 Q1 amended** | Answer 2 gives weight-priced items **their own per-kilogram price column** rather than overloading `unit_price`. That is better than what I proposed and it removes the dynamic-label problem — §6 Q1. |
| **§6 Q2 closed** | Step 1 display removed; list column kept, defined as the **earliest** required date across the batch's items, adopting `DELAY_GRACE_DAYS`. |
| **§3.3 amended** | `works_branch_id` becomes the header-level branch the consumers point at. **You asked whether that breaks any of the 24: it covers 10 of them and leaves 14 untouched**, because those 14 are date consumers, not branch consumers. Breakdown in §3.3. |
| **§8 replaced** | Five of seven answered. Two remain from my list, plus one remnant and two new ones this round opened. |

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
| **A3** | *"My instinct is that numbers should stay fixed once assigned, since they appear in emails and documents"* | ~~Renumber ascending~~ → **permanent `batch_sequence` suffixes** | **RESOLVED in favour of A3.** The decisions table was reversed and the reversal accepted. §3.5. |
| **A4** | Unit price per what? | *(now answered)* | **RESOLVED.** Weight-priced items get their own **per-kilogram price column**; `unit_price` keeps its single meaning. §6 Q1. |
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

**RESOLVED — `177` is the founding consignment's id.** A group's number is the
`consignments.id` of the batch that founded it. That is already what the screen
shows (`importsMap.ts:243`, `systemId: String(c.id)`), so **all 179 existing
numbers stay correct with no back-fill**, and consequence 3 above dissolves.

Batch 2 gets its own primary key, which is **never displayed**: the group
supplies the number, the row supplies the identity. Two things follow that are
worth stating because they are easy to get wrong later:

- **`consignment_number` is not a stored column on the group** — it is
  `group.founding_consignment_id`, so there is nothing to keep in step and
  nothing that can drift. The group needs that one FK, added when the group row
  is created and never changed. It is *not* the same as "the batch with
  `batch_sequence = 1`", because that batch can be deleted while the number must
  survive (§3.5).
- **The number and the id of a later batch are different integers**, so nothing
  may derive a display number from `consignment.id` any more. Today three places
  do exactly that — `cross_module.py:182` and the two dashboard copies. §3.4 is
  what fixes them, and it is now load-bearing rather than tidy-up: after this
  change, rendering `f"Import {consignment.id}"` on batch 2 prints a number that
  belongs to no consignment anyone can look up.

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
| `is_locked` | **`POST /{id}/submit` — the only site. See below.** | `POST /{id}/reopen`, **admin only** | update/submit return **423** |
| `is_deleted` | `DELETE /{id}` | `POST /undo-delete/{id}` | Hidden from lists unless `include_deleted` |

The closed test is **two-part**, `app/imports/helpers.py:739`:

```python
def is_closed(consignment):
    return (consignment.current_status == Status.ARRIVED_AT_WORKS.value
            and consignment.record_state == "submitted")
```

A draft may sit at "Arrived at Works" and remain editable. Submitting never
locks; only closing does. **§3.10 replaces this with a one-part test.**

#### A CLAUDE.md error, found while costing that change

CLAUDE.md rule 8 says:

> *"a consignment closes when its status reaches 'Arrived at Works'; `is_locked`
> (`server_default false`) is set on that update"*

**It is not set on that update.** `update_consignment.py:197` only *reads*
`is_locked`, to reject an edit on an already-locked record; it never writes it.
The complete set of writes in imports is:

| Site | Writes |
|---|---|
| `routes/submit_consignment.py:77` | `is_locked = True` — **the only place it is ever set** |
| `routes/reopen_consignment.py:52` | `is_locked = False` |

All three modules are identical in this respect — `logistics/routes/submit_consignment.py:71`
and `trucking/routes/submit_consignment.py:71` are the only lock sites in theirs,
which is what CLAUDE.md says correctly *for those two* ("Only `POST /{id}/submit`
sets `is_locked`") and incorrectly for imports.

**So no consignment in production has ever been locked by the application.** All
142 were locked by the loader, which writes `record_state` and `is_locked`
directly from the status (`load_05_consignments.py:117`, `terminal_flags`). The
app-side lock path exists and has never fired on a real record — which is worth
knowing before relying on it, and is why §3.10's change is larger than it looks.

Rule 8's wording is corrected in the same PR (§5.1).

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

**Dashboard counts — the real cost. DECIDED, per site.**

An LC split in two counts as **2** where today it counts as 1. Each of the 14
sites therefore has to say whether it means *how many LCs* (count distinct
`batch_group_id`) or *how many arrivals* (count rows). Line numbers are the
current tree; several drifted in Phase 1.

| # | Site | Figure | Unit | Why |
|---|---|---|---|---|
| 1 | `dashboard/imports/helpers.py:73` | `source_coverage` — total | **rows** | Its own docstring settles it: the coverage denominator has to be the population on screen, and the screen lists batches. |
| 2 | `dashboard/imports/helpers.py:78` | `source_coverage` — in-period | **rows** | Numerator of #1. A different unit makes the percentage meaningless. |
| 3 | `whole/helpers.py:264` | `imports_period_value` — `consignments` | **rows**, + group count published | Value is summed per batch row, so a group count beside a row-summed value gives a false average. See "both units" below. |
| 4 | `whole/helpers.py:292` | `imports_value_undated` — count | **rows** | The complement of #3's population. Dated + undated must add back to it. |
| 5 | `whole/helpers.py:310` | `imports_date_coverage` — total | **rows** | A completeness ratio over the same population as #3. |
| 6 | `whole/helpers.py:350` | `imports_in_process_by_stage` | **rows** | Groups is not expressible here: status is per batch, and two batches of one LC are legitimately at different stages. |
| 7 | `whole/helpers.py:556` | `shipments_handled` — import total / datable | **rows** | The figure's name is the unit. A batch *is* a shipment handled. |
| 8 | `whole/helpers.py:575` | `shipments_handled` — in-window | **rows** | Same figure as #7, windowed. |
| 9 | `whole/helpers.py:792` | `imports_population` — total + buckets | **rows**, + group count published | The buckets are status-keyed so they can only be rows (#6). The total must match its buckets AND equal #3. |
| 10 | `whole/helpers.py:860` | `imports_coverage` — total | **rows** | The Overview's twin of #1. |
| 11 | `whole/helpers.py:863` | `imports_coverage` — in-period | **rows** | The Overview's twin of #2. |
| 12 | `whole/references.py:518` | `imports_delayed_references` — total | **rows** | Must equal `imports_delay`'s count (`:821`–`823`, already row-shaped). A batch arrives late on its own account. |
| 13 | `imports/helpers.py:273` | list pagination total | **rows — forced** | It counts the rows the page returns. Groups here breaks paging, not merely the number. |
| 14 | `masters/helpers.py:250` | `_grouped_count`, 3 callers | **split** | The column's new home decides it — below. |

(`whole/helpers.py:270`, `whole/references.py:652`, `imports/helpers.py:316`
count items and history rows and are unaffected.)

**#14 splits three ways**, because one function serves three masters whose
columns land in different places:

- `:161` **supplier** → **groups**. `supplier_id` lives on the group, so the
  query moves to `consignment_batch_groups` and counting its rows *is* counting
  groups. "Used by N orders."
- `:164` **branch** → **groups**, on `group.works_branch_id`. The clearest case
  in the set: splitting one LC must not inflate a branch's usage.
- `:190` **clearing agent** → **rows**. `clearing_agent_id` stays per batch
  (§3.3, Step 3). An agent who cleared two batches of one LC did two
  clearances, and **understating that in a deactivation guard fails in the
  dangerous direction** — it invites someone to switch off an agent the
  business is still using.

**Twelve rows, two groups, one rows-on-a-per-batch-column. The shape of that
answer is itself worth stating:** every imports *dashboard* figure comes out as
rows because all of them are arrival- or status-shaped. The only
commercial-shaped counts in the whole system are the masters usage counts.

**#3 and #9 publish BOTH units.** "Rs 29bn across 14 consignments" turns
ambiguous the moment one of those is a second batch. The tile keeps counting
**rows** — it has to, to stay reconcilable with its buckets and its value — and
the payload additionally carries the group count, so a panel can read *"2
batches across 1 order, 3 lines"*. This is CLAUDE.md's existing reference rule
(*"Both units are published, never one silently"*) applied one level up, and it
is an added field rather than a changed one.

**Is any of this read as "LCs" on screen? No — checked, not assumed.** Across
all five dashboards every KPI tile FACE is money, a percentage or a day count;
consignment counts live in the sub-line beneath, which is exactly where the
second unit lands. The only places a count is the primary number are bar charts
(Consignments by Country / Supplier / Works, Imports in process by stage) and
all of them are status- or attribute-shaped, where rows is the only coherent
reading. The genuine "reads as one LC shown twice" risk is not a count at all —
it is the reference LISTS, which label each import row by `instrument_number`,
so two batches of one LC render as two rows with an identical reference. That is
§3.4's job (`consignment_number()` / `payment_reference()`, build-order step 1,
**not yet shipped**), not a count decision.

**The decisions go in the CODE, not in a commit message**, and each is asserted
so a later change cannot flip one silently — see "Proving the count decisions"
below.

#### Proving the count decisions

Given CLAUDE.md's history of two screens disagreeing about one metric, the
group-vs-row choice is asserted rather than trusted. **Both halves are needed,
and the reason is a fact about the data:**

**Every group in the database holds exactly one batch.** Revision A gave each
existing consignment a group of its own, and step 7 has not built batch
creation yet. So at all 14 sites `count(rows)` and `count(distinct group)`
return the identical number, and **no assertion driven through HTTP against
the real data can distinguish a correct choice from a flipped one.** It would
pass either way — the "both screens looked right" failure, in the very test
written to prevent it.

- **A pytest suite pins each site's unit**, against the compiled SQL rather
  than against data. Pure, no database, runs in the default suite — so it is
  the one that actually fails on a later edit.
- **`tests/check_dashboard_consistency.py` proves the screens reconcile**,
  against a scratch database carrying **hand-built fixture rows**: one group
  with two batches, which is the only state in which rows and groups differ.
  Scratch database only; it never touches an operational table.

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

#### `works` becomes `works_branch_id`, and it absorbs the header branch

**Decided.** `works` becomes `works_branch_id`, a proper FK to `branches`, on the
group. This is not a cosmetic change of type — **it changes what the field is
for.** The requirements move branch to the item level, so
`Consignment.branch_id` has no successor at header level; `works_branch_id`
becomes the header-level branch, and items carry their own `branch_id` for the
per-item variation.

`Consignment.branch_id` is therefore **dropped**, which makes it a twelfth
column removed from `consignments` (revision 2 counted eleven). The back-fill is
trivial and lossless: copy `Consignment.branch_id` into the group's
`works_branch_id`, which is populated on **177 of 179** rows. Two consignments
have no branch — the `QH` rows CLAUDE.md records as deliberately branch-less —
and they stay branch-less.

**You asked whether this reading breaks any of the 24 consumers. It covers 10
and leaves 14 untouched**, because the 24 are not all branch consumers:

| | Count | Sites | Effect |
|---|---|---|---|
| **Branch** | **10** | `imports/helpers.py:204`, ~~`:953`~~; `dashboard/imports/helpers.py:149`, `:208`; `whole/references.py:89`, `:521`, `:533`, `:629`, `:657`; `masters/helpers.py:164` | **Covered.** Repoint from `Consignment.branch_id` to `group.works_branch_id`. |
| **`required_date`** | **11** | `serializers.py:101`; `dashboard/imports/helpers.py:43`, `:125`; `dashboard/imports/calculations.py:631`, `:768`; `whole/helpers.py:71`, `:169`, `:821`, `:823`; `whole/references.py:501`, `:503` | **Not covered.** No header-level successor. Needs the earliest-across-items rule from §6 Q2. |
| **`requisition_date`** | **3** | `serializers.py:100`; `reports/helpers.py:165`, `:167` | **Covered, and by a better route than an aggregate** — see below. |

`imports/helpers.py:953` was `submission_errors`'s branch check and is **struck
out: step 2b deleted the function**, so the branch group is 9 live sites, not
10. That is the whole reason 2b went first.

So the works answer is a real simplification — it removes the hardest third of
the problem — but **it does not make §7 item 2 go away.** Fourteen date
consumers still read a column that is moving down a level, and eleven of them
now need the "earliest across the batch's items" rule applied consistently
rather than only in the list column.

#### What each group BECOMES — decided, revision 7

The three rows above say where each consumer points afterwards. This says how,
because the mechanics differ inside a group and one of them hides an N+1.

**A — Branch → `group.works_branch_id`.** One substitution, two forms. Seven
are SQL joins (`outerjoin(Branch, Branch.id == Consignment.branch_id)` in
`dashboard/imports/helpers.py:149`, `:208` and `whole/references.py:89`, `:521`,
`:533`, `:629`, `:657`) and become a join through `ConsignmentBatchGroup` — an
extra join, not a subquery. Two are filters reading the group directly
(`imports/helpers.py:204`'s list filter, `masters/helpers.py:164`'s usage
count, the latter counting groups per §3.2 #14).

**B — `required_date` → earliest across the batch's order items.** §6 Q2 fixes
the rule (`min(order_item.required_date)` over the batch's live lines, ignoring
lines with none). Applying it splits four ways:

- **B1 · a shared correlated MIN, as a SQL column (4).**
  `dashboard/imports/helpers.py:43` and `whole/helpers.py:71` (the two
  `DATE_FIELDS` map entries), and `whole/helpers.py:821`, `:823`
  (`imports_delay`'s `measurable` / `late`). **Defined once and imported, never
  restated** — these four decide window membership and the Delayed tile, so two
  spellings here is precisely the drift CLAUDE.md is a record of.
- **B2 · Python reads over already-loaded lines (3).**
  `dashboard/imports/calculations.py:631` (`delivery_delay`), `:768`
  (`category_delays`), and `serializers.py:101`. **This is where the N+1
  lands**: all three walk the whole filtered set, so
  `selectinload(Consignment.items).joinedload(ConsignmentItem.order_item)` must
  be added to `fetch_consignments`, `fetch_filtered_consigments` and
  `fetch_consignments_page` in the same change. `serializers.py:101` is the one
  §6 Q2 warns is easy to miss: the list payload carries no lines, so the SERVER
  has to supply the minimum or the front end's `requiredDelayDays` silently
  reads nothing while keeping its signature.
- **B3 · two sites that GAIN a real per-line column (2).**
  `dashboard/imports/helpers.py:125` and `whole/helpers.py:169`
  (`line_date_column` / `_imports_line_column`) today fall back to the header
  for `required_date`, with a comment saying no line equivalent exists. One now
  does. They stop being fallbacks and filter `order_item.required_date` per
  line — so **window membership under `date_field=required_date` gets strictly
  more precise and row counts on that filter will change.** Correct, and stated
  rather than discovered.
- **B4 · the ranked drill-down (2).** `whole/references.py:501`, `:503`
  (`days_late`). **Keeps the batch minimum**, deliberately: the rows are
  consignments and the list must total the KPI it drills into (#12), which is
  the failure CLAUDE.md is a record of. If the reader needs to know WHICH line
  is late, that belongs in the row's detail string, not in what the row counts.

**C — `requisition_date` → the order item's own column, no aggregate (3).**
`reports/helpers.py:165`, `:167` move from `Consignment.requisition_date` to
`ConsignmentOrderItem.requisition_date`; `_MODEL` already queries the line table
and `_JOINS` back to the header, so it is a join hop. Row counts narrow,
correctly — the same precision gain CLAUDE.md records for the shaft and category
filters.

`serializers.py:100` leaves the header payload and appears per line. **The WRITE
path keeps accepting the header key**, fanning it onto every order item exactly
as Phase 1's `sync_order_item_from_line` already does. Without that, step 6
breaks the wizard (`importsMap.ts:257`, `:454`, `:549` read and write it as a
header field) and step 8 would have to ship alongside it.

#### The consequence nothing aggregates on

**`consignment_order_items.branch_id` is written, back-filled on all 455 rows,
and displayed — and nothing aggregates on it.** Branch-grouped figures all read
`group.works_branch_id`, so every branch total in the app stays
one-branch-per-order, exactly as it is today.

That is the decision (§7 item 2 originally proposed grouping by item and this
section settles it the other way), and it is recorded here rather than left to
be noticed because it is a real gap rather than a detail. **If the business
later wants branch reporting to follow the item, that is a deliberate separate
change** — it moves every branch figure in the app — and not something to slip
into this one.

**Two further consequences of putting the branch on the group rather than the
batch**, neither of which is a defect but both of which change a number:

1. **A branch-grouped figure now attributes every batch of an LC to one branch.**
   That is correct, and it is the answer to revision 2's §8 question 3 for
   branch — but it interacts with §3.2: the query still returns one row per
   batch, so an LC split in two contributes **twice** under that branch. Whether
   each branch-grouped site should count rows or distinct groups is the same
   14-site decision, and the branch sites now inherit it.
2. **`masters/helpers.py:164` and `:250` — the Branch "used" count — should count
   groups, not batches**, or splitting one LC inflates a branch's usage. This is
   the clearest case in the whole set for the "commercial-shaped figures count
   groups" default in §3.2.

#### `requisition_date`: no aggregate — the filters move onto the item

**Decided, and it is a better answer than the earliest-across-items rule applied
to `required_date`.** Reports already query `ConsignmentItem` and join back to
the header (`app/reports/helpers.py::_MODEL`, `_JOINS`), so the date filters at
`reports/helpers.py:165` and `:167` simply move from
`Consignment.requisition_date` to the order item's own column. **No aggregate is
computed and none is needed.**

**Existing report row counts will change, and the change is a correction.**
Today a date range on requisition date returns whole consignments, so a
consignment whose lines were requisitioned months apart hands back **every** line
— including lines requisitioned well outside the requested window. Afterwards a
line qualifies on its own date. Narrower results, and right ones.

This is the same precision gain CLAUDE.md already records for the shaft and
category filters when reports moved to one row per line: *"filters that used to
mean 'does ANY line of this consignment match' now mean 'does THIS line match' —
more precise."* Requisition date joins that set.

**The third site takes the same move, and it is not a filter.**
`app/imports/serializers.py:100` emits `requisition_date` as a header field on
the consignment payload. Under §3.7 there is no header value to emit, so **the
field leaves the header payload and appears per line instead**, alongside
`required_date` (`:101`) and the other per-item fields the requirements move into
the expanded view. Nothing aggregates it. The list stops showing it at all, which
is what the requirements ask for — *"Main list — remove: requisition date,
required date"*.

Note the asymmetry with `required_date`, which is deliberate: that one keeps an
aggregate (**earliest**, §6 Q2) because the delay column is a header-level
comparison across rows and has to show one number. `requisition_date` has no such
consumer — it is a filter and a display, both of which work better per line.

**Two things the requirements do not cover, and I am not inventing:**

- `po_date` is **removed** — decided. Full consumer list and what survives in
  §4.8.
- `clearing_agent_id`, `mode_of_shipment`, `loading_port_id` and
  `delivery_port_id` are named in none of the four lists. They are Step 3
  fields, so I have treated them as **per batch** — a different port or agent
  per shipment is normal. The one remaining item in §8.

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

**`177` is the founding batch's id** (§0.4), so `consignment_number()` reads
`group.founding_consignment_id` and never `consignment.id` — the distinction
that matters on batch 2, whose own id is not its number.

### 3.5 Numbering permanence — DECIDED: permanent suffixes

**This is settled.** The decisions table said "batch deleted → remaining batches
renumber ascending"; that has been **reversed and the reversal accepted**. The
governing decision is now:

| | |
|---|---|
| Batch deleted | **Remaining batches keep their numbers. Nothing renumbers, ever.** |

The reasoning is kept below because it is the justification for a rule that will
look odd to whoever next reads a list with a gap in it.

Under a `RANK()` over live batches, a
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
3. ~~It contradicts a decision you told me not to reopen.~~ **Withdrawn — the
   decision was reopened and reversed. This is no longer a cost.**

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

### 3.6 What happens to `batch_no` — DECIDED: frozen, never converted

**This is settled, and it is stronger than what revision 2 proposed.** Revision 2
suggested a report so operators could split the 15 historical multi-batch
consignments by hand. **That is dropped. They are never converted.**

The rule:

- **`batch_no` stops being written.** It is removed from the item form, per the
  requirements.
- **`batch_no` stays readable on existing rows**, in the expanded per-item view,
  as the historical record of how those consignments were split.
- **The column is never dropped**, and there is no conversion path and no
  conversion report.

**Why not convert, even though the data is real.** Roughly twelve of the fifteen
are locked and closed (at the 79% rate in §1.2). Converting them would mean an
admin reopening consignments whose goods have already arrived, and restating
`foreign_total` and `pkr_total` on figures that have already been reported. That
is what CLAUDE.md rule 4 exists to prevent — *"the money totals are STORED
(recomputed on save) so a later rate change or edit can't restate a printed
report"* — and no operational benefit justifies it. Those consignments are
finished. The record of how they were split is worth keeping; re-litigating
their arithmetic is not.

**Consequence to state plainly:** `batch_no` becomes a permanently frozen
legacy column. Anyone reading the schema later will find a column nothing writes,
and the temptation will be to drop it in a cleanup. It needs a comment on the
model saying it is deliberate, and a line in CLAUDE.md, or it will be removed by
someone being tidy.

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
| Money | `price_basis`, `unit_price`, `weight_unit_price`, `unit_weight` (§6 Q1) |
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
by weight    ->  line.quantity * order_item.unit_weight * order_item.weight_unit_price
```

Note the two different price columns — that is answer 2, and it is better than
the single overloaded column revision 2 proposed. §6 Q1.

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

> **Revision 7 — and the same distinction applies to WRITING, so record it
> before the transitional mirror sets a precedent.**
>
> Step 6 adds `helpers.sync_batch_group`, which mirrors the shared values from
> **batch 1 only** onto the group. That is correct for a MIRROR: a mirror needs
> exactly one source, and batch 1 is the only non-arbitrary choice.
>
> **It is not the answer to "who edits the order", and it must not become one.**
> Any batch may be deleted, the founding one included. Under a batch-1 rule as a
> permanent design, an order whose first shipment was deleted would have
> commercial terms nobody could ever correct — and it would fail silently, since
> the write would simply not propagate.
>
> **Step 7 edits the group AS THE GROUP**: one row, addressed directly, with the
> §3.9 freeze as the only thing standing in front of it. No batch is privileged.
> The mirror is temporary and disappears with the columns it mirrors from — once
> the shared attributes come off `Consignment` there is one copy again and
> nothing to propagate, which is the whole point of (i).

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

### 3.9 The group freeze — closing the hole answer 4 opened

Adding a batch to a locked group is now allowed to any user, always, with no
admin and no reopen. That is right operationally, and it opens exactly the hole
you identified: **the group is not lockable, so a user with ordinary edit rights
can change a group-level value while a batch in that group is closed.**

The worst case is concrete. Batch 1 closes at rate 278.50; its `pkr_total` is
stored and has been reported. Somebody edits the group's `exchange_rate` to
281.00 in order to book batch 3 correctly. Batch 1's **stored** total does not
change — its update route 423s, so `recompute_derived()` never runs on it — but
the group now says 281.00 while batch 1's stored figure says 278.50. Every
figure derived at read time from `group.exchange_rate` disagrees with the stored
one, and neither is wrong for its own basis. That is CLAUDE.md's
"One metric, one definition" failure, reached from a new direction.

Note that the danger is **not** that a closed batch gets silently restated — the
existing row lock already prevents that. It is that stored and derivable values
silently diverge, and there is nothing on screen to say which a given number
came from.

#### The rule

> **A group's fields freeze the moment the FIRST batch in that group closes**,
> in **two tiers**. Closed means `is_closed()` — which per §3.10 is now
> **status "Arrived at Works", and nothing else**.

**The one-part test makes this freeze stronger, and that is the right direction.**
Under the two-part test the group's exchange rate would have stayed editable
while a batch's goods sat at the factory, simply because nobody had pressed
Submit on it — the money could be restated on a consignment that had
demonstrably arrived. Freezing on the arrival itself ties the rule to the event
that makes restatement wrong, rather than to an administrative gesture that may
never happen.

**Tier 1 — HARD FROZEN. Nobody, including an admin. No override.**

`exchange_rate`, `rate_booked_on`, `rate_source`, `currency`.

These are the **valuation inputs**. Changing any of them after a batch closes
restates that batch's stored `pkr_total`, which is exactly what CLAUDE.md rule 4
exists to prevent: *"the money totals are STORED (recomputed on save) so a later
rate change or edit can't restate a printed report."* A rate that has been
reported against is a historical fact, not a field. There is no override because
there is no legitimate case for one — a genuinely rebooked rate applies to the
*next* LC, not retrospectively to this one.

**Tier 2 — FROZEN FOR NORMAL USERS, admin-overridable through the existing
reopen path.**

`supplier_id`, `origin`, `consignment_type`, `incoterm`, `instrument_number`,
and `works_branch_id`.

**These are commercial facts, not valuation inputs.** They describe who the
counterparty is and under what terms; none of them feeds a stored money total.
Correcting a wrong one on a three-batch LC is **normal work**, not an
exceptional recovery — the record should not have to stay permanently wrong
because one shipment has landed. So they freeze against casual edits, since a
closed batch was cleared against these values and they should not move without
deliberation; and an admin reopening a batch *is* that deliberation.

The override is the **existing `POST /{id}/reopen`**. No separate group-level
reopen to build, and no second unlocking concept to learn: reopen a batch, the
group unfreezes, fix the field, close it again.

> **A note for whoever maintains this.** Tier 2 is **not** a guard against
> typos, and must not be documented as one. It would be a poor guard anyway:
> CLAUDE.md rule 13 permits inline supplier creation with `verified=False`, and
> a user can pick the wrong supplier from an entirely correct dropdown. The
> justification is the one above — commercial facts versus valuation inputs —
> and the two tiers make no sense read any other way.

**Not frozen at all — the payment process.** `insurance_amount`, the
`payment_addenda` rows, and every `Payment` row. **Confirmed:** an LC is retired
*after* the goods arrive, which is why `opening_or_retirement_date` and
`Payment.status` exist, so payment activity following the first batch's close is
the normal course of the process rather than an edit to a settled record.
Freezing them would lock the payment screen at exactly the point it starts being
used.

**Nor are the system-controlled columns.** `batches_ever` still increments and
new batches still attach, because answer 4 requires it. The freeze governs
user-editable fields, not bookkeeping.

**`payment_instrument` is deliberately absent from both tiers.** It is the
paired half of `instrument_number` and belongs in Tier 2 with it — but it is
also part of the payment reference display (§3.4), and Step 4 is unfrozen. It
should be Tier 2; noting it here because "the instrument is frozen but the
instrument number is not" is the kind of split that gets implemented by
accident.

#### Why two tiers rather than one

A flat freeze is simpler to implement and worse to live with. The two sets fail
differently and deserve different answers.

Restating a reported `pkr_total` is **not recoverable by correcting it** — the
figure has already gone into a report someone acted on, and changing it now
produces a second version of history rather than a fix. That is why Tier 1 has
no override: the right response to a wrong rate is a note, not an edit.

Naming the wrong supplier is **fully recoverable by correcting it**, and leaving
it wrong is the worse outcome — every future report, every supplier-wise total
and every Pareto chart carries the error forward. A permanent freeze on that set
would optimise for a risk that does not exist at the cost of one that does.

#### What enforces it, and where

**Not a database constraint.** The freeze condition is "does any sibling row
satisfy `is_closed()`", which is cross-row, so a CHECK cannot see it — the same
limitation as B3, for the same reason.

**A helper next to the one it mirrors**, in `app/imports/helpers.py`, beside
`is_closed()`:

```python
HARD_FROZEN = {"exchange_rate", "rate_booked_on", "rate_source", "currency"}
ADMIN_FROZEN = {"supplier_id", "origin", "consignment_type", "incoterm",
                "instrument_number", "payment_instrument", "works_branch_id"}

def group_is_frozen(group):
    return any(is_closed(b) for b in group.consignments if not b.is_deleted)

def frozen_fields_for(group, user):
    """Which group fields this user may not write right now."""
    if not group_is_frozen(group):
        return frozenset()
    return HARD_FROZEN if user.is_admin else HARD_FROZEN | ADMIN_FROZEN
```

**Note what `frozen_fields_for` does NOT do: it never returns an empty set for an
admin on a frozen group.** Tier 1 survives `is_admin`, which is the only place in
this application where that is true — every other check in `authorize()` passes
unconditionally for an admin. That asymmetry is deliberate and needs a comment at
the definition, or the first person to read it will assume it is a bug and
"fix" it.

Derived, not stored. A stored `frozen_at` column would be a denormalisation that
can drift from the batch statuses it summarises, and this design has already
rejected exactly that shape twice (§3.5's suffix, §3.8's shared fields). A group
holds a handful of batches and they are loaded anyway, so deriving it costs
nothing.

**Called from the group update path, returning 423** — the same status the row
lock returns, so the front end's existing "this record is closed" handling
applies unchanged and there is no second locked-state vocabulary to learn.

**Two details that are easy to miss and expensive to omit:**

- **`serialize_consignment` must publish it.** The serializer already returns
  `missing_fields` so a disabled Submit and a failed submit cannot disagree
  (CLAUDE.md says so in as many words). The freeze needs the same treatment —
  a `group_finance_frozen` flag on the payload — or the wizard will render an
  editable rate field that 423s on save.
- **The revert path must respect it.** `revert()` writes old values back without
  going through the update route, so a revert on a *non-closed* batch could
  restore a group field that is frozen because a *different* batch closed. The
  check belongs in `revert` as well as in update, and that is the kind of second
  call site that gets found in production rather than in review.

### 3.10 Submission rules removed, and closing decoupled from submitting

**Decided.** `submission_errors()` goes. `POST /{id}/submit` always succeeds
(subject to the lock). Data quality moves to the input layer: dropdowns,
masters, required-at-entry.

This is the single largest simplification in the change — it deletes a function,
a 422 path, three frontend mirrors and a whole class of drift. It also has one
consequence you did not list, which is the reason this section is long.

#### Closing is decoupled from submitting

**Decided.** `is_closed()` becomes a **one-part** test:

```python
def is_closed(consignment):
    return consignment.current_status == Status.ARRIVED_AT_WORKS.value
```

And submit goes back to meaning only *"I am finished editing this"* — it sets
`record_state` and does nothing else.

**This is the right place for the meaning to live.** "Arrived at Works" is a
statement about the world: the goods are at the factory. Completion follows from
that fact rather than from a user asserting it. Under the two-part test a
consignment whose goods had demonstrably arrived stayed editable until somebody
remembered to press a button, which made the lock depend on an administrative
gesture rather than on the event it was supposed to represent.

It also removes the trap revision 4 identified. With the rule set gone, the
two-part test would have made submit a one-click, admin-only-to-undo lock on any
consignment already at Arrived at Works. Decoupling dissolves that rather than
mitigating it: submit no longer locks anything, so there is nothing to warn
about at submit time.

#### The correction: locking does not move, it has to be written

> *"Locking then fires on the status change rather than on submit … Remove the
> locking side effect from `submit_consignment.py:75-76`."*

**`submit_consignment.py:77` is the only place `is_locked` is ever set to `True`
in imports** (§1.2). The update route reads it at `:197` and never writes it.
CLAUDE.md says otherwise and CLAUDE.md is wrong.

So this is not a move. **Delete the write from submit and nothing locks at all** —
`is_locked` stays `false` for ever on every record the app creates, and the
closed lock silently ceases to exist. The locking has to be **added** to
`update_consignment.py`, on the transition into `Arrived at Works`:

```python
# in the update route, after the status has been applied
if is_closed(consignment):
    consignment.is_locked = True
```

**Two consequences of that placement**, both of which need handling in the same
change:

- **It must fire on the transition, in the same request that sets the status.**
  The route currently rejects any write to a locked record (`:197`), so the lock
  has to be applied *after* that check and after the status is set — otherwise
  the request that closes the consignment rejects itself.
- **`helpers.py:168–173` must follow.** The list's `include_closed` filter tests
  `status == CLOSED_STATUS_VALUE AND is_locked == True` — the two-part test
  again, spelled out in SQL rather than through `is_closed()`. Left alone with
  the lock write deleted, that condition never matches and `include_closed=False`
  (the default) stops hiding closed consignments from the list. It should become
  the status test alone, matching the new `is_closed()`.

The second is the one that would ship unnoticed: it is not a crash, it is
"closed consignments started appearing in the default list" a week later.

#### The confirmation dialog moves to the status change

Not on submit — submit is no longer irreversible. **On the status change to
"Arrived at Works"**, which is where the irreversible act now lives:

> *"This marks the consignment complete and locks it. An admin must reopen it to
> edit."*

**Recorded as a consequence of the decision, not argued against it: the dialog
can warn about the lock but cannot say what is missing.** `missing_fields` is
gone with the rest of the rule set, so there is no list of gaps to show and no
way to say *"you are about to close this with no supplier and no exchange rate"*.
The warning is about permanence only. That is the trade the decision makes —
data quality moves to the input layer, so by the time a consignment reaches
Arrived at Works it is expected to be complete, and nothing checks that
expectation at the boundary.

#### `missing_only` — your premise is wrong, and it survives untouched

> *"The `missing_only` query parameter … is driven by the same source. It stops
> meaning anything."*

It is not, and it does not. `app/imports/helpers.py:217–218`:

```python
# "Missing information only" — the server-side notion of an incomplete
# record is a draft (a submitted one has passed the full rule set).
if missing_only:
    conditions.append(Consignment.record_state == "draft")
```

It filters on `record_state`, never on `submission_errors()`. CLAUDE.md
documents it the same way — *"`missing_only` (= draft)"*. So the parameter keeps
working exactly as it does now, on both `get_consignments_list.py:28` and
`export_consignments.py:85`.

**What breaks is its name and its comment, not its behaviour.** Today "draft"
implies "incomplete", because a record could only leave draft by passing the rule
set. Afterwards `record_state` says nothing about completeness, so a filter
called "Missing information only" returns records that may be entirely complete.

**Recommendation: rename, do not remove.** `missing_only` → `drafts_only`, and
delete the comment's second clause. The filter is genuinely useful — "show me
what nobody has marked finished" is a real question — it is just no longer a
question about missing fields. Removing it would take a working filter away
because its label went stale.

#### What `record_state` means afterwards

Today it means *"this record has passed the full rule set"*. Afterwards it means:

> **A user has marked this record finished. Nothing verifies that claim.**

That is weaker than before, and **weaker still than revision 4 assumed**: with
`is_closed()` now testing status alone, `record_state` no longer forms half of
the close condition either. It drives exactly one thing — the `drafts_only`
filter above — and is otherwise an informational flag on the record and a column
in the export.

**That is a fair description of what it should be.** A user saying "I am
finished editing this" is useful information and a reasonable thing to filter on.
It was never a good basis for a lock, which is what the two-part test made it.

Three things follow that should be written down rather than discovered:

- **The loaders are unaffected.** `load_05_consignments.py:117`'s
  `terminal_flags(status)` derives `record_state` and `is_locked` from the
  status, not from any rule set, so loaded rows keep arriving correctly stamped.
- **`export_consignments.py:51` exports `record_state` as a column.** Its
  meaning in that sheet changes with everything else; the column header should
  say "Marked finished" rather than anything implying validation.
- **§1.3's latent bug disappears.** The `works` requirement that made all 179
  loaded consignments un-resubmittable goes with the rest of the rule set. That
  problem is solved by deletion rather than by the backfill §7 item 8 proposed —
  the backfill is still worth doing for data quality, but it is no longer
  load-bearing.

#### What replaces `missing_fields`

`serializers.py:135` publishes it on every read; `serializers.py:69–74` computes
it. Both go. It has **eight consumers in imports alone**, and they are not all
the same thing:

| Consumer | What it does | Replacement |
|---|---|---|
| `ImportsStatusList.tsx:303–306` | "N fields missing" warning tag | **Nothing.** |
| `ImportsStatusList.tsx:688` | `flagged={(r) => r.missing.length > 0}` — row highlight | **Nothing.** |
| `ImportsStatusDetail.tsx:99`, `:190` | Disabled Submit + "Missing: …" tooltip | **Nothing** — submit is never blocked now. |
| `ImportsStatusDetail.tsx:234` | KeyFigure *"Information: N pending / Complete"* | **Nothing.** |
| `ImportsStatusDetail.tsx:237–239` | "Pending information: …" banner | **Nothing.** |
| The wizard's requirements banner (`SubmitRequirements.tsx`) | Lists outstanding requirements per step | **Nothing, in imports.** |

**The honest answer is that nothing replaces them.** That is the decision, not an
oversight: if data quality is enforced at entry then a record cannot be
incomplete in the ways these surfaces reported, and a tag that can never fire is
worse than no tag. But it should be stated plainly rather than discovered as an
absence, because **the blue "pending allocation" highlight from the requirements
(§3.7) now becomes the only row-level warning on the imports list.** That is a
narrower signal than the one it replaces, and it is the only one left.

**One cross-module consequence to handle deliberately.**
`components/SubmitRequirements.tsx` and `lib/submitRequirements.ts` are
**shared** — `logisticsStatus/schema.ts`, `truckingStatus/schema.ts` and both of
their wizards use them, and `app/logistics/helpers.py:646` and
`app/trucking/helpers.py:603` still have their own `submission_errors()`.

**So this decision applies to imports only, and it makes imports diverge from
the other two modules.** After it, logistics and trucking still block submit and
still show requirement banners; imports does not. That is a real inconsistency
for a user who works across all three, and it is a cost of the decision rather
than a reason against it — but it should be a choice. If the intent is for all
three to lose their rule sets, say so and it is nearly the same amount of work.
If not, `SubmitRequirements.tsx` stays for the other two and imports simply
stops importing it.

#### B4 is dissolved, not answered

Revision 2 answered B4 — how `schema.ts` and `submission_errors()` are kept in
agreement — with a fixture-based test and a review rule. **That answer is now
moot.** With neither side blocking anything, there is nothing to keep in
agreement: no 422 to predict, no disabled button to justify, no divergence that
can reach a user.

Recorded as **closed by this decision rather than solved by that one**. The
distinction matters, because the underlying problem — two encodings of one rule
in two languages — is not fixed and would come straight back the moment any
validation is reintroduced anywhere in this module.

`tests/test_submission_rules.py` goes with the function it tests. That is one of
the four suites CLAUDE.md describes as chosen "for consequence rather than
coverage percentage", so its removal should be noted in the same commit rather
than left to look like an accidental deletion.

---

## 4. The migration

**Two Alembic revisions, expand then contract** — answer 7, and it is the right
call. Revision 2 of this document proposed one revision that both created the new
structure and dropped twenty-six columns, which is what forced §4.6's admission
that the downgrade was hand-written and effectively untested. Splitting it
removes that problem rather than mitigating it.

| | What it does | Reversibility |
|---|---|---|
| **Revision A — expand** | Creates `consignment_batch_groups`, `consignment_order_items`, `payment_addenda`; adds the FK columns; **copies** the shared and per-order values onto the new rows. Original columns stay in place, populated, and unread by the new code. | **Purely additive. `downgrade()` drops what it added and nothing else.** Trivially and genuinely reversible. |
| **Revision B — contract** | Drops the twelve orphaned columns from `consignments`, thirteen from `consignment_items`, and `payments.consignment_id`. A release later, once batching has run in production. | Reversible only in the sense revision 2 described. But by then nothing reads them, so rolling back the *code* no longer needs the columns. |

The gap between them is the point: the risky deploy is Revision A, and Revision A
is the one that can be undone with a single `alembic downgrade`.

**The cost of the gap is duplicated state**, and §4.7 is about what stops that
duplication becoming divergence. You asked for that named rather than assumed,
and it turned out to be worth asking.

### 4.1 Schema — groups and the shared fields

```
create table consignment_batch_groups (
    id                  serial primary key,

    -- identity. The displayed number IS the founding batch's id (§0.4), so
    -- there is no number column to keep in step and none that can drift.
    founding_consignment_id integer not null references consignments(id),
    batches_ever            integer not null server_default '1',  -- §3.5

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

-- REVISION B ONLY, a release later (§4, §4.7). Twelve columns: the eleven
-- shared values plus branch_id, which works_branch_id now succeeds (§3.3).
-- alter table consignments
--     drop column supplier_id, origin, currency, consignment_type, incoterm,
--                 payment_instrument, instrument_number,
--                 exchange_rate, rate_booked_on, rate_source, works, branch_id

-- ONE index, not two. A unique index on (batch_group_id, batch_sequence) leads
-- with batch_group_id, so it already serves every lookup by group and the
-- foreign key check. Revision 5 listed a second, single-column index as well;
-- it cost a write on every consignment save and answered nothing the first
-- cannot.
create unique index uq_consignments_group_sequence
    on consignments (batch_group_id, batch_sequence)
```

#### The two link constraints are DEFERRABLE — and without that, §4.1 could not run

**Corrected in revision 6, after building it.** `founding_consignment_id` and
`batch_group_id` are both NOT NULL and each points at the table the other lives
in. With foreign keys checked per statement, **there is no order in which a new
order and its first batch can be inserted.** All three orderings were tried
against the real schema:

| Insert order | Result |
|---|---|
| group first | `fk_batch_groups_founding_consignment` — the consignment is not present |
| consignment first | `fk_consignments_batch_group` — the group is not present |
| both inside one transaction | same failure; the check does not wait for COMMIT |

So the migration's own back-fill is the *only* thing that could ever have
worked, because it writes the link column onto rows that already exist. Every
create after it — through the app or through the loader — would have been a
500.

Both constraints are therefore **`DEFERRABLE INITIALLY DEFERRED`**:

```
alter table consignments
    add constraint fk_consignments_batch_group
    foreign key (batch_group_id) references consignment_batch_groups(id)
    deferrable initially deferred
```

**This does not weaken either constraint**, and that was checked rather than
assumed: a transaction that inserts one half and commits still fails, naming the
missing row. Deferring moves the check to COMMIT; it does not remove it. What it
buys is the one sequence that works — take the group's id from its sequence,
insert the consignment carrying it, then insert the group referencing the
consignment, then commit.

The model mirrors this, and `founding_consignment_id` additionally carries
`use_alter=True` so `create_all` can still build a brand-new database: without it
SQLAlchemy cannot sort two mutually dependent tables and warns that it is
ignoring the cycle.

**RESTRICT is not deferrable, in Postgres, ever.** Both `ondelete` clauses stay
`RESTRICT`, which means a group and its founding consignment can never be HARD
deleted — as a pair or singly. Nothing in this system hard-deletes, so this costs
nothing operationally; it is recorded because it is surprising when first met.

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

    price_basis         varchar not null server_default 'quantity',   -- §6 Q1
    unit_price          numeric(18,4),   -- per unit_of_measurement
    weight_unit_price   numeric(18,4),   -- per kilogram; weight basis only
    unit_weight         numeric(14,3),   -- kg PER UNIT, not the line total

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

-- REVISION B ONLY (§4, §4.7).
-- alter table consignment_items
--     drop column item_id, item_code, item_name, placeholder_name, specification,
--                 hs_code, unit_price, unit_of_measurement,
--                 requisition_type, reference_number, job_number, mo_number,
--                 description

create index ix_consignment_order_items_group on consignment_order_items (batch_group_id)
create index ix_consignment_items_order_item on consignment_items (order_item_id)
```

The **drops** in §4.1 and §4.2 are the part to review hardest. They are what
makes this migration destructive rather than additive, and they are why §4.6
says what it says about reversibility.

### 4.3 Data migration

For each of the **183** consignment rows — all 179 live *and* all 4 soft-deleted;
excluding the deleted would break undo-delete:

1. Insert one `consignment_batch_groups` row, **copying** the twelve shared
   columns off the consignment — `branch_id` into `works_branch_id` (§3.3), the
   other eleven by name. Copying, not moving: the originals stay until
   Revision B.
2. Set `batch_group_id`, `batch_sequence = 1`, `batches_ever = 1`, and
   `founding_consignment_id` to the consignment's own id (§0.4) — which is what
   makes every existing displayed number stay exactly as it is.
3. For each of that consignment's item lines — **455 across the table** — insert
   one `consignment_order_items` row, copying the per-order columns off the
   line, with `ordered_quantity = quantity` and `allocated_quantity = quantity`:
   the whole order is allocated to the single batch, which is exactly what those
   rows mean today.

   **`COALESCE(quantity, 0)`, not `quantity` — added in revision 6.**
   `ordered_quantity` is NOT NULL and **two lines carry no quantity at all**:
   ids **451** and **460**, on soft-deleted consignments **179** and **182**,
   which are blank in every column — no item code, no name, no quantity. As
   written this step aborted the whole migration on those two rows. A blank line
   orders nothing, so it back-fills as 0. **This is the only place the migration
   writes a value the source did not hold**, and it is confined to two rows that
   hold nothing.

   **Where the demand fields come from — under-specified in revision 5.**
   `branch_id`, `requisition_date` and `required_date` are on the order item per
   §3.3, but they are **header** columns today and the line has no copy of them.
   The back-fill therefore reads them off the CONSIGNMENT: while a consignment
   has exactly one branch and one pair of dates, the header value is the true
   one for every line under it. Leaving them NULL would empty every per-item
   date the moment the code starts reading the new column.
4. Point the line's `order_item_id` at it.
5. ~~Then, and only then, drop the columns.~~ **Nothing is dropped in Revision A.**
   The originals stay populated and unread until Revision B (§4, §4.7).

Every group has one member, so by the §3.4 rule **every existing consignment
displays with no suffix**, and by §0.4 with exactly the number it shows today.
No back-fill of numbers, and nothing an operator would notice.

`batch_group_id` and `order_item_id` get `NOT NULL` in Revision A, after the
back-fill, so no window exists in which a consignment has no group or a line has
no order item.

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
    alter column batch_group_id set not null

-- REVISION B ONLY
-- alter table payments drop column consignment_id
```

**Today this moves exactly one row: there is a single payment record in the
entire database.** Revision 2 of this document used that to argue the migration
was cheap. **That framing was wrong and I am correcting it** — per answer 8 the
single row is because staff have not started using the screen, not because the
screen is dead. The migration is cheap *today*; it is not a reason to treat
payments as a minor part of the change, and the insurance and addenda work in
this section is built as specified regardless.

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

**And per §3.6 there is no later conversion either** — no report, no conversion
path, no eventual drop of `batch_no`. Revision 2 proposed a report so operators
could split those fifteen by hand; that is withdrawn. Reasons 1 and 3 above
apply just as much to a deliberate on-screen conversion as to a migration: the
consignments are closed, their goods have arrived, and their figures have been
reported. The historical marker stays readable and nothing rewrites those rows.

### 4.6 Down-revision, and whether it is honestly reversible

`down_revision` is the current head; the real hash goes into the revision when
it is written.

**Splitting the migration in two (answer 7) fixes the problem revision 2 could
only admit to.** Revision 2 dropped twenty-six columns in one revision, so its
`downgrade()` had to recreate them and copy data back — hand-written code the
normal path would never exercise, which I flagged as the least-tested code in
the change. That is gone.

- **Revision A is purely additive**, so its `downgrade()` drops what it added
  and nothing else. There is no data-copying downgrade to write, no untested
  path, and the round trip is exact. **This is the revision that ships with the
  risky deploy, and it is cleanly reversible at any point** — before or after
  real batches exist. Rolling it back loses the batches, which is the correct
  behaviour for rolling back the feature that created them.

- **Revision B is the one-way door**, and by the time it runs the feature has
  been live for a release, nothing reads the orphaned columns, and rolling back
  the *code* no longer needs them. It drops twenty-six columns and its
  `downgrade()` recreates them empty — which is honest, because the data has
  been living in the new tables for a release and copying it backwards would be
  reconstructing history rather than reversing a change.

#### TWO semantic views read these columns, and they are NOT this app's to change

**Found by trying the drop, then by asking the database properly.** Against a
scratch clone:

```
ALTER TABLE consignments DROP COLUMN supplier_id;
-- ERROR: cannot drop column supplier_id of table consignments
--        because other objects depend on it
-- DETAIL: view v_import_shafts depends on column supplier_id of table consignments
```

That found one. The `pg_depend` query below found the second, `v_item_demand_picture`,
which the failing drop never mentioned because it does not touch `supplier_id`:

```sql
SELECT DISTINCT dependent.relname
  FROM pg_depend d
  JOIN pg_rewrite r        ON r.oid = d.objid
  JOIN pg_class dependent  ON dependent.oid = r.ev_class
  JOIN pg_class source     ON source.oid = d.refobjid
 WHERE source.relname IN ('consignments', 'consignment_items');
```

Between them they read seven moved columns: `c.supplier_id`, `c.origin`,
`ci.item_code`, `ci.item_name`, `ci.specification`, `ci.unit_price`,
`ci.unit_of_measurement`.

**Neither view is in `Base.metadata`.** `create_all` does not know them,
autogenerate proposes nothing about them, and `configure_mappers()` is perfectly
happy. They are invisible to every check this project has, and they surface
exactly once — when the `DROP COLUMN` runs.

**Both are defined in `chatbot_backend/database/semantic_views.sql`**, which is
a different service with its own code and its own `.env`, and is the same reason
its tables are excluded from Alembic (CLAUDE.md, "Database migrations"). So
Revision B cannot be written by this project alone.

##### This is not only a Revision B problem — it is live NOW

The views read the ORPHANED copies. After step 6 every edit writes the group and
the order line, and the consignment's own `supplier_id` and `origin` are never
written again. Measured on a scratch database immediately after step 6's own
route sweep:

| consignment | `consignments.origin` (what the views read) | `consignment_batch_groups.origin` (the truth) |
|---|---|---|
| 178 | `China` | `SyncProbe` |
| 21 | `China` | `batch2-wrote-over-China` |
| 179 | `China` | `batch2-wrote-over-China` |

Three edits, three views now answering with the creation-day value. Nothing
errored, and nothing will. **§7 item 3 predicted "chatbot answers go wrong with
nothing to notice"; this is the mechanism, and it starts the day step 6
deploys** — not the day Revision B runs.

##### Verified against his branch — the views are repointed, with one defect

`origin/chatbot-and-loaders` repoints both views, and it covers **all seven**
moved columns: `c.supplier_id`→`g.supplier_id`, `c.origin`→`g.origin`, and
`ci.{item_code, item_name, specification, unit_price, unit_of_measurement}`→`oi.*`
— including the `item_name` regexes in `v_import_shafts`'s `CASE` and `WHERE`,
which are easy to miss because they are predicates rather than output columns.
Applied to a scratch database the views hold **zero** dependencies on the
orphaned columns, and `v_import_shafts` agrees with the app exactly: 22
consignments over 100 lines, the same as `/dashboard/imports?shafts_only=true`.

**But the script cannot be applied to a database that already has the views.**
`CREATE OR REPLACE VIEW` cannot change a column's type, and this change does:

```
ERROR: cannot change data type of view column "unit_price"
       from numeric(14,4) to numeric(18,4)
```

`consignment_items.unit_price` is `Numeric(14,4)`; `consignment_order_items.unit_price`
is `Numeric(18,4)`. On a fresh database the script is fine. On the dev or
production database it fails **on that one statement and psql carries on**, so
the run looks successful, `v_import_shafts` silently stays on the orphaned
columns, and Revision B then fails on it exactly as before. The file needs a
`DROP VIEW IF EXISTS v_import_shafts;` ahead of the create, or the deploy needs
`psql -v ON_ERROR_STOP=1` so the failure is loud. **That file is not this
project's to change** — reported, not fixed.

##### The loaders write BOTH copies, and that is correct until Revision B

`load_05_consignments.CONSIGNMENT_COLUMNS` still lists the nine orphaned header
columns alongside `BATCH_GROUP_COLUMNS`, which is precisely what §4.7's rule
requires during the gap. **It also means Revision B has a fourth part**: those
nine names, and the thirteen item ones, must come out of the loader's column
lists in the same release as the drop, or the next `load_all` fails on a column
that no longer exists.

##### What Revision B therefore is

1. `DROP VIEW v_import_shafts`, `DROP VIEW v_item_demand_picture`;
2. the column drops;
3. recreate both, reading `consignment_batch_groups` and
   `consignment_order_items` — **already written**, on
   `origin/chatbot-and-loaders`, subject to the `CREATE OR REPLACE` defect above;
4. take the nine orphaned header columns and the thirteen item ones out of the
   loaders' column lists, in the same release.

The `downgrade()` must recreate the ORIGINAL definitions, not the new ones, or a
rollback leaves views over columns that no longer exist. And step 3 is a change
to another team's file, so **Revision B needs that team in the loop before it is
written, not after it fails.** Re-run the `pg_depend` query at the time — one
drop found one view and the query found two; there is no reason to assume two is
the final number.

**Still take a backup before Revision B**, and say so in the deploy note. Not
before Revision A — that one can simply be downgraded.

**What the split does not fix:** the feature flag is still worth having, because
Revision A's reversibility is about the *schema*, not about a half-migrated
operational state. If batches have been created and reverting means telling
users their second shipments no longer exist, "the migration is reversible" is a
statement about the database and not about the business. The flag keeps that
window closed until you are confident.

### 4.7 What stops anything writing to the orphaned columns during the gap

You asked for this named rather than assumed, and it was worth asking: the
answer is stronger than I expected in one respect and **it exposes a silent
failure in a different feature**, which I would not have found without the
question.

#### The control that actually works: remove the attributes from the model

**In the same release as Revision A, delete the eleven mapped attributes from
`Consignment` and the thirteen from `ConsignmentItem`, while leaving the columns
in the database.** SQLAlchemy cannot write a column it does not know about, so
this is not a convention — it is a structural impossibility for every ORM path.

> **Revision 6: the same RELEASE, but NOT the same PR — and it did not ship with
> Phase 1.** Three of those attributes are join columns for relationships in
> another module: `Consignment.supplier_id` and `branch_id` carry
> `Supplier.consignments` and `Branch.consignments`, and
> `ConsignmentItem.item_id` carries `Item.consignment_items`
> (`app/masters/models.py`). Delete the attributes and those relationships have
> no foreign key to join on, so **mapper configuration fails and every query in
> the app 500s** — measured, with two of the eleven removed. Around 116 call
> sites across `app/` read them besides.
>
> Repointing those consumers **is** §9 step 6, so steps 5 and 6 cannot be
> separated without a broken tree between them. The attribute removal therefore
> travels with step 6. Nothing else in §4.7 moved: the loaders are updated and
> the `post_load` checks are in, because those are safe on their own.
>
> This is also what exposed the verification command as worthless for exactly
> this class of change — see "Verifying this work" at the top.

> **Revision 7 — CORRECTION: "around 116 call sites" is an undercount of
> roughly half. It is 219 references across 19 files.** Counted, not estimated.
>
> | Cluster | Refs |
> |---|---|
> | `imports/helpers.py` | 44 |
> | `dashboard/imports/helpers.py` | 38 |
> | `dashboard/imports/calculations.py` | 23 |
> | `dashboard/whole/references.py` | 22 |
> | `imports/serializers.py` | 15 |
> | `cross_module.py` | 14 |
> | `reports/helpers.py` | 13 |
> | the other 12 files | 50 |
>
> **And 219 is not 24.** The 24 in §3.3 are the sites whose *meaning* changes.
> The rest change *location*, and they exist because removing a mapped
> attribute removes the RELATIONSHIP built on it: `Consignment.branch_id` and
> `supplier_id` carry `Consignment.branch` / `.supplier`, and
> `ConsignmentItem.item_id` carries `ConsignmentItem.item`. So every
> `consignment.branch.name`, every `item.item.category` and every
> `joinedload(Consignment.supplier)` goes too — including
> `CONSIGNMENT_VALUE`'s `Consignment.exchange_rate`, `_LINE_VALUE`'s
> `ConsignmentItem.unit_price` and `shaft_consignment_ids()`'s
> `ConsignmentItem.item_name`, which between them underpin every money figure
> and the shafts filter on every screen.
>
> **It also INVERTS THE WRITE PATH, which this section never said.** Phase 1's
> `sync_order_item_from_line` (`imports/helpers.py`) reads `item.item_code`,
> `item.unit_price` and `consignment.branch_id` off the very attributes being
> removed, and `new_batch_group` reads `consignment.branch_id`. After the
> removal, create and update must write the group and the order item DIRECTLY
> rather than mirroring from columns that no longer exist — which pulls the
> Pydantic schemas in with them. **That, not the repointing, is what makes step
> 6 large.** It is not a rename.

Two things make that a complete control here rather than a partial one, and both
had to be checked rather than assumed:

- **Every dropped column is nullable, with no default.** I verified all
  twenty-five against `information_schema`. So an INSERT that omits them
  succeeds and leaves NULL. Had any been `NOT NULL`, removing the attribute
  would have broken every create immediately — a loud failure, but it would have
  forced a different plan.
- **The diff and revert machinery is driven by the MAPPER, not the table.**
  `updated_fields` (`helpers.py:376`) builds
  `{c.key for c in Consignment.__mapper__.column_attrs}` and skips any field not
  in it; `revert_local_fields` (`:681`) iterates
  `inspect(consignment).mapper.column_attrs`. Neither touches
  `__table__.columns`. So removing an attribute removes it from the change
  history and from revert as well as from create and update — no separate work.

#### The three paths that bypass that, ranked by how likely they are to happen

1. **The loaders — the real risk.** `load_all` and `reload_changed` write raw
   `psycopg2` INSERTs naming columns explicitly, so they are entirely outside
   the ORM and will keep populating the orphaned columns unless they are changed
   in the same release. They would not error; they would quietly write a second
   copy of the truth, which is precisely the divergence expand-and-contract
   exists to prevent. **This is the path most likely to be missed**, because
   CLAUDE.md's own history says so: the loaders are the code that forgot
   `bump_sequence`, forgot the renamed `PPC/Store` column, and forgot
   `record_state`'s server default. Mitigation: a `post_load.py` check asserting
   the orphaned columns are NULL on rows created after the migration — the same
   conditional-check pattern already used there.

2. **Alembic autogenerate.** With the attributes gone and the columns present,
   the *next* `--autogenerate` for any unrelated change will propose dropping
   them — folding Revision B into a revision nobody meant to be Revision B.
   Mitigation: say so in Revision A's docstring. CLAUDE.md already says
   autogenerate is a first draft and not a fact, so the review step exists; this
   just tells the reviewer what to expect.

3. **Raw SQL anywhere else.** There is none against these columns outside the
   loaders and the dashboards, and the dashboards only read. Named for
   completeness.

4. **AN ORDINARY ORM UPDATE OF THE COPY NOBODY READS — added in revision 7,
   after it actually happened.** This is the one that got through, and it is
   worth stating separately because the first three are all about writes that
   bypass the model, and this one does not bypass anything.

   *"SQLAlchemy cannot write a column it does not know about"* is true, and it
   was never the whole story. **The control is only as good as the moment the
   attributes come off** — and between the migration and that moment, both
   copies exist and both are perfectly writable. The failure needs no raw SQL
   and no loader: `new_batch_group` copied the shared values onto the group once
   at creation and nothing copied them again, so an ordinary `PUT` updated the
   consignment and left the group holding its creation-day value. No error, no
   raw INSERT, no bypass — just two copies and one writer.

   It was invisible because it is the *unread* copy that goes stale, and an
   unread copy diverging costs nothing until the day it is read. The change that
   moves the readers is therefore the change that detonates it, which is exactly
   the worst time to find out.

   **The general form, which is what to carry forward: during an
   expand-and-contract gap, EVERY write path has to maintain BOTH copies, not
   just the ones outside the ORM.** `helpers.sync_batch_group` is the fix and it
   is deliberately transitional — once the attributes are gone there is one copy
   again and nothing to mirror.

   **This is the third time this document named a risk and got the mechanism
   wrong.** The verification command was worthless for exactly the class of
   change it was meant to cover (revision 6); the circular foreign key could
   never have been inserted as specified (revision 6); and §4.7 guarded the
   three exotic write paths while the ordinary one diverged. The pattern is not
   that the risks were wrong — all three were real — but that the *mechanism*
   was reasoned about rather than exercised. Build it before believing it.

5. **A DATA MIGRATION — added after it happened too, which is what makes the
   rule general.** Alembic revision `d5e81b6a2c07` normalises the enum values
   the workbooks loaded. It updated `consignments.payment_instrument` and not
   `consignment_batch_groups.payment_instrument` — so it corrected the copy
   nothing reads, left the copy everything reads holding `Advance`, `FOC` and
   `Contract`, and a loaded consignment still rejected its own save **while
   every test in that revision passed.**

   **The rule, now stated once rather than re-learned per path:**

   > **During the gap between expand and contract a value exists TWICE, and
   > every write path has to maintain both copies — the ORM, the loaders, a
   > data migration, a repair script, anything. "SQLAlchemy cannot write a
   > column it does not know about" describes the contract side of the
   > migration, not the gap, and the gap is where all the work happens.**

   Paths 1–3 are writes that go *around* the model. Paths 4 and 5 do not go
   around anything — path 4 is an ordinary `PUT`, path 5 is an `UPDATE` in a
   migration — which is exactly why the control §4.7 was built around could not
   see either of them. **Two of the five bypass paths were found by running the
   code; neither was predicted.**

   The tell is the same both times and is worth recognising early: **it is the
   UNREAD copy that goes stale, so the cost is zero until the day something
   reads it.** Anything that writes one copy during the gap is suspect on sight,
   and "I checked the column and it was clean" means nothing unless the column
   checked is the one the code actually reads.

#### The failure this uncovered: revert across the migration boundary

`revert_local_fields` walks the mapper's attributes and applies any matching key
from the stored history JSON. **Every `ConsignmentChangeHistory` row written
before Revision A contains keys like `supplier_id` and `exchange_rate` under
`fields`.** After the attributes move to the group, those keys match nothing on
the consignment, and the loop skips them.

**The revert then reports success and silently does not restore them.** A user
undoing a pre-migration change gets the item and date fields back and none of
the shared ones, with no error and nothing on screen to say half the change was
not undone. In a feature whose entire purpose is undo, that is worse than a
failure.

This is not caused by the two-revision split — it would happen under the
single-revision plan too. The split just makes it visible, because the columns
still exist while the attributes do not.

**DECIDED — route to the group, do not raise.**

1. **Old shared-field keys are applied to the group.** In `revert`, a history key
   that is not a `Consignment` attribute but *is* a `ConsignmentBatchGroup`
   attribute is written to the group instead. **Undo keeps working on the oldest
   records, which are the ones most likely to be reverted.**

   **The ambiguity I was guarding against does not exist.** Every pre-migration
   consignment is a group of one (§4.3), so `supplier_id` in an old history row
   has exactly one destination and there is nothing to resolve. That holds
   permanently, not just at migration time: a history row predating the migration
   can only belong to a consignment that founded its own group, and later batches
   join groups rather than creating history that predates them.

   **Subject to the §3.9 freeze.** A revert touching a Tier 1 field on a frozen
   group must refuse — reverting is a write, and rule 4 does not care which route
   the write took. A Tier 2 field follows the same admin rule as any other edit.
   This is the second call site §3.9 names, and it is the one that gets missed.

   **If costing this turns up something that makes it materially harder than
   raising** — a case where the destination genuinely is ambiguous, or the freeze
   interaction needs a third behaviour — that comes back to you rather than being
   switched silently.

2. **Anything matching neither model still raises.** Routing handles the known
   move; a key belonging to no model at all is a real defect and should be loud.
   The current silent skip is what made this class of bug invisible, and removing
   it is a two-line change worth making **before** the migration (build order
   step 3) so the boundary behaviour is observable rather than assumed.

**Revision 7 — this is TWO paths, not one, and the second one is worse.**

Everything above describes `revert_local_fields`, which walks
`Consignment.__mapper__.column_attrs` and which Phase 1 made raise. **The
CHILD-row equivalent, `revert_old_values` (`imports/helpers.py`), has the
identical mapper-driven bug and no loud failure at all** — Phase 1 hardened only
the header half.

It walks `inspect(consignment_data).mapper.column_attrs` for each
`ConsignmentItem` and applies whichever history keys match. **Every
`ConsignmentChangeHistory` row ever written carries `item_code`, `item_name`,
`unit_price`, `specification`, `requisition_type` and the rest under its item
diffs** — thirteen keys that stop matching `ConsignmentItem` the moment those
attributes move to `ConsignmentOrderItem`. Today they would all be skipped in
silence, and an item revert would report success having restored the line's
quantity and landed cost and nothing else.

So step 6 does both halves, symmetrically:

- **Header keys** that are not `Consignment` attributes but ARE
  `ConsignmentBatchGroup` attributes → written to the group.
- **Item keys** that are not `ConsignmentItem` attributes but ARE
  `ConsignmentOrderItem` attributes → written to the line's order item.
- **Anything matching neither, on either path, raises**, naming the keys.

The destination is unambiguous on both, and for the same reason: every
pre-migration consignment is a group of one, and every pre-migration line
back-filled exactly one order item (§4.3).

3. **The stored history JSON is not rewritten.** It is tempting to translate old
   rows in the migration so the keys nest under the group. Against: the history
   is an audit record of what was changed and by whom, and rewriting it to match
   a new schema makes the audit trail a derived artefact of the current model
   rather than a record of what happened. Routing at read time achieves the same
   result without touching the record.

### 4.8 Removing `po_date`

**Decided: removed.** It joins the Revision B drop list, making it a thirteenth
column off `consignments`.

**First, the thing you expected to lose is already gone.**

> *"schema.ts's `procurementLeadDays()` computes requisition-to-PO lead time and
> dies with the column."*

`procurementLeadDays` is defined at `schema.ts:541–542` and **called from
nowhere**. A repository-wide search returns exactly one hit: its own definition.
It is already dead code, and has been. It does not die with the column — it died
before it, and nothing on any screen has been showing procurement lead time.

That matters for your question of whether anything is worth keeping by another
route: **the feature you were about to preserve was never running.** If
requisition-to-PO lead time is wanted, it is a new feature to specify, not an
existing one to rescue — and it cannot be built from imports at all once
`po_date` is gone.

**Second — and this is the one worth pausing on — the metric survives elsewhere,
on better data.** `app/dashboard/whole/helpers.py:477–482` computes
`avg(PurchasesData.purchase - PurchasesData.po_date)` over the purchases table,
which has **78,931 rows** against imports' 179 and is the system's actual record
of procurement. Imports' `po_date` was never the source of a procurement-lead-time
figure anyone reads. Nothing needs replacing.

**The consumer list.** Note that most repository hits for `po_date` are
`PurchasesData.po_date`, a different table on a different module, and are
**untouched**. Only these are `Consignment.po_date`:

| Where | What | Action |
|---|---|---|
| `app/imports/models.py:104` | the column | Drop in Revision B |
| `app/imports/models.py:110` | comment on `requisition_date` — *"The gap to po_date is procurement lead time"* | Reword; the gap no longer exists |
| `app/imports/schemas.py:72` | Pydantic input field | Remove |
| `app/imports/serializers.py:99` | response field | Remove |
| `app/reports/serializers.py:156` | `"po_date": c.po_date` on the imports **line** serializer | Remove — and note `:158` `"works": c.works` in the same block needs the §3.3 move |
| `app/reports/routes/report_export.py:34` | the `"PO Date"` column label | **Keep** — shared with purchases |
| `schema.ts:181`, `:464`, `:503` | zod field, default, Step 1 field list | Remove |
| `schema.ts:183` | comment distinguishing it from `requisitionDate` | Remove |
| `schema.ts:541–542` | `procurementLeadDays` — **already dead** | Delete |
| `Step1Consignment.tsx:296–297` | the date input | Remove |
| `lib/api/imports.ts:83`, `:321` | API types | Remove |
| `lib/api/importsMap.ts:453`, `:548` | payload and draft mapping | Remove |
| `lib/api/importsChangeHistoryMap.ts:62` | `{ label: 'PO date', kind: 'date' }` | **Keep** — see below |
| `lib/reportBuilder.tsx:91`, `:148` | two report column lists | Remove from the imports list (`:148`); `:91` is purchases |

**`importsChangeHistoryMap.ts:62` must stay**, and it is the easiest one to
delete by mistake. It is the display label for `po_date` in the **change
history**, and every history row written before this change still contains
`po_date` entries. Removing the label leaves those rows rendering a raw column
name or nothing at all. This is the same class of problem as §4.7's revert gap —
history outlives the schema — and the fix here is trivial: leave the label in
place. It costs one line and it keeps the audit trail readable.

### 4.9 Locking the drafts already at Arrived at Works — the count is ZERO

You asked for the number before the revision is written. **It is zero, and it is
zero across all 183 rows, not just the live ones.**

**Live consignments at "Arrived at Works" — all 142 of them:**

| `record_state` | `is_locked` | Count |
|---|---|---|
| `submitted` | `true` | **142** |

There is no other row. And in the other direction:

| Check | Count |
|---|---|
| Drafts at Arrived at Works, not yet locked — **the ones that would newly lock** | **0** |
| Locked but *not* at Arrived at Works (the new rule would call these open) | **0** |
| At Arrived at Works, submitted, but not locked | **0** |
| Soft-deleted rows at Arrived at Works and not locked | **0** |

**The 31 drafts are all still in flight**, spread across the six pre-arrival
statuses:

| Status | Drafts |
|---|---|
| In Transit | 13 |
| Ready Awaiting Sailing | 6 |
| On Road | 5 |
| Under Production | 5 |
| TT/LC in Process | 1 |
| Under Examination | 1 |

**So the one-part and two-part tests agree on every row in the database today.**
`is_locked` and `is_closed()` are already perfectly aligned — 142 locked, 142 at
Arrived at Works, 142 submitted, with no drift in either direction. Nothing
changes state when the rule changes, and nothing is in the state the new rule
says cannot exist.

**Write the lock statement into the revision anyway.**

```sql
update consignments
   set is_locked = true
 where current_status = 'Arrived at Works'
   and not is_locked
```

It affects zero rows as of this count, and that is exactly why it costs nothing
to include. **The count is a snapshot, not a guarantee**: between now and the
deploy an operator can move a draft to Arrived at Works, and the four soft-deleted
rows can be restored by undo-delete at any time. A statement that no-ops today
and catches a row that appeared last Tuesday is the cheap side of that bet.

It also documents the invariant. Anyone reading the revision later sees the rule
asserted in SQL — *at Arrived at Works implies locked* — rather than having to
trust that it happened to hold.

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
| **Rule 8 is factually wrong about `is_locked`** | It says the flag is "set on that update" when status reaches Arrived at Works. No update route in any module sets it; submit is the only site (§1.2). Correct the wording, not just the rule. |
| **The three modules now disagree** | See below. This is the largest documentation debt the change creates. |

### 5.1a The three-module divergence — imports only

This change applies to **imports alone**. Logistics and trucking keep the
two-part `is_closed()` and keep their submission rule sets; they will be brought
into line later. **Recording it here and in CLAUDE.md is not optional** — three
modules that look identical and behave differently is precisely the kind of thing
that gets discovered by a developer assuming the pattern holds.

| | Imports (after) | Logistics | Trucking |
|---|---|---|---|
| **`is_closed()`** | status alone | status **and** submitted | all vehicles delivered **and** submitted |
| **What submit does** | sets `record_state`, nothing else | validates, sets `record_state`, **locks** | validates, sets `record_state`, **locks** |
| **What locks** | the status change, in the update route | `POST /{id}/submit` | `POST /{id}/submit` |
| **Submission rules** | none — always succeeds | `helpers.py:646` | `helpers.py:603` |
| **`missing_fields` on read** | gone | `serializers.py:113` | `serializers.py:109` |
| **Requirements banner** | gone | `SubmitRequirements.tsx` | `SubmitRequirements.tsx` |

**CLAUDE.md needs this as a table, in the same PR**, in the cross-cutting
patterns section where "Draft vs submitted and the closed lock — present in all
three modules" currently claims uniformity that will no longer hold.

**`components/SubmitRequirements.tsx` and `lib/submitRequirements.ts` STAY.**
They are shared with `logisticsStatus/schema.ts`, `truckingStatus/schema.ts` and
both of those wizards. Imports stops importing them; nothing is deleted from the
component itself. Deleting a shared component because one of its three consumers
went away is the obvious mistake here, and it would break two working modules.

The same applies to the backend: `app/logistics/helpers.py:646` and
`app/trucking/helpers.py:603` keep their own `submission_errors()`. Only imports'
is removed, and `tests/test_submission_rules.py` covers imports' — check before
deleting whether it exercises the other two.
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

> **Revision 7 — this missed the SCANNER, which is the part that reads moving
> columns.** `app/notifications/scanner.py:629` selects
> `Consignment.instrument_number` and `Consignment.payment_instrument` for the
> payment-due notification; both move to the group. `:525`–`:526` and `:578`
> read `instrument_number` again for the clearance-aging and demurrage scans.
> These are live paths that run on a schedule with nobody watching, so a break
> here surfaces as notifications quietly not being sent. **In scope for step
> 6.**

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

**Masters.** `masters/helpers.py:164` and `:250` — the Branch "used" count.

> **Revision 7 — CORRECTION: NOT "through the order item".** §3.3 settled the
> branch on `group.works_branch_id`, and this line was never updated to match.
> The count reads the GROUP and counts groups (§3.2 #14). `masters/helpers.py`
> also carries two more callers of the same function that this entry never
> mentioned: **supplier** (`:161`, → groups) and **clearing agent** (`:190`, →
> rows, because that column stays per batch).

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

**RESOLVED — and the answer is better than what I proposed.** Revision 2
recommended one `unit_price` column carrying two meanings with a dynamic label.
Answer 2 gives weight-priced items **their own per-kilogram price column**
instead:

| Column | Meaning | Used when |
|---|---|---|
| `unit_price` | price per one `unit_of_measurement` | `price_basis = 'quantity'` |
| `weight_unit_price` | price **per kilogram** | `price_basis = 'weight'` |
| `unit_weight` | kilograms **per unit** | `price_basis = 'weight'` |

**Two things this fixes that the single-column version did not.**

The dynamic label problem disappears: `unit_price` stays *"Unit Price (per
{unit_of_measurement})"* and the new field is simply *"Price per kg"*. Neither
label has to be computed, and neither can be read as the other.

More importantly, **a column that means two different things depending on a flag
on the same row is a stored ambiguity, and this app has been bitten by that
shape before.** Anyone summing `unit_price` across items — a report, an export
column, a future dashboard — would be adding rupees-per-kilogram to
rupees-per-piece and getting a number with no meaning, with nothing in the data
to warn them. Two columns make that arithmetic impossible to write by accident.

`net_weight` is untouched and keeps its documented meaning — the line's total
for its whole quantity — even though it is empty and a redefinition would have
migrated nothing. That is the right call for the reason in the block quote
above: the sibling module uses the same name the same way, and a silent
redefinition is discovered by whoever next reads `LogisticsItem` and assumes
they match.

**A4 is closed by implication:** the weight unit is **kilograms**, because the
price is defined as per-kilogram. `unit_weight` is `Numeric(14,3)` in kg, the
same convention as `net_weight` and `LogisticsItem.gross_weight`. Worth a
comment on the column, since "weight" alone is exactly the kind of unqualified
unit that becomes a question later.

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

**RESOLVED, as recommended, with both caveats adopted.** The Step 1 display goes
(`Step1Consignment.tsx:212`, rendered 310–314). The list column stays, with two
changes:

- **It is defined as the EARLIEST required date across that batch's items.**
  `required_date` moves to the order item (§3.7), so a batch has no single one —
  `min(order_item.required_date)` over the batch's live lines, ignoring lines
  with none. Earliest rather than latest because the column exists to say
  *"something here is late"*, and the first date to pass is the first thing that
  is late.
- **It adopts `DELAY_GRACE_DAYS`**, so the column and the dashboard's Delayed
  tile stop contradicting each other about the same consignment.

`schema.ts:550` `requiredVsEtaDelay` is deleted and `importsMap.ts:317`
`requiredDelayDays` is kept, **which also resolves finding 4** — one
implementation, one consumer.

One consequence to carry into the build: `requiredDelayDays` currently takes a
list row with a single `requiredDate`. Under the earliest-across-items rule the
*server* must supply that minimum on the serialized row, because the list
payload does not carry the batch's item lines. That is a serializer change, not
a frontend one, and it is easy to overlook because the frontend function keeps
its signature.

The reasoning, kept because the two are easy to conflate:

- In the list, delay is *comparative*. It sorts (`ImportsStatusList.tsx:325`)
  and tells you which of forty consignments to look at first.
- In Step 1 it is a number beside two fields the user is mid-way through typing,
  changing as they type, that they cannot act on and cannot sort. Noise during
  data entry.

One fact to keep in view: `required_date` is populated on only **97 of 179**
consignments, so the column is blank on 46% of rows. That is a data gap, not a
bug, but it makes the column less useful than it looks and it will not improve
until the field is filled in during entry.

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
in the app. That needs your agreement before it ships. Both are now settled: §3.3 for branch and for requisition date.

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

### 5 — HIGH: revert silently half-succeeds across the migration boundary

**What.** §4.7. `revert_local_fields` (`helpers.py:681`) walks the mapper's
attributes and applies matching keys from the stored history JSON. Every
`ConsignmentChangeHistory` row written before the migration carries keys like
`supplier_id` and `exchange_rate`. Once those attributes move to the group, the
keys match nothing and **the loop skips them**.

**Why HIGH.** The revert reports success. A user undoing a pre-migration change
gets the per-batch fields back and none of the shared ones, with no error and
nothing on screen saying half the change was not undone. In a feature whose
entire purpose is undo, silent partial success is worse than failure — and the
records most likely to be reverted are the ones with the most history, which are
the oldest ones, which are exactly the ones whose history predates the
migration.

This is not caused by splitting the migration; the single-revision plan had it
too. It was found only because answer 7 asked what stops writes to the orphaned
columns.

**Mitigation.** §4.7: route unknown history keys to the group (subject to the
§3.9 freeze), and make a key matching neither model **raise rather than skip** —
the silent skip is what makes this class of bug invisible, and removing it is
worth doing on its own account. Do not rewrite the stored history JSON to match
the new schema; an audit record should say what happened, not what the current
model would prefer.

### 5b — MEDIUM: the migration gap duplicates the truth

**What.** §4, §4.7. Between Revision A and Revision B the shared values exist in
two places. The ORM cannot write the old copies once the attributes are removed,
but the **loaders bypass the ORM entirely** and will keep populating them.

**Why not higher.** It fails quietly rather than loudly, but it is bounded: the
new code never reads the orphaned columns, so a stale copy misleads a human
reading the database directly rather than corrupting a screen.

**Mitigation.** Update both loaders in the same release as Revision A; add a
`post_load.py` check asserting the orphaned columns are NULL on rows created
after the migration. Name Revision B in Revision A's docstring so the next
autogenerate does not fold the drop into an unrelated change.

### 6 — HIGH: the 142 locked consignments

**What.** 79% of live consignments are locked; update and submit return 423, and
only an admin reopens. Any operation writing to a sibling row hits that wall.

**Resolved, and it opened a second risk.** Adding a batch to a locked group is
allowed to any user, always, with no admin and no reopen. §3.5 (numbering writes
nothing) and §3.8 (shared fields stored once, so nothing propagates) mean the
lock is no longer in the way of anything.

**But the group itself is not lockable**, so an ordinary user could edit a
group-level exchange rate while a batch in that group is closed, putting the
stored `pkr_total` and the derivable one permanently at odds. **§3.9 is the rule
that closes it** — the group's valuation and commercial fields freeze the moment
the first batch closes, enforced in the update path *and* in `revert`, published
on the serialized payload so the wizard does not render an editable field that
423s.

### 6b — HIGH: the lock moves, and the only site that sets it is being deleted

**Resolved in principle, but the implementation is the risk.** Revision 4's
version of this entry — submit becoming a one-click lock — is **dissolved** by
decoupling closing from submitting (§3.10). Submit no longer locks anything.

**What replaces it is a sequencing risk.** `submit_consignment.py:77` is the
**only** place `is_locked` is ever set to `True` in imports (§1.2). The
instruction was to remove it; the locking does not move on its own. If the write
is deleted and not added to the update route in the same change:

- Nothing ever locks. `is_locked` stays `false` for ever on every record the app
  touches, and the closed lock silently ceases to exist.
- `helpers.py:173`'s `include_closed` filter — which tests
  `status == CLOSED_STATUS_VALUE AND is_locked == True` — never matches, so
  **closed consignments stop being hidden from the default list**. Not a crash;
  a behaviour change noticed a week later.

**Why HIGH despite being straightforward.** The app-side lock path has **never
fired on a real record** — all 142 locked rows came from the loader (§1.2) — so
there is no production evidence that it works, and a regression in it produces no
error. It cannot be verified by observing that nothing broke.

**Mitigation.** Delete and add in one change, never separately. Update
`helpers.py:168–173` to the one-part test alongside `is_closed()`. And test the
transition explicitly — set a draft to Arrived at Works, assert `is_locked`
became true and that the next update returns 423 — because nothing in the
existing data exercises this path.

### 6c — MEDIUM: the closing dialog cannot say what is missing

**What.** §3.10. The confirmation moves to the status change, where the
irreversible act now lives. But `missing_fields` is gone, so it can warn about
permanence and nothing else — it cannot say *"you are about to close this with
no supplier and no exchange rate"*.

**Why it matters.** Closing is the last moment anything could have caught an
incomplete record, and it is now the moment with the least information. A
consignment can be locked with empty required fields and no warning naming them.

**Mitigation — none proposed, and this is the trade the decision makes.** Data
quality moves to the input layer, so a consignment reaching Arrived at Works is
*expected* complete; nothing verifies that expectation at the boundary. Recorded
so it is a known consequence rather than a discovery. If it later proves painful,
the cheapest answer is a non-blocking count of empty required fields in the
dialog — which is `submission_errors()` returning for display only, and should be
recognised as that rather than reintroduced by accident.

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

### 9 — LOW: `batch_no` becomes a frozen legacy column

**What.** 59 lines carry a hand-typed batch marker on 15 consignments. Under
§3.6 those are **never converted**: the column stops being written, stays
readable, and is never dropped.

**Downgraded from MEDIUM.** Revision 2 ranked this as two competing sources of
truth. It is not, once conversion is off the table — the old marker describes 15
finished consignments and the new structure describes everything after, and the
two never apply to the same record. What remains is a documentation risk, not a
data one.

**Mitigation.** A comment on the model and a line in CLAUDE.md saying the column
is deliberately frozen. Without one, the next person tidying the schema will
find a column nothing writes and drop it.

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

## 8. Open questions

### Closed by your answers

| Revision 2 asked | Answer |
|---|---|
| **Q1** What is `177`? | The founding consignment's id. No back-fill. §0.4 |
| **Q2** What unit is `unit_weight`? | Kilograms — the weight price is defined per-kg. §6 Q1 |
| **Q3** What does a consignment show when its items disagree? | **Branch: closed** — `works_branch_id` at header level, items vary below (§3.3). **Required date: closed** — earliest across the batch's items (§6 Q2). **Requisition date: still open**, see 2 below. |
| **Q4** Batch into a locked group? | Always allowed, any user. §7 item 6, and it produced §3.9 |
| **Q5** Numbering permanence? | Accepted. Decisions table reversed. §3.5 |

### Also closed this round

| | Answer |
|---|---|
| Revert, pre-migration history | Route to the group, not raise. §4.7 |
| Freeze scope | Two tiers — hard (valuation) and admin-overridable (commercial). §3.9 |
| Payments in the freeze | Excluded, confirmed. §3.9 |
| Requisition date | Filters move onto the item's own column; no aggregate. §3.3 |
| `po_date` | Removed. §4.8 |
| Submission rules | Removed entirely. §3.10 |

### Closed in the final round

| | Answer |
|---|---|
| The four Step 3 fields | **All per batch.** `clearing_agent_id`, `mode_of_shipment`, `loading_port_id`, `delivery_port_id` stay on `consignments`. Each shipment can use a different agent, so `clearing_agent_id` does **not** join Tier 2 and is not subject to the §3.9 freeze. |
| Closing vs submitting | Decoupled. One-part `is_closed()`; submit sets `record_state` only. §3.10 |
| The confirmation dialog | On the status change to Arrived at Works. §3.10 |
| Drafts already at Arrived at Works | **Zero.** Nothing to lock. Statement included anyway. §4.9 |
| Scope | Imports only; the divergence is recorded in §5.1a and goes into CLAUDE.md. |

---

### §8 is empty. The design is complete.

Everything in this document is decided. There is no question outstanding, no
assumption standing in for an answer, and nothing I am waiting on.

**Three things to carry into Phase 1**, none of them open questions — they are
findings that change the work and are easy to lose between a design and a
keyboard:

1. **`submit_consignment.py:77` is the only site that sets `is_locked`.**
   Removing it without adding the write to the update route deletes the closed
   lock entirely, silently. §3.10, §7 item 6b.
2. **CLAUDE.md rule 8 is factually wrong** about where `is_locked` is set, and
   `helpers.py:168–173` encodes the two-part test in SQL separately from
   `is_closed()`. Both need correcting alongside the code. §1.2, §5.1.
3. **`SubmitRequirements.tsx` and the logistics/trucking `submission_errors()`
   stay.** Only imports' are removed. §5.1a.

---

## 9. Build order, if approved

Not a commitment — the sequence I would follow, so you can see the shape.

1. **Unify the display identities** into `consignment_number()` and
   `payment_reference()` (§3.4), and change the payment reference to mode +
   number. No schema change, independently shippable, and it makes the batching
   change smaller.

   > **HARD ORDERING RULE, added in revision 7: STEP 1 MUST SHIP BEFORE STEP 7.
   > NOT STILL UNSHIPPED WHEN STEP 7 CREATES THE FIRST REAL SECOND BATCH.**
   >
   > It is still unshipped. `consignment_reference()` (`imports/helpers.py`)
   > remains the only implementation, alongside the two dashboard copies
   > (`calculations.py:350`, `:842`) and `cross_module.py:182`.
   >
   > **Why it is a sequencing constraint and not a tidy-up.** Every list that
   > names an import row labels it by `instrument_number` — the reference
   > drill-downs (`whole/references.py`), the trucking queue, the notifications.
   > `instrument_number` moves to the GROUP, so it is shared by every batch of
   > one LC. The moment step 7 creates a real second batch, those lists render
   > **two rows carrying the identical reference**, which reads as a duplicate
   > rather than as a split. The count is right; the label lies about it.
   >
   > **And nothing fails while it is missing**, which is exactly why it gets
   > forgotten: today every group holds one batch, so one group means one label
   > and the duplication cannot occur. It is harmless right up to the commit
   > that makes it wrong, and then it is wrong everywhere at once with no error
   > anywhere.
2. **Fix finding 11** (no empty draft) and **finding 12** (export: one row per
   line, every field, drafts and deleted excluded). Both independent, and the
   export forces a full field inventory before the model moves.
2b. **Remove the submission rules and decouple closing from submitting** (§3.10).
   **DONE**, as its own PR, ahead of step 6 — it deletes `submission_errors()`
   outright, so repointing its `branch_id` / `supplier_id` rules onto the group
   in step 6 would have been work thrown away, and it takes
   `imports/helpers.py:953` off the 24-consumer list.

   Built exactly as specified below, plus four things found while building:

   - **`is_truly_closed` and `is_closed` agree on all existing data.** The
     one-part and two-part tests both return 148 on the 178 live rows; zero
     consignments are at "Arrived at Works" while unlocked. So the default
     list is unchanged today and the new rule only affects records created
     from now on — §4.9's finding, re-confirmed against the restored clone.
   - **`revert_old_values` has the same silent-skip bug as
     `revert_local_fields` had, for ITEM history, and no loud failure at all.**
     Out of scope here; it is in step 6, together with routing (§4.7 item 1).
   - **`itemPendingFields` survives the front-end deletion.** It is an
     input-layer prompt beside a field being typed, not a prediction of a gate,
     which is precisely where quality was moved TO. `consignmentSubmitSchema`,
     `pendingFields` and `submitRequirements` all went; that one did not.
   - **THIS MACHINE'S database carries no `alembic_version` row — production is
     fine.** Corrected after first reporting it the other way round. The local
     `supply_chain_erp` was dropped and rebuilt by `create_all` + `load_all` on
     **9 September 2026**, outside Alembic, which is why it has no revision row
     and why it now holds **178 consignments / 450 lines** rather than the
     183/455 this document measured. **Production is a different PostgreSQL
     instance: 191 consignments, `alembic_version` at `3142a00a5b31`. The gate
     is active there and working as designed.**

     **Outstanding, and it must be resolved before step 7.** Step 6 adds no
     tables, so an ungated `create_all` costs nothing while it runs. From step 7
     onward it does: a service start could half-apply a migration, which is the
     exact failure the gate exists to prevent. **The fix is a restore from the
     09:52 dump followed by `alembic upgrade head` — never `alembic stamp`.**

     Until then, any figure quoted from the local database says so.

   One change, because the pieces are only safe together:
   - `submission_errors()`, `missing_fields`, the eight frontend consumers, and
     imports' entry in `tests/test_submission_rules.py` — **not** logistics' or
     trucking's (§5.1a);
   - `is_closed()` to the one-part test, **and `helpers.py:168–173` with it**;
   - delete the `is_locked` write from `submit_consignment.py:77` **and add it to
     `update_consignment.py`** on the transition into Arrived at Works — never
     one without the other (§7 item 6b);
   - the confirmation dialog on the status change, not on submit;
   - rename `missing_only` to `drafts_only`;
   - a test for the transition, since no existing data exercises the app-side
     lock path (§1.2).

   Independent of batching and shippable on its own.
3. **Make revert fail loudly** on a history key matching no attribute (§4.7
   item 2). Two lines, independent of everything else, and it is what makes step
   6's boundary problem visible instead of silent. Do it *before* the migration,
   not after. **DONE, in the Phase 1 PR** — `revert_local_fields` now raises
   naming the orphaned keys. Only this half; the ROUTING half (§4.7 item 1)
   needs the group to exist and stays at step 6.
4. **Alembic Revision A — expand** (§4), behind a feature flag with the UI
   disabled. Purely additive, so a plain `downgrade` undoes it. **DONE** —
   `a1c4f27b93de`, applied and downgraded against a scratch clone of production;
   the post-downgrade schema is byte-identical to the pre-migration one.
5. **Update both loaders** and add the `post_load.py` checks (§4.7).
   ~~Remove the mapped attributes from `Consignment` and `ConsignmentItem`~~ —
   **moved to step 6** (§4.7): they are join columns for relationships in
   `masters`, so removing them without repointing the consumers breaks mapper
   configuration and the whole app with it. Route old history keys to the group
   in `revert` (§4.7 item 1) — also step 6, since it needs the attributes gone
   to be reachable.

   **Done, with Revision A, plus the minimum create logic pulled forward from
   step 7**: a create builds a group of one and an order line per shipment line.
   `batch_group_id` and `order_item_id` are NOT NULL, so without it the first
   save is a 500 rather than a missing feature. Allocation, batch creation,
   numbering and the freeze stay at step 7.
6. **DONE** — see revision 8. **Remove the mapped attributes** (moved here from
   step 5, §4.7) together
   with **the 24 header-field consumers** (§3.3, §7 item 2) — 9 live branch
   sites onto `works_branch_id` (the 10th died with step 2b), 14 date sites onto
   the order item per §3.3's four groups — and **the 14 count decisions**
   (§3.2) with their assertions. The largest piece, and the one to do while the
   flag is off.

   **Decided in revision 7, not yet built.** Scope, now that it has been
   counted rather than estimated:

   - the attribute removal is **219 references across 19 files**, not 24 and not
     116 (§4.7), because it takes three RELATIONSHIPS with it;
   - it **inverts the write path** — create/update must write the group and
     order item directly, which pulls the Pydantic schemas in (§4.7);
   - **both revert paths** get routing and a loud failure, not just the header
     one (§4.7);
   - `notifications/scanner.py` is in scope (§5.2);
   - the count assertions are **two suites**, because no HTTP assertion can
     discriminate rows from groups until a group holds two batches (§3.2).

   Verification: `configure_mappers()` against a scratch database — the bare
   import cannot see a broken mapper, and this step is almost entirely mapped
   attributes moving. Then the real HTTP routes: create, update, list, detail,
   submit, revert and all five dashboards, because what remains after that is
   read paths, which the helpers cannot prove.
7. **Backend:** group and order-item models, allocation with the row lock
   (§6 B3), batch creation, numbering (§3.5), the group freeze (§3.9).
8. **Frontend:** the Step 3 allocation screen, list rows and blue highlight,
   expanded per-item view, the `SearchableSelect`-backed country (ISO 3166) and
   works dropdowns, the per-item price-basis checkbox and the second price
   field.
9. **Payments:** the group move (§4.4), insurance, the addenda table.
10. **Chatbot metadata**, verified by importing `backend.*` from inside
    `chatbot_backend/`.
11. **CLAUDE.md**, same PR — rules 1, 2 and 11 (§5.1), the frozen `batch_no`
    column (§3.6), and the group freeze (§3.9).
12. **Alembic Revision B — contract** (§4), a release later, once batching has
    run in production. Backup first.
