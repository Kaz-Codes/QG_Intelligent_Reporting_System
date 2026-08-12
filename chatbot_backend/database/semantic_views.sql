-- ---------------------------------------------------------------------------
--  Semantic views: business definitions as CODE, not as prose.
--
--  Every wrong answer this project has produced came from the same place - a
--  business word ("shaft", "scrap", "out of stock", "type") described in
--  English in a prompt, and re-interpreted by the model on every single run.
--  Prose is ambiguous to the same model that misreads the schema:
--
--    * "match bar and shaft" was read as SQL AND, requiring both words, and
--      returned 0
--    * '\ybar\y' was written '\\ybar\\y', which looks for a literal backslash,
--      and returned 0
--    * ILIKE '%bar%' matched Barrel, Barbed Wire and Wheelbarrow
--    * "out of stock" was counted over stock ROWS (one per item per branch),
--      giving 1,407 where the answer is 871
--
--  A view cannot be misread. It is written once, verified once, and every
--  query selects FROM it. Change the definition here and every answer that
--  depends on it changes with it - there is no second copy in a prompt to
--  drift out of step.
--
--  Apply with:  psql -d supply_chain_db -f database/semantic_views.sql
--  Re-runnable: every view is CREATE OR REPLACE.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- v_branches - every spelling of a branch, mapped to one canonical code
--
-- SEVEN branches, codes confirmed by the business:
--     QBL2  Qadri Brothers Unit 2      (also written QB2, QBL-II)
--     QBL   Qadri Brothers
--     QCL   Qadcast
--     QE    Qadbros Engineering
--     QE2   Qadbros Engineering Unit 2 (also written QE-II)
--     QEN   Qadri Engineering
--     IOL   Izmir Office Lahore        (also "Corporate Office Izmir")
--
-- This view exists because the SAME branch is written differently in every
-- table, and no column anywhere records the mapping:
--     stock / issuance / store_requisition   full legal name
--     purchases_data                         short code (QB2, QE-II)
--     branches (the imports master)          short code (QBL-II); its own
--                                            `code` column is NULL on every row
--     logistics_packages / trucking          short code
--
-- The codes are a trap: QE is QadBROS, QEN is QadRI. Guessing
-- "Qadri Engineering -> QE" returns a DIFFERENT COMPANY's numbers, with no
-- error and a plausible figure.
--
-- TWO views, on purpose, because ONE was a trap.
--
-- The first attempt was a single view with one row per alias, carrying
-- branch_code alongside. Joining it on `alias` is correct; joining it on
-- `branch_code` - the obvious thing to write, and what the model wrote -
-- matched every alias row sharing that code and DOUBLED the answer:
-- QEN purchases came back 40,416 instead of 20,208, with no error.
--
-- Split so that NEITHER view has a repeating join key:
--     v_branches         one row per branch  (branch_code unique)  - 7 rows
--     v_branch_aliases   one row per spelling (alias unique)       - 20 rows
-- Any join to either one is now safe; fan-out is impossible.
--
--     -- a column holding codes OR legal names - always via the alias map:
--     JOIN v_branch_aliases a ON a.alias = purchases_data.branch
--     JOIN v_branch_aliases a ON a.alias = issuance.branch
--     GROUP BY a.branch_code
--
--     -- add the display name only when you need it:
--     JOIN v_branches b ON b.branch_code = a.branch_code
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_branch_aliases;
DROP VIEW IF EXISTS v_branches;

CREATE VIEW v_branches AS
SELECT * FROM (
    VALUES
        ('QBL2', 'Qadri Brothers Unit 2'),
        ('QBL',  'Qadri Brothers'),
        ('QCL',  'Qadcast'),
        ('QE',   'Qadbros Engineering'),
        ('QE2',  'Qadbros Engineering Unit 2'),
        ('QEN',  'Qadri Engineering'),
        ('IOL',  'Izmir Office Lahore'),
        -- Each appears once, in the imports master and in logistics. Not one of
        -- the seven; carried so a join never silently drops the row.
        ('QH',   'QH'),
        ('QFL',  'QFL')
) AS t(branch_code, branch_name);

CREATE VIEW v_branch_aliases AS
SELECT * FROM (
    VALUES
        -- alias exactly as stored in the data,     canonical code
        ('QE',                                       'QE'),
        ('Qadbros Engineering (Pvt) Ltd.',           'QE'),
        ('QEN',                                      'QEN'),
        ('Qadri Engineering (Pvt) Ltd.',             'QEN'),
        ('QCL',                                      'QCL'),
        ('Qadcast (Pvt) Ltd.',                       'QCL'),
        ('QBL2',                                     'QBL2'),
        ('QB2',                                      'QBL2'),
        ('QBL-II',                                   'QBL2'),
        ('Qadri Brothers (Pvt.) Ltd. (Unit-II)',     'QBL2'),
        ('QBL',                                      'QBL'),
        ('QBL-I',                                    'QBL'),
        ('Qadri Brothers (Pvt) Ltd.',                'QBL'),
        ('QE2',                                      'QE2'),
        ('QE-II',                                    'QE2'),
        ('Qadbros Engineering (Pvt) Ltd. (Unit-II)', 'QE2'),
        ('IOL',                                      'IOL'),
        ('Corporate Office Izmir',                   'IOL'),
        ('QH',                                       'QH'),
        ('QFL',                                      'QFL')
) AS t(alias, branch_code);


-- ---------------------------------------------------------------------------
-- v_import_shafts - shafts as they are IMPORTED
--
-- Exactly three types, per the business:
--     Forged Steel Round Bar
--     Forged Steel Hollow Drill Bar
--     Forged Alloy Steel Round Bar
--
-- These live on the import LINES (consignment_items), NOT in the item master -
-- searching `items` for them returns nothing, which is why this view reads
-- consignment_items directly. shaft_type normalises the three spellings
-- (the workbook writes "Drill Bars" plural on some rows) so a count by type
-- gives three groups rather than five.
--
-- ONLY for the imports context. A general question about shafts is NOT this
-- view - it is the items actually named shaft, derived in SQL:
--     WHERE items.name ~* '[[:<:]]shafts?[[:>:]]'
-- There is deliberately no v_shaft_items: outside imports "shaft" means what
-- the name says, and if the user disagrees with the set, ask them rather than
-- freezing a different guess into a view.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_import_shafts AS
SELECT ci.id,
       ci.consignment_id,
       ci.item_code,
       ci.item_name,
       CASE
           WHEN ci.item_name ~* 'alloy'  THEN 'Forged Alloy Steel Round Bar'
           WHEN ci.item_name ~* 'hollow' THEN 'Forged Steel Hollow Drill Bar'
           ELSE 'Forged Steel Round Bar'
       END                              AS shaft_type,
       ci.specification,
       ci.quantity,
       ci.unit_of_measurement            AS uom,
       ci.unit_price,
       c.current_status,
       c.origin,
       c.eta,
       c.etd,
       s.name                            AS supplier
FROM consignment_items AS ci
JOIN consignments AS c
  ON c.id = ci.consignment_id
 AND c.is_deleted = false
LEFT JOIN suppliers AS s
  ON s.id = c.supplier_id
WHERE ci.is_deleted = false
  AND ci.item_name ~* '[[:<:]]forged[[:>:]]'
  AND ci.item_name ~* '[[:<:]]bars?[[:>:]]';


-- ---------------------------------------------------------------------------
-- v_import_shaft_material - shaft material as CATALOGUED
--
-- The four forged-bar names in the item master, 88 codes:
--     Forged Round Bar                 28
--     Forged Round Bar Stepped         30
--     Forged Drill Bar Hollow          15
--     Forged Drill Bar Stepped Hollow  15
--
-- Matched by name explicitly, on purpose. The previous definition used
--     category ILIKE '%shaft%'  OR  (forged AND (bar OR shaft))
-- which also pulled in "Shaft (Forged)" and "Shaft Black Tank Plate" - a plate,
-- not shaft material - for 90. The category 'Shaft Material(Temp)' is not a
-- reliable filter on its own.
--
-- DISTINCT FROM v_import_shafts. This is what the CATALOGUE carries; that is
-- what the import DOCUMENTS actually list, and the two use different wording
-- ("Forged Round Bar" here, "Forged Steel Round Bar" there). Neither is wrong -
-- pick by whether the question is about the item master or about imports.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_import_shaft_material AS
SELECT i.id,
       i.item_code,
       i.name,
       i.default_specification,
       i.default_unit_of_measurement AS uom,
       i.category,
       i.is_active
FROM items AS i
WHERE lower(trim(i.name)) IN (
    'forged round bar',
    'forged round bar stepped',
    'forged drill bar hollow',
    'forged drill bar stepped hollow'
);


-- ---------------------------------------------------------------------------
-- v_item_stock_position - one row per ITEM, aggregated across every branch
--
-- `stock` holds one row per item PER BRANCH, so counting it directly counts
-- item-branch pairs. This collapses it to the item, which is what a business
-- question means by "how many items ...".
--
-- available_qty = stock_qty - hold_qty, i.e. what is actually usable. An item
-- whose stock is entirely reserved is unavailable in practice even though
-- stock_qty is positive.
-- ---------------------------------------------------------------------------
-- Dropped rather than replaced: CREATE OR REPLACE cannot add a column to
-- an existing view, and the dependent views are rebuilt below anyway.
DROP VIEW IF EXISTS v_item_demand_picture;
DROP VIEW IF EXISTS v_branch_depleted_items;
DROP VIEW IF EXISTS v_out_of_stock_by_branch;
DROP VIEW IF EXISTS v_out_of_stock_items;
DROP VIEW IF EXISTS v_item_stock_position;
CREATE VIEW v_item_stock_position AS
SELECT s.item_code,
       MAX(s.item_name)                            AS item_name,
       COUNT(*)                                    AS branches_held_at,
       SUM(COALESCE(s.stock_qty, 0))               AS stock_qty,
       SUM(COALESCE(s.hold_qty, 0))                AS hold_qty,
       SUM(COALESCE(s.available_qty, 0))           AS available_qty,

       -- THE VALUE OF THE INVENTORY: everything held, including stock that is
       -- reserved. Held stock is committed, not gone, so it is still inventory
       -- the company owns - this is the figure "what is our inventory worth"
       -- must use.
       --
       -- Exposed because it was MISSING, and its absence chose the wrong
       -- answer: available_amount was the only value column in this view, so
       -- "the value of inventory" was answered as 860,385,662.91 (available
       -- only) when the company holds 982,117,697.87. A 121.7m understatement
       -- that no rule could have prevented, because the right column was not
       -- reachable.
       SUM(COALESCE(s.stock_qty_amount, 0))        AS stock_amount,

       -- The narrower measure: value of the UNRESERVED portion only. Answers
       -- "what could we use or sell today", not "what do we own".
       SUM(COALESCE(s.available_amount, 0))        AS available_amount,
       (SUM(COALESCE(s.available_qty, 0)) <= 0)    AS is_out_of_stock,

       -- The RAREST class this item carries at any branch. A < B < C
       -- sorts correctly, so MIN is the rarest, matching the documented
       -- reading of "how many A items" (A at at least one branch).
       MIN(s.rank)                                 AS rank,
       -- Kept because 103 items disagree across branches, and an answer
       -- that says "A" for an item that is C at two of its three sites
       -- is hiding the thing worth knowing.
       STRING_AGG(DISTINCT s.rank, '/' ORDER BY s.rank) AS branch_ranks
FROM stock AS s
GROUP BY s.item_code;


-- ---------------------------------------------------------------------------
-- v_out_of_stock_items - THE DEFINITION OF "OUT OF STOCK". 871 items.
--
-- An item at zero in one branch while another branch still holds it is NOT out
-- of stock; it is out at that branch. Items with no stock row at all are not
-- here either - they are simply not stocked, which is a different question.
--
-- THIS IS THE ONLY DEFINITION. Every out-of-stock answer, at any grain, must
-- come from this view or one of the two below that are derived from it. Do not
-- write `available_qty <= 0` against `stock` to answer an out-of-stock
-- question: that is a DIFFERENT set (1,160 items - anything empty at any one
-- branch), and mixing the two is what made "how many items are out of stock?"
-- return 871 while "which branch has the most?" returned per-branch counts
-- that summed past 871. Two true numbers, one contradiction on screen.
-- ---------------------------------------------------------------------------
CREATE VIEW v_out_of_stock_items AS
SELECT p.item_code,
       p.item_name,
       p.rank,
       p.branch_ranks,
       p.branches_held_at,
       p.stock_qty,
       p.hold_qty,
       p.available_qty
FROM v_item_stock_position AS p
WHERE p.is_out_of_stock;


-- ---------------------------------------------------------------------------
-- v_out_of_stock_by_branch - the SAME 871 items, split by where they sit
--
-- For "which branch has the most out-of-stock items". Derived from the view
-- above rather than recomputed, so a branch figure can never disagree with the
-- company total: every row here belongs to an item that is out of stock by the
-- one definition.
--
-- A caveat to state when reporting these: an item stocked at three branches is
-- out of stock at all three, so it appears three times and the branch counts
-- sum to MORE than 871. That is the count of affected item-locations, not a
-- partition of the 871. Say "items affected at this branch", never imply the
-- branches divide the total between them.
-- ---------------------------------------------------------------------------
CREATE VIEW v_out_of_stock_by_branch AS
SELECT s.branch,
       o.item_code,
       o.item_name,
       o.rank,
       s.rank                              AS branch_rank,
       COALESCE(s.stock_qty, 0)            AS branch_stock_qty,
       COALESCE(s.hold_qty, 0)             AS branch_hold_qty,
       COALESCE(s.available_qty, 0)        AS branch_available_qty,
       o.branches_held_at
FROM v_out_of_stock_items AS o
JOIN stock AS s ON s.item_code = o.item_code;


-- ---------------------------------------------------------------------------
-- v_branch_depleted_items - "nothing left HERE", which is NOT out of stock
--
-- The genuinely different question the old ad-hoc SQL was answering: what has
-- run dry at this branch, whether or not another branch can cover it. Useful
-- to a storekeeper, and deliberately given its own name so it can never be
-- reported as "out of stock" - an item empty here with 500 at the next branch
-- is a TRANSFER, not a purchase.
--
-- Call these items DEPLETED AT THAT BRANCH. Reserve "out of stock" for
-- v_out_of_stock_items.
-- ---------------------------------------------------------------------------
CREATE VIEW v_branch_depleted_items AS
SELECT s.branch,
       s.item_code,
       s.item_name,
       s.rank                                     AS branch_rank,
       COALESCE(s.stock_qty, 0)                   AS branch_stock_qty,
       COALESCE(s.hold_qty, 0)                    AS branch_hold_qty,
       COALESCE(s.available_qty, 0)               AS branch_available_qty,
       p.available_qty                            AS company_available_qty,
       -- The distinction in one column: TRUE means nowhere else has it either,
       -- so this row is also in v_out_of_stock_items.
       p.is_out_of_stock                          AS out_of_stock_company_wide
FROM stock AS s
JOIN v_item_stock_position AS p ON p.item_code = s.item_code
WHERE COALESCE(s.available_qty, 0) <= 0;


-- ---------------------------------------------------------------------------
-- v_item_types - one row per distinct item NAME
--
-- A "type" is a distinct name, not a distinct item_code: each code is a
-- name + spec variant, so Round Bar alone is over a thousand codes but one
-- type. Counting codes overstates a type question more than twentyfold.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_item_types AS
SELECT lower(trim(i.name))        AS item_type,
       MIN(i.name)                AS display_name,
       COUNT(*)                   AS item_codes,
       MIN(i.category)            AS category
FROM items AS i
WHERE i.name IS NOT NULL AND trim(i.name) <> ''
GROUP BY lower(trim(i.name));


-- ---------------------------------------------------------------------------
-- v_item_consumption_monthly - the demand signal, per item per month
--
-- Only status 'Issue' counts as consumption. 'Hold' and 'HoldIssuence' are
-- reservations that have not been consumed, and including them overstates the
-- burn rate. There is no status called 'Issued'.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_item_consumption_monthly AS
SELECT iss.item_code,
       date_trunc('month', iss.from_date)::date AS period,
       SUM(COALESCE(iss.quantity, 0))           AS quantity,
       SUM(COALESCE(iss.total_price, 0))        AS value,
       COUNT(*)                                 AS issue_lines
FROM issuance AS iss
WHERE iss.from_date IS NOT NULL
  AND iss.status = 'Issue'
GROUP BY iss.item_code, date_trunc('month', iss.from_date);




-- ---------------------------------------------------------------------------
-- v_item_demand_picture - everything an "how are we doing on <item>" question
-- needs, in one row per item.
--
-- Exists because the four-lens answer for an item always wants the same six
-- figures, and assembling them from five tables per question produced a
-- different query (and a different number) every run:
--
--   DESCRIPTIVE   current stock, what we issued in the last 3 months,
--                 how many days that stock covers
--   DIAGNOSTIC    is there open demand, how big, and when is the next delivery
--   PRESCRIPTIVE  how much short we are once stock and incoming are counted
--
-- THE WINDOW IS DELIBERATE. `issued_qty_3m` covers the last 3 months from
-- CURRENT_DATE, as asked. But the burn RATE behind days_of_cover divides by the
-- days in that window that could actually contain data (issuance currently ends
-- ~1 month before today). Dividing by the full 90 days would understate the
-- burn and OVERSTATE days of cover - the one direction that gets somebody a
-- stockout. `data_through` is exposed so an answer can say how fresh this is.
--
-- suggested_buy_qty is DEMAND-DRIVEN, not a reorder policy: it is what open
-- requisitions ask for that stock and incoming shipments do not already cover.
-- No safety-stock target is invented here, because nobody has set one. To add
-- a cover target, multiply daily_burn by the days wanted and add it.
-- ---------------------------------------------------------------------------
-- Dropped rather than replaced: CREATE OR REPLACE cannot insert a column into
-- the middle of an existing view's column list, and this view gains columns as
-- the answer it feeds grows.
CREATE VIEW v_item_demand_picture AS
WITH win AS (
    SELECT (CURRENT_DATE - INTERVAL '3 months')::date          AS win_start,
           CURRENT_DATE                                        AS win_end,
           (SELECT MAX(from_date) FROM issuance)               AS data_through
),
recent AS (
    SELECT i.item_code,
           SUM(COALESCE(i.quantity, 0))            AS issued_qty_3m,
           COUNT(*)                                AS issue_lines_3m,
           MAX(i.from_date)                        AS last_issued_on
    FROM issuance i, win w
    WHERE i.status = 'Issue'
      AND i.from_date >= w.win_start
    GROUP BY i.item_code
),
-- A FULL YEAR drives the cover figure. Three months is too short a base: a
-- quiet quarter sent Resin Sand to 3,001.9 days (8.2 years) off 31 kg, where a
-- year of issuance puts it at 245. A year also spans seasonality, so a
-- seasonal item does not look critical or comfortable purely by when it is
-- asked about.
yearly AS (
    SELECT i.item_code,
           SUM(COALESCE(i.quantity, 0))            AS issued_qty_12m,
           COUNT(*)                                AS issue_lines_12m
    FROM issuance i
    WHERE i.status = 'Issue'
      AND i.from_date >= (CURRENT_DATE - INTERVAL '12 months')
    GROUP BY i.item_code
),
demand AS (
    SELECT sr.item_code,
           SUM(COALESCE(sr.pending_quantity, 0))   AS open_demand_qty,
           COUNT(*)                                AS open_requisitions,
           MIN(sr.required_date)                   AS earliest_required_date,

           -- How much of the open demand has ALREADY been bought. Without this
           -- an answer says "buy 18,660 kg" while a purchase is half done.
           SUM(COALESCE(sr.pur_quantity, 0))       AS demand_purchased_qty,

           -- WHERE each requisition has got to, worst-first is not knowable
           -- here so they are listed alphabetically with their counts. This is
           -- a SUMMARY column on an already per-item row, not a rollup of
           -- records that should have stayed separate.
           STRING_AGG(
               DISTINCT sr.status || ' x' || sr.n::text, ', '
           )                                       AS demand_statuses,
           bool_or(sr.overdue)                     AS demand_overdue
    FROM (
        SELECT sr2.item_code,
               sr2.pending_quantity,
               sr2.pur_quantity,
               sr2.required_date,
               COALESCE(sr2.status, 'Unknown')     AS status,
               COUNT(*) OVER (
                   PARTITION BY sr2.item_code, COALESCE(sr2.status, 'Unknown')
               )                                   AS n,
               CASE
                   WHEN sr2.required_date IS NOT NULL
                    AND sr2.required_date < CURRENT_DATE THEN true
                   ELSE false
               END                                 AS overdue
        FROM store_requisition sr2
        WHERE COALESCE(sr2.pending_quantity, 0) > 0
    ) sr
    GROUP BY sr.item_code
),
incoming AS (
    SELECT ci.item_code,
           SUM(COALESCE(ci.quantity, 0))           AS incoming_qty,
           COUNT(DISTINCT c.id)                    AS incoming_consignments,
           MIN(c.eta)                              AS earliest_eta,
           STRING_AGG(
               DISTINCT c.current_status, ', ' ORDER BY c.current_status
           )                                       AS incoming_statuses
    FROM consignment_items ci
    JOIN consignments c
      ON c.id = ci.consignment_id
     AND c.is_deleted = false
     AND c.current_status NOT IN ('Arrived at Works', 'Order Cancelled')
    WHERE ci.is_deleted = false
      AND ci.item_code IS NOT NULL
    GROUP BY ci.item_code
)
SELECT p.item_code,
       p.item_name,
       p.rank,
       p.branch_ranks,
       p.available_qty,
       p.stock_qty,
       p.hold_qty,

       COALESCE(r.issued_qty_3m, 0)                AS issued_qty_3m,
       COALESCE(r.issue_lines_3m, 0)               AS issue_lines_3m,
       r.last_issued_on,
       w.win_start                                 AS issued_since,
       w.data_through,

       COALESCE(y.issued_qty_12m, 0)               AS issued_qty_12m,
       COALESCE(y.issue_lines_12m, 0)              AS issue_lines_12m,

       -- The business's formula: a year's issuance spread over 365 days.
       ROUND(COALESCE(y.issued_qty_12m, 0) / 365.0, 4) AS daily_burn,

       -- NULL, not infinity, when nothing has been issued: "we cannot tell"
       -- is the honest answer, and a made-up large number reads as comfort.
       -- STOCK DAYS = stock in hand / (yearly issuance / 365).
       -- NULL, never infinity, when nothing moved in a year: "we cannot tell"
       -- is the honest answer, and a huge number reads as comfort.
       CASE
           WHEN COALESCE(y.issued_qty_12m, 0) <= 0 THEN NULL
           ELSE ROUND(p.available_qty / (y.issued_qty_12m / 365.0), 1)
       END                                         AS days_of_cover,

       COALESCE(d.open_demand_qty, 0)              AS open_demand_qty,
       COALESCE(d.open_requisitions, 0)            AS open_requisitions,
       d.earliest_required_date,
       d.demand_statuses,
       COALESCE(d.demand_purchased_qty, 0)         AS demand_purchased_qty,
       COALESCE(d.demand_overdue, false)           AS demand_overdue,

       COALESCE(i.incoming_qty, 0)                 AS incoming_qty,
       COALESCE(i.incoming_consignments, 0)        AS incoming_consignments,
       i.earliest_eta,
       i.incoming_statuses,

       GREATEST(
           0,
           COALESCE(d.open_demand_qty, 0)
           - p.available_qty
           - COALESCE(i.incoming_qty, 0)
       )                                           AS suggested_buy_qty
FROM v_item_stock_position p
CROSS JOIN win w
LEFT JOIN recent   r ON r.item_code = p.item_code
LEFT JOIN yearly   y ON y.item_code = p.item_code
LEFT JOIN demand   d ON d.item_code = p.item_code
LEFT JOIN incoming i ON i.item_code = p.item_code;
