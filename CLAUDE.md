# Import Status Management System

Internal Django app replacing a manual imports status Excel sheet.
Runs on the office LAN. Roughly 10-30 users. Not internet-facing.

This system tracks a consignment from requisition through payment, shipping,
customs clearance and arrival at works. The Excel sheet it replaces is still
being used to run the business, so business rules are not to be invented —
if something is ambiguous, stop and ask rather than guessing.

## Stack — do not deviate without asking

- Django 5.2 LTS + PostgreSQL 16 (Python 3.12, conda env named `imports`)
- Server-rendered Django templates + HTMX + Alpine.js + Tailwind (standalone CLI, no npm)
- django-crispy-forms with crispy-tailwind
- django-simple-history for audit trails
- **No React, no DRF, no SPA.** The UI is HTML fragments returned by Django views.
- Exports: openpyxl for Excel, WeasyPrint for PDF

## Apps

| App | Owns |
|---|---|
| `accounts` | Custom User (`AUTH_USER_MODEL = 'accounts.User'`), roles, permission mixins |
| `masters` | Supplier, Branch, Item, Port, ClearingAgent, Works, Currency, UoM |
| `consignments` | Consignment header, ConsignmentItem lines, all 7 wizard steps, status and ETA history |

## Roles

| Role | Enter | Edit existing | Reports | Manage users |
|---|---|---|---|---|
| Admin | yes | yes | yes | yes |
| Manager | yes | yes | yes | no |
| Entry Operator | yes | own drafts only | yes | no |
| Viewer | no | no | read-only list and reports | no |

Viewers **can** see values, prices and PKR amounts. Nothing financial is hidden by role.

Masters (Supplier, Port, ClearingAgent, Item, Branch, Works) are managed by
Managers and Admins through a Masters screen reachable from the main nav —
not through the Django admin. Entry Operators and Viewers don't get that nav item.

Enforce permissions server-side with mixins and decorators. Template `{% if %}`
hides things from view; it is never the security boundary.

---

# Data model rules

## 1. Consignment (header) to ConsignmentItem (lines)

One consignment carries many items. This is the single most important structural
rule in the system — flattening it breaks the finance and clearance modules.

**Header (`Consignment`) holds:**
branch, supplier, country of origin, currency, consignment type (EFS / Regular),
PO date, payment instrument type and number, instrument date, works,
exchange rate, rate date, rate source, current status, system remarks,
user remarks, clearing agent, GD number, gate out date, free days, ELC, ALC.

**Line (`ConsignmentItem`) holds:**
requisition type, reference no, job no, MO no, item, item code, specification,
quantity, unit of measure, batch no, H.S. code, foreign unit price.

## 2. Requisition details belong to the ITEM, not the consignment

Reference No, Job No and MO No are properties of the demand that generated a
line item, not of the shipment. Because they are driven by requisition type,
**requisition type also sits on the line.**

A single consignment can therefore carry Store items and Engineering items
together. Anywhere the requisition type is displayed for a whole consignment
(list view, reports), show the distinct set — e.g. "Store + Engineering".

| Requisition type | Fields that appear |
|---|---|
| Store | Reference No |
| Engineering | Reference No + Job No + MO No |
| Others | Free-text description of the purpose |

All of these are nullable and may be filled later. They still count toward the
item's pending-information badge.

Implement the mapping once as a rules dict, validated in the form's `clean()`.
Mirror the same dict in JS for the UX. Adding a requisition type later must be
a one-line change, not a hunt through if-statements.

## 3. Money is DecimalField, never FloatField

- Foreign amounts and unit prices: `max_digits=18, decimal_places=4`
- Exchange rate: `max_digits=12, decimal_places=6`
- PKR amounts: `max_digits=20, decimal_places=2`

## 4. Calculated values are computed, never keyed in

| Value | Derivation |
|---|---|
| Line foreign total | quantity x foreign unit price |
| Consignment foreign total | sum of line totals |
| Consignment PKR total | foreign total x exchange rate (**store this**, rates move) |
| Transit time | ETA minus ETD, in days |
| Clearance time | Gate out minus the actual arrival date — the date status became "Arrived at Port" in the `StatusChange` log. Falls back to ETA only if that status was never recorded |
| Variance | ALC minus ELC, stored both as absolute and as a percentage |

Exchange rate is booked **on the consignment** with the date it was taken and
its source. Never convert a stored foreign value using a live or current rate —
the same record would show a different PKR figure every time it was opened,
and no printed report could be reconciled.

## 5. History tables, never text fields

**`ETARevision`** — consignment, old_eta, new_eta, reason, changed_by, changed_at.
The "1st ETA was X, 2nd was Y" string shown in reports is **generated** from this
table. Storing it as text destroys the delay analytics and can be overwritten by
a user edit.

**`StatusChange`** — consignment, from_status, to_status, changed_by, changed_at.
Gives the audit trail and stage-ageing analysis ("average days under examination").

Slippage on the list view = current ETA minus the **first** ETA ever promised.

## 6. Remarks are two separate fields

- `system_remarks` — auto-generated, read-only, built from ETA and status history
- `user_remarks` — free text entered by the user

They are displayed concatenated in reports but never share an input.

## 7. Payments are a child table

`Payment` — consignment, date, value, status (Paid / Unpaid), reference.
Partial payments are normal and expected. Labels are instrument-driven and the
logic lives in exactly one place:

| Instrument | Number label | Date label |
|---|---|---|
| LC | LC number | Retirement date |
| Adv | Advance payment reference | Opening date |
| DP | DP document number | Opening date |
| CAD | CAD document number | Opening date |

## 8. Draft vs submitted

Almost every field can be filled later. Consignments therefore carry a draft
state and a completeness calculation.

- `save_draft` accepts anything, including empty required fields
- `submit` enforces the full rule set
- Django forms validate all-or-nothing by default, so this needs a `submitting`
  flag checked inside `clean()` — two validation paths on one form

Fields commonly filled later: batch no, H.S. code, consignment type, unit price,
exchange rate, rate date, reference/job/MO numbers, and the entire clearance
and landed-cost modules.

## 9. Status list (ordered — do not reorder)

TT/LC in Process, Under Production, Ready Awaiting Sailing, In Transit,
Arrived at Port, Under Custom Clearance, Under Examination, Under Assessment,
Arrived at QFL, On Road, Arrived at Works

Store as a `TextChoices` with an explicit order attribute. The list view groups
these into six stages: Pre-shipment, Production, In transit, Clearance, Inbound, Closed.

"Arrived at Works" is treated as closed and is **hidden from the list by default**.

## 10. Free text is banned for anything reported on

Supplier, branch, works, port of loading, port of delivery, clearing agent and
item all resolve to master tables. Free text guarantees three spellings of one
supplier and destroys supplier-wise reporting.

## 11. ELC and ALC are manual, per-item entries — never calculated

Estimated Landed Cost and Actual Landed Cost are typed in by a user, per item,
in PKR. Nothing in this system derives them. Goods value, bank charges and
demurrage are shown alongside as reference figures only, to sanity-check what
is entered — they are never summed into ELC or ALC. Duty, freight and
clearing-agent fees are not tracked anywhere in this system; the figures here
are a partial picture and are never a substitute for the numbers a user enters.

Record the entering user and timestamp on each figure separately — ELC and ALC
are usually entered weeks apart by different people, so one `updated_by` /
`updated_at` pair on the line is not enough to answer who entered which.

## 12. Item master carries defaults — the line stores its own values

Item holds multiple H.S. codes (one-to-many — an item can classify differently
by variant or origin), a default UoM and a default specification. Category is
free text with existing values offered as suggestions, not a fixed choice list.

These populate the consignment line when the item is picked, but the line
stores its own copy from that point on. It never re-reads the master
afterwards, so changing the master later does not retroactively change past
consignments.

## 13. Inline creation during data entry — Supplier, Item, Port, Clearing Agent only

Any role that can enter data may create these four masters inline, without
leaving the wizard: type a name that matches nothing, and a small form appends
it to the master with `verified=False`. Unverified records surface in a review
queue in Masters until a Manager or Admin opens and saves them, confirming the
details are correct. Ports also need a Sea/Air type captured at creation, since
mode-based filtering elsewhere depends on it.

Branch and Works are **never** creatable inline — they are our own entities
and must exist beforehand, set up deliberately through Masters, not typed into
existence mid-consignment.

---

# Wizard modules

The wizard is seven steps. Status and Remarks are one screen — a status change
and its context are usually entered together, and splitting them doubled the
navigation for no benefit.

1. **Consignment** (`wizard_step1.html`) — header fields plus repeating item panels
2. **Finance** (`wizard_step2_finance.html`) — instrument type/number/date, works, per-item unit price, FX conversion
3. **Shipping** (`wizard_step3_shipping.html`) — mode, POL, POD, readiness date, ETD, ETA, transit time, ETA works
4. **Payments** (`wizard_step4_payments.html`) — partial payments table
5. **Status & remarks** (`wizard_step5_status_remarks.html`) — status history, ETA revision log, system remarks (generated) and user remarks (free text)
6. **Clearance** (`wizard_step6_clearance.html`) — agent, GD number, gate out, free days, clearance time
7. **Landed cost** (`wizard_step7_landed_cost.html`) — ELC, ALC, variance

Each step saves independently. Users are interrupted mid-entry constantly;
never require a single end-of-wizard submit.

The static prototypes toggle new-vs-edit with a `?id=` query string on each
wizard file, carried through Continue/Back/stepper links, with one mock
record's worth of data hand-written into each file's JS. That's a stand-in
only. In Django these are distinct URLs — `/consignments/new/` for a fresh
draft and `/consignments/<pk>/edit/<step>/` for an existing one — resolved
from the database, not a query string parsed in the browser.

---

# Frontend conventions (established — match these)

## Visual language

Dense, flat and functional. Navy `#0F1B2D` with a brass `#B8873B` accent.
No drop shadows, no heavily rounded cards, no decorative whitespace. Border
radius is 4px throughout. Tabular numerals on every number, code and date.

These are screens operators stare at all day. Information density beats elegance.

Colour is meaning, not decoration:
- brass — needs attention or is user-editable emphasis
- green `#1F7A5A` — complete, on time, paid
- amber `#B4531A` — pending, approaching a deadline
- red `#A32F2F` — late, unpaid, overdue

## Existing screens — read these before building new ones

In `templates/consignments/`:

- `consignment_list.html` — list, filters, six-stage pipeline strip, sortable
  columns, ETA revision tags, slippage, free-days countdown, Excel and PDF export
- `wizard_step1.html` — header fields plus stacked item panels with per-item
  requisition details and pending badges
- `wizard_step2_finance.html` — instrument with type-driven labels, per-item
  pricing with live totals, PKR conversion with rate date and source

New screens must match their structure, spacing and component vocabulary.
When in doubt, copy the pattern from an existing file rather than inventing one.

## Patterns to reuse, not reinvent

**Pending information.** Any incomplete record shows exactly what is missing,
by name, on hover. This appears as per-item badges on Step 1, a banner on Step 2,
and a flag column on the list. It should be one shared partial, so a field added
later surfaces everywhere automatically.

**Conditional fields.** Driven by a single rules object per screen
(requisition type on Step 1, instrument type on Step 2). Never scattered
if-statements in the template.

**Calculated values.** Displayed as read-only derived output, greyed, with the
derivation stated. Partial data produces a provisional total marked with an
asterisk, never a blank.

**Carried-forward context.** Later wizard steps show a read-only strip of the
key header fields from earlier steps, so the user always knows which consignment
they are editing.

**Exports.** Always export the **filtered** set, never the whole table.
Excel carries every column; PDF carries a readable subset in landscape.
Both are one Django view: `GET /consignments/export/?<same querystring>&format=xlsx|pdf`,
sharing the list view's queryset function so filters cannot drift apart.

**List view table header.** Do not re-add `position:sticky` to
`consignment_list.html`'s table header. The table sits inside an
`overflow-x:auto` container, and a sticky header there overlaps the first
data row instead of staying pinned. This was tried and reverted.

## Templates and static

```
templates/
  base.html
  partials/          HTMX fragments, prefixed with _
  consignments/
  accounts/
static/
  css/input.css      Tailwind source
  js/app.js          Alpine components
```

---

# Conventions

- `snake_case` fields, `PascalCase` models, singular model names
- Every model carries `created_at`, `updated_at`, `created_by`
- Nothing is ever hard-deleted. Every model carries a soft-delete flag so
  closed and deleted records stay available to reports
- Index every column used in a list filter: status, branch, supplier, ETA,
  requisition type, consignment type
- Use `select_related` and `prefetch_related` on the list view. N+1 queries are
  the only realistic performance risk in this system
- Business logic lives in models and forms, never in templates
- Before every commit: `python manage.py makemigrations --check --dry-run`
  and `python manage.py check`

# Working agreement

Backend is written by an intern; frontend by the project owner. Neither invents
a field name, URL name or status value alone — it is written here first, then
implemented. If something needed is missing from this file, add it in the same
commit as the code.

Branch, commit, push, open a pull request. `main` is never committed to directly.

# When to stop and ask

Business rules around imports, LCs, customs and duty are domain knowledge, not
something to infer from context. If a rule is unclear or a requested change
appears to contradict something written above, raise it rather than resolving it
silently. A wrong assumption baked into the data model is expensive; a question
is cheap.
