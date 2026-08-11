"""
Database schema description handed to the SQL agent.

Two ways to get the schema:

  * DB_SCHEMA_TEXT below - a hand-written summary, always available, cheap in
    tokens, and works before the database is even up.
  * live_schema() - reads information_schema from the real database.

get_schema_text() prefers the live schema and falls back to the static one,
so the SQL agent keeps working while the database is still being built.

Keep DB_SCHEMA_TEXT in sync with the ERP models, which own the schema:
supply_chain_erp-master/app/{masters,imports,logistics,trucking}/models.py and
app/loading/schemas/*.py.
"""

from functools import lru_cache

# ---------------------------------------------------------------------
# Static summary. Grouped by module the way the business talks about them.
# ---------------------------------------------------------------------
DB_SCHEMA_TEXT = """
=== HOW THIS DATABASE IS SHAPED (read first) ===

Two ID styles live side by side, and mixing them is the most common mistake:

  * The STORES tables (stock, issuance, store_requisition, purchases_data) key
    on items.item_code, a TEXT business code like '7230-60'. Join them with
      JOIN items i ON i.item_code = <table>.item_code
  * The ERP modules (imports, logistics, trucking) key on integer surrogate
    ids. consignment_items carries BOTH: item_id (integer -> items.id) and a
    copied item_code/item_name text snapshot taken when the line was entered.
    Join those on item_id.

SOFT DELETES. Every ERP table carries is_deleted; rows are never physically
removed. ALWAYS add "AND <alias>.is_deleted = false" when querying
consignments, consignment_items, logistics_*, trucking_*. The stores tables
(stock, issuance, store_requisition, purchases_data) have NO is_deleted column
- do not add the filter there, it will error.

DRAFT ROWS. consignments, logistics_consignments and trucking_consignments
carry record_state ('draft' / 'submitted'). Everything loaded from the
workbooks is 'draft'. Do NOT filter on record_state unless the user asks about
completeness - filtering it out hides essentially all historical data.

=== MASTER TABLES ===

items(id PK, item_code UNIQUE, name, default_specification,
      default_unit_of_measurement, category, is_active, is_verified)
    Item master. `name` is the item name (was `item`), `default_specification`
    the spec (was `specs`). There is NO material_standard or group_name column
    any more - `category` carries the grouping. Retired items have
    is_active = false, and many also have '(Deleted)' in their name.

suppliers(id PK, name, country, city, contact_name, phone, email,
          default_currency, default_payment_terms, is_active, is_verified)

branches(id PK, name, code, city, address, is_active, is_verified)
    THE IMPORTS BRANCH TABLE. `consignments.branch_id` -> `branches.id` is the
    only way imports carry a branch.
    `name` HOLDS THE SHORT CODE, not a legal name. The five real values are
    'QE', 'QEN', 'QCL', 'QBL-II', 'QH'.
    `code` IS NULL ON EVERY ROW - never filter or join on it, it matches nothing.
    RESOLVE IT THROUGH v_branch_aliases, never v_branches directly:
        JOIN branches br ON br.id = c.branch_id
        JOIN v_branch_aliases a ON a.alias = br.name
    The alias map carries every spelling including 'QBL-II' and 'QH', so EVERY
    consignment resolves - a row that fails to join is a bug, not an unknown
    branch. (An earlier version keyed on a `legal_name` column and had neither,
    which matched ZERO rows and is how "how many import consignments are of QE"
    once answered 0 when the true answer was 34.)
    Use LEFT JOIN when adding the branch for display - a consignment with a NULL
    branch_id exists and an INNER JOIN drops it.

works(id PK, name, code, ntn_strn, note, is_active, is_verified)
ports(id PK, name, country, port_type, un_locode, used_as, is_active)
clearing_agents(id PK, name, licence_no, contact_name, phone, primary_port_id)
hs_codes(id PK, item_id -> items.id, code, is_active)

=== STORES / INVENTORY ===

stock(id PK, item_code -> items.item_code, item_name, branch, hold_qty,
      stock_qty, stock_qty_amount, available_qty, available_amount,
      reorder_level, rank)
    Current snapshot, ONE ROW PER ITEM PER BRANCH. NOT a history table - it has
    no date column at all, so any "stock over time" question must be answered
    from issuance (consumption) or purchases_data (inflow) instead.
    COUNTING: because a stocked item has one row per branch, COUNT(*) here
    counts item-branch pairs, NOT items. Any "how many items ..." question must
    aggregate to item_code first (GROUP BY item_code, or COUNT(DISTINCT
    item_code)) or it overstates the answer - 1,407 rows are at or below zero
    available, but they are far fewer DISTINCT items - the gap is the whole
    point, and the live figures are in the profile block.
    available_qty = stock_qty - hold_qty, and it is the quantity actually
    usable; prefer it over stock_qty for anything about availability.
    `rank` is the business's A/B/C rarity class - A rarest, C least rare. It is
    per item PER BRANCH like everything else on this table, so one item can be
    A at one branch and C at another (103 of them are). Use it to PRIORITISE a
    list of items, never as a filter the user did not ask for. See the item
    rank term for the counting rules.
    `reorder_level` exists but is EMPTY on every row today - there is no safety
    stock or reorder policy in this data. Do not present it as one, and do not
    treat a NULL here as "reorder level is zero".

issuance(id PK, issuance_code, item_code -> items.item_code, item_name,
         specification, department, branch, issue_to_others, authorized_by,
         issued_by, received_by, description, ref_no, demand_ref_no,
         quantity, status, from_date, unit_price, total_price, job_number)
    Consumption transactions - the main demand history, and the largest
    table in the database. Its date range and row count are in the profile
    block, not here; they change on every load. from_date is the issue date; use it for consumption
    trends and burn-rate calculations.
    issuance_code is the issuance DOCUMENT number and is NOT unique: one
    document issues many items (thousands cover more than one item code, the
    largest covers 222). COUNT(*) counts issue LINES; for the number of
    issuance documents use COUNT(DISTINCT issuance_code).

store_requisition(id PK, item_code -> items.item_code, item_name, ref_no,
                  department, branch, prepare_date, description, required_by,
                  req_quantity, pur_quantity, pending_quantity, last_purchase,
                  previous_price, required_date, status, sourced_by,
                  previous_supplier, original_required_date, stock_in_date)
    Internal demand raised by departments. pending_quantity = not yet bought.

purchases_data(id PK, item_code -> items.item_code, item_name, specification,
               po_number, po_date, ref_no, qty, branch, amount, ppc_store,
               required_d, purchase, mop, dc_no, bill_no, sourcing_o, supplier)
    Local purchases. `purchase` is the date it landed
    and `required_d` the date it was needed - the gap between them is the
    observed procurement lead time. There is no separate purchase_order table
    any more; po_number and po_date live here.

=== IMPORTS ===

consignments(id PK, branch_id -> branches, supplier_id -> suppliers,
             clearing_agent_id -> clearing_agents,
             loading_port_id -> ports, delivery_port_id -> ports,
             requisition_date, works, origin, currency, consignment_type,
             incoterm, po_date, required_date, mode_of_shipment,
             cargo_readiness_date, etd, eta, eta_works, payment_instrument,
             instrument_number, opening_or_retirement_date, exchange_rate,
             rate_booked_on, rate_source, foreign_total, pkr_total,
             current_status, effective_date, remarks, gd_number,
             gd_filing_date, free_days_allowed, gate_out_date,
             demurrage_or_detention_paid, container_detention,
             record_state, is_locked, is_deleted, created_by_id)
    One import consignment (header). current_status is the transit status, in
    this order: 'TT/LC in Process', 'Under Production', 'Ready Awaiting
    Sailing', 'In Transit', 'Arrived at Port', 'Under Custom Clearance',
    'Under Examination', 'Under Assessment', 'Arrived at QFL', 'On Road',
    'Arrived at Works'. "On water" / "sailing" = 'In Transit'.
    NOTE: the old import_details.file_no commodity category ('Shafts',
    'Foundry Material', ...) does NOT exist in this schema. To find imports of
    a commodity, match consignment_items.item_name / description / item_code.

consignment_items(id PK, consignment_id -> consignments, item_id -> items.id,
                  item_code, item_name, specification, hs_code, quantity,
                  unit_price, unit_of_measurement, batch_no, requisition_type,
                  elc, alc, variance_absolute, variance_percentage,
                  reference_number, job_number, mo_number, description,
                  is_deleted)
    The item lines of an import. item_code/item_name are a text SNAPSHOT taken
    when the line was entered; item_id is the live link to the master. elc and
    alc are the estimated and actual landed cost, entered by hand per line.
    MOST IMPORT LINES ARE NOT IN THE ITEM MASTER. 294 of 451 lines (65%) have an
    item_code with no matching items row - 291 of those are `TMPNL...`
    placeholder codes created at entry time. So:
      * NEVER INNER JOIN consignment_items to items. It silently discards
        two thirds of every import answer. Use LEFT JOIN, always.
      * To find an item on the import side, match the line's OWN text -
        ci.item_name ILIKE '%hardner%' - NOT items.name through a join.
        Asked whether any hardner is imported, a join through items found ONE
        code; matching ci.item_name found FOUR (26382-60, 26838-60, TMPNL0069,
        TMPNL0125) across 8 lines. Three of those four are absent from the
        master entirely.
      * The snapshot and the master can also DISAGREE on spelling for the same
        code ('Hardener' vs 'Hardner' on 26382-60), so match both spellings.
    Corollary: an item can be actively imported and still have NO stock row and
    NO master row. A stock-based query cannot see it - say so rather than
    reporting "not imported".

eta_revision_history(id PK, consignment_id -> consignments, eta_type,
                     previous_eta, new_eta, cause_of_revision, user_id)
    One row per ETA change. Slippage = the current eta minus the FIRST
    previous_eta ever recorded for that consignment.

status_update_history(id PK, consignment_id -> consignments, previous_status,
                      new_status, effective_date, remarks, user_id)
payments(id PK, consignment_id -> consignments, retirement_date, value,
         payment_exchange_rate, bank_charges, status, bank_reference,
         is_deleted)

=== LOGISTICS IS FOUR SEPARATE THINGS - DO NOT MIX THEM ===

"Logistics" covers four distinct activities. They live in different tables,
answer different questions, and their row counts are NOT comparable. Decide
which one the question is about before writing anything, and never add them
together into a single "logistics" total.

  1. EXPORT / LOCAL ORDERS - logistics_consignments (+ logistics_items)
     The order itself: customer, incoterm, ports, shipping line, costs, status.
     "How many export orders", "which orders are sailing", "export costs".

  2. PACKING - logistics_packages
     How the goods were boxed: packing works, colour code, packing dates,
     packing cost, gross weight. One row per packing record, several per order.
     "Packing delays", "packing cost", "what is packed".

  3. CONTAINERS - logistics_containers
     One row per container booked against an order, with its type.
     "How many containers", "container mix". Note container_no is NULL on every
     row - the source recorded a COUNT per type, not registration numbers.

  4. TRUCKING / INBOUND-OUTBOUND - trucking_consignments (+ trucking_vehicles)
     Road movement, a SEPARATE module with no foreign key to the above. The
     only link is reference_no as free text, so never invent a join between
     trucking and logistics.

EXPORT DOCUMENTATION is a fifth activity the business tracks, but it is NOT in
this database - no table holds a document status. Say so plainly when asked;
do not substitute logistics_consignments.current_status, which is the shipment
stage and says nothing about paperwork.

A question that names one of these means only that one. "How many shipments"
is ambiguous across (1) and (4) - ask, or answer both with a label saying which
is which.

=== LOGISTICS / EXPORTS ===

logistics_consignments(id PK, order_type, department, origin_country,
                       origin_city, origin_province, customer_name, mo_no,
                       batch_no, batch_label, incoterm, pol, pod,
                       shipping_line, clearing_agent, booking_no,
                       port_in_date, etd_sailing_date, cro_arrival_date,
                       actual_arrival_date, packing_cost,
                       transportation_charges, container_detention, insurance,
                       trucking_lhr_to_khi, fumigation_cost, lashing,
                       qfl_charges, qfl_container_movement,
                       custom_clearance_charges, port_charges, dhl_charges,
                       sea_air_freight, current_status, effective_date,
                       gate_out_date, sent_to_trucking, record_state,
                       is_locked, is_deleted, created_by_id)
    One outbound order (export or local). order_type is 'Export' or 'Local';
    department is the product line ('Sugar', 'Cement'). mo_no holds the EXPORT
    NUMBER and batch_label the batch - together they identify the order in the
    business's own language.
    current_status - THE SEVEN VALUES THAT ACTUALLY EXIST, with live counts:
        'Under Production' 584 | 'Under Packing' 465 | 'Transportation' 212
        'Delivered' 111 | 'On Water' 38 | 'At QFL' 10 | 'At Port' 4
    There is NO 'Sailing', NO 'Gate Out' and NO 'Packed' in this column - those
    are the ERP's enum names, not what the loaders wrote. Filtering on them
    returns 0 rows and no error. Not-yet-shipped is 'Under Production' /
    'Under Packing'; shipped-not-arrived is 'Transportation' / 'On Water';
    arrived-not-closed is 'At Port' / 'At QFL' - THESE COUNT AS ARRIVED, NOT
    in transit (business rule); closed is 'Delivered'.
    The cost columns are the export expenditure breakdown; total shipping cost
    is their sum, not a stored column.

logistics_items(id PK, consignment_id -> logistics_consignments, job_no,
                item_detail, quantity, unit_weight, gross_weight,
                planned_rfd_date, actual_rfd_date, is_deleted)
    What is on the order. RFD = Ready For Dispatch; planned vs actual measures
    schedule adherence. job_no may hold several joined job numbers.

logistics_packages(id PK, consignment_id -> logistics_consignments,
                   colour_code, packing_works, packing_ready_date,
                   packing_date, quoted_packing_cost, actual_packing_cost,
                   gross_weight, status, is_deleted)
    One row per packing record. status - the four real values, with counts:
        'Packed' 793 | 'Packing under manufacturing' 135 | 'Under Packing' 28
        'Under Final Packing' 6
    There is no 'Pending' and no 'Gate Out' here. Note 'Under Packing' means
    something different in this column than in logistics_consignments -
    a package still being packed, not an order still being packed.

logistics_containers(id PK, consignment_id -> logistics_consignments,
                     container_no, container_type, is_deleted)
    One row per container. container_type is like "20' Standard",
    "40' Flat Rack", 'LCL', 'AIR'. container_no is usually NULL for loaded
    history - the source recorded counts per type, not individual numbers.

NOTE - export paperwork is NOT in this database. The source workbook tracks 22
    documents per export (customs / customer / bank invoices, packing lists,
    bills of lading, GD, certificates of origin), but no table holds a document
    status. Questions about pending paperwork, document completion percentages
    or "which documents are outstanding" CANNOT be answered - say so plainly
    rather than substituting logistics_consignments.current_status, which is
    the shipment stage and means something different.

logistics_status_history(id PK, consignment_id, previous_status, new_status,
                         effective_date, remarks, user_id)

=== TRUCKING (road movements) ===

trucking_consignments(id PK, movement_type, source, source_ref,
                      execution_date, transporter_name, shifting_type,
                      item_details, pickup, destination, reference_no,
                      quoted_freight, actual_freight, payment_status,
                      paid_amount, detention, dispatch_note_date, eta_works,
                      remarks, record_state, is_locked, is_deleted,
                      created_by_id)
    One trucking job. movement_type is 'Inbound' / 'Outbound' /
    'Intrafactory'. reference_no is the shipment reference or IDM number.
    Freight savings = quoted_freight - actual_freight (computed, not stored).
    There is NO job-level status column - status lives on each vehicle.

trucking_vehicles(id PK, consignment_id -> trucking_consignments,
                  vehicle_number, vehicle_type, no_of_packages, driver_phone,
                  net_weight, gross_weight, container_no, container_type,
                  tracking_status, is_deleted)
    One row per truck. A job moves on several trucks, each advancing on its
    own. tracking_status has EXACTLY TWO values in the data:
        'Delivered' 246 | 'Going to load' 218
    So on the road there is no in-between: a truck is delivered or it is not.
    "In transit by road" therefore means tracking_status <> 'Delivered', not
    some third status. A job counts as closed only when EVERY one of its
    vehicles is 'Delivered'.

=== SYSTEM (rarely useful for business questions) ===

users(id PK, username, role_id -> roles, is_active), roles(id PK, name),
activity_logs(id PK, user_id, username, action, method, path, entity_type,
              entity_id, status_code, detail, created_at)

=== SEMANTIC VIEWS - PREFER THESE OVER REBUILDING THE DEFINITION ===

There is deliberately NO view for shafts or scrap. A material named in a
question is just an item whose NAME contains that word - derive it in SQL
with items.name ~* '[[:<:]]word s?[[:>:]]' (whole word, singular stem), and
say in the answer which rule you used so the user can correct it.
The one exception is IMPORTED shafts, which are a fixed three-type list -
see v_import_shafts.


Each of these encodes a business definition that is easy to get subtly wrong.
When a question is about one of them, SELECT FROM THE VIEW rather than writing
the filter yourself: the view is the definition, and rewriting it by hand is
how the same question ends up with different answers on different runs.

v_item_stock_position(item_code, item_name, branches_held_at, stock_qty,
                      hold_qty, available_qty, available_amount, is_out_of_stock)
    Stock collapsed to ONE ROW PER ITEM across all branches. Use this for any
    "how many items ..." stock question - the raw `stock` table has one row per
    item per branch, so counting it counts item-branch pairs instead.

v_out_of_stock_items(item_code, item_name, branches_held_at, stock_qty,
                     hold_qty, available_qty)
    Items with nothing usable left ANYWHERE. An item at zero in
    one branch while another still holds it is not here.

v_item_types(item_type, display_name, item_codes, category)
    One row per distinct item NAME. A "type" is a name, not an item_code -
    each code is a name+spec variant. COUNT(*) here answers "how many types".

v_item_consumption_monthly(item_code, period, quantity, value, issue_lines)
    The demand signal: issued quantity per item per month, already restricted
    to status 'Issue' (excluding 'Hold' / 'HoldIssuence', which are not
    consumption). Use this for trends, burn rate and forecast series.

=== TWO PATTERNS TO WRITE YOURSELF ===

These used to be views. Write them directly - but write them THIS way, because
both have a trap, and the in-transit one carries a business ruling you must not
re-derive: 'At Port' and 'At QFL' are ARRIVED, not in transit.

GOODS IN TRANSIT - inbound and outbound live in different tables with different
vocabulary, so a question about what is moving needs BOTH sides UNIONed, with a
literal label saying which side each row came from:

    SELECT 'Import' AS direction, c.id, c.instrument_number AS reference,
           s.name AS counterparty, c.current_status, c.etd, c.eta
    FROM consignments c
    LEFT JOIN suppliers s ON s.id = c.supplier_id
    WHERE c.is_deleted = false AND c.current_status ILIKE '%in transit%'
    UNION ALL
    SELECT 'Export', lc.id, lc.mo_no, lc.customer_name, lc.current_status,
           lc.etd_sailing_date, lc.actual_arrival_date
    FROM logistics_consignments lc
    WHERE lc.is_deleted = false
      AND lc.current_status IN ('Transportation', 'On Water')
    UNION ALL
    SELECT 'Road', tc.id, tc.reference_no, tc.customer_name, 'Going to load',
           tc.created_at::date, NULL
    FROM trucking_consignments tc
    WHERE tc.is_deleted = false
      AND EXISTS (SELECT 1 FROM trucking_vehicles tv
                  WHERE tv.consignment_id = tc.id AND tv.is_deleted = false
                    AND tv.tracking_status <> 'Delivered')

    NARROWING IT TO ONE MATERIAL (shafts, resin, scrap) does NOT change the
    counting unit. Join to the line table to filter, then count the CONSIGNMENT:

        SELECT COUNT(*) FROM (
            SELECT DISTINCT lc.id
            FROM logistics_consignments lc
            JOIN logistics_items li ON li.consignment_id = lc.id
             AND li.is_deleted = false
            WHERE lc.is_deleted = false
              AND li.item_detail ~* '[[:<:]]shafts?[[:>:]]'
              AND lc.current_status IN ('Transportation', 'On Water')
            ...same for the imports and road arms...
        ) t

    One consignment carrying eight shaft lines is ONE shipment, not eight.
    Counting lines on one arm and consignments on another returned 19, 5, 18 and
    13 for the same question on four consecutive runs - the arms were right
    every time, only the unit moved.

    The trap is answering from ONE side and reporting it as the whole picture.
    NO STATUS STRING EXISTS ON MORE THAN ONE SIDE. Inbound says 'In Transit';
    outbound says 'Transportation' / 'On Water'; road says 'Going to load'.
    Filtering all three on one vocabulary returns 0 from the other two and
    reports it as an answer.

PROCUREMENT LEAD TIME - observed from history, because there is no planning
table in this schema (the old ab_items with lead_time_days and safety_days is
gone, and safety days have NO source at all):

    SELECT p.item_code,
           COUNT(*) AS purchases,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY (p.purchase - p.required_d))
               AS median_lead_days
    FROM purchases_data p
    WHERE p.purchase IS NOT NULL AND p.required_d IS NOT NULL
      AND p.purchase >= p.required_d
    GROUP BY p.item_code

    The trap is AVG instead of the median - one stalled order then sets the
    planning figure for the item. Also exclude rows where purchase < required_d
    (arrived before it was needed); those are data errors, not negative lead
    times, and they drag the average below zero.

=== JOIN NOTES ===

* Stores tables join to items on TEXT item_code:
    JOIN items i ON i.item_code = s.item_code
* consignment_items joins to items on INTEGER item_id -> items.id. It also
  carries its own item_code text snapshot; prefer item_id for the join.
* Imports fan out: consignments -> consignment_items / eta_revision_history /
  status_update_history / payments, all on consignment_id.
* Logistics fans out: logistics_consignments -> logistics_items /
  logistics_packages / logistics_containers, all on consignment_id.
* Trucking fans out: trucking_consignments -> trucking_vehicles on
  consignment_id.
* Trucking is NOT linked to logistics or imports by a foreign key. The link is
  by reference_no text only, so do not invent a join between them.
* store_requisition.ref_no matches purchases_data.ref_no but has no FK.
* Always filter is_deleted = false on consignments, consignment_items,
  logistics_* and trucking_*. The stores
  tables have no such column.
* `stock` has no date column - it is a snapshot. Any question about stock
  "over time" must use issuance (consumption) or purchases_data (inflow).
"""


def live_schema() -> str:
    """Read the real schema out of Postgres. Returns '' if the DB is down."""
    from sqlalchemy import text

    from backend.config import get_engine

    query = text(
        """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    try:
        with get_engine().connect() as conn:
            rows = conn.execute(query).fetchall()
    except Exception:
        return ""

    if not rows:
        return ""

    tables: dict[str, list[str]] = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(table_name, []).append(f"{column_name} {data_type}")

    return "\n".join(
        f"{name}({', '.join(cols)})" for name, cols in sorted(tables.items())
    )


@lru_cache(maxsize=1)
def get_schema_text() -> str:
    """Live schema when the database is reachable, static summary otherwise."""
    live = live_schema()
    if not live:
        return DB_SCHEMA_TEXT
    # The static text carries the join notes and semantics that
    # information_schema cannot express, so we send both.
    return f"{DB_SCHEMA_TEXT}\n\n=== LIVE COLUMNS FROM DATABASE ===\n{live}"
