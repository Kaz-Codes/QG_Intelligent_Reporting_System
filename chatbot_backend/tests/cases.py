"""
The regression cases.

Each case pairs a QUESTION with a TRUTH QUERY. The truth query is plain SQL run
straight against the database, so the expected answer is recomputed on every run
and never goes stale when the data is reloaded - the alternative, hard-coded
numbers, would have to be re-verified by hand after every load and would quietly
start lying the first time somebody forgot.

check types
-----------
scalar     the assistant's result must be a single value equal to the truth
rowcount   the number of rows returned must equal the truth
nonzero    the result must be a single value greater than zero - for questions
           where the exact figure moves with the data but "nothing" is a bug
refuses    the assistant must decline: the data genuinely is not in the schema
clarifies  the assistant must ask rather than guess

Every case here exists because something got it wrong, or because it is close
enough to something that did. The `why` field records which.
"""

CASES = [
    # ---------------------------------------------------------------- shafts
    {
        "id": "shaft-types-count",
        "question": "how many types of shafts do we have",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(DISTINCT lower(trim(name))) FROM items WHERE name ~* '[[:<:]]shafts?[[:>:]]'
        """,
        "why": ("answered 0, then 145, then 55, then 6 (the forged import "
                "material). A shaft is an item NAMED shaft - 15 names."),
    },
    {
        "id": "shaft-item-codes",
        "question": "how many item codes have shaft in the item name, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM items WHERE name ~* '[[:<:]]shafts?[[:>:]]'",
        "why": "types vs codes were conflated - a type is a name, not a code",
    },
    {
        "id": "import-shaft-material",
        "question": "how many item codes are classified as forged shaft material in the item master, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM v_import_shaft_material",  # 88, was 90
        "why": ("forged bar stock is only called 'shaft' in the imports context; "
                "it must not answer a general shaft question"),
    },
    {
        "id": "shafts-on-water",
        "question": "how many shaft shipments are currently in transit",
        "check": "scalar",
        "truth_sql": """
            -- A SHIPMENT IS A CONSIGNMENT, NOT A LINE, on all three sides.
            -- The previous version counted logistics LINES against trucking
            -- CONSIGNMENTS and left imports out entirely, so it asserted 13
            -- and marked the correct answer (18) wrong.
            SELECT COUNT(*) FROM (
                SELECT DISTINCT 'imports' AS side, v.consignment_id AS id
                FROM v_import_shafts v
                WHERE v.current_status = 'In Transit'
                UNION ALL
                SELECT DISTINCT 'exports', lc.id
                FROM logistics_consignments lc
                JOIN logistics_items li ON li.consignment_id = lc.id
                 AND li.is_deleted = false
                WHERE lc.is_deleted = false
                  AND li.item_detail ~* '[[:<:]]shafts?[[:>:]]'
                  AND lc.current_status IN ('Transportation', 'On Water')
                UNION ALL
                SELECT DISTINCT 'road', tc.id
                FROM trucking_consignments tc
                WHERE tc.is_deleted = false
                  AND tc.item_details ~* '[[:<:]]shafts?[[:>:]]'
                  AND EXISTS (SELECT 1 FROM trucking_vehicles tv
                              WHERE tv.consignment_id = tc.id
                                AND tv.is_deleted = false
                                AND tv.tracking_status <> 'Delivered')
            ) t
        """,
        "why": "said 'no shafts on water' while two were sailing to customers",
    },
    {
        "id": "shaft-stock-is-empty",
        # Worded as a single total on purpose. "How much shaft material do we
        # have in stock" was answered with a 90-row listing of the shaft items -
        # a fair reading of the question, but not a scalar, so the case failed
        # on its phrasing rather than on the answer.
        "question": "what is the total available stock quantity of forged shaft material we import, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT COALESCE(SUM(p.available_qty), 0)
            FROM v_item_stock_position p
            JOIN v_import_shaft_material s ON s.item_code = p.item_code
        """,
        "why": "shaft MATERIAL genuinely has no stock; must not be widened to find rows",
    },

    # ----------------------------------------------------------------- scrap
    {
        "id": "scrap-exists",
        "question": "how many scrap items do we have",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM items WHERE name ~* '[[:<:]]scraps?[[:>:]]'",
        "why": "answered 'scrap is not recorded' for 93 codes / 10,311 issuances",
    },
    {
        "id": "scrap-consumption",
        "question": "how much scrap have we consumed in total",
        "check": "nonzero",
        "truth_sql": """
            SELECT SUM(c.quantity) FROM v_item_consumption_monthly c
            JOIN items s ON s.item_code = c.item_code AND s.name ~* '[[:<:]]scraps?[[:>:]]'
        """,
        "why": "same refusal risk on the movement side",
    },

    # ----------------------------------------------------------------- stock
    {
        "id": "out-of-stock-items",
        "question": "how many items are out of stock",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM v_out_of_stock_items",
        "why": "answered 1,407 (stock ROWS, one per item per branch) not 871 items",
    },
    {
        "id": "stocked-items",
        # "do we hold stock of" is ambiguous between "have any left" (3,891) and
        # "carry as a stocked line" (4,762) - the assistant answered the second
        # and was not wrong. Worded explicitly, and the other reading is pinned
        # as its own case below so both stay honest.
        "question": "how many different items currently have stock available",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM v_item_stock_position WHERE available_qty > 0
        """,
        "why": "same per-branch double-counting trap",
    },
    {
        "id": "items-with-stock-records",
        "question": "how many different items have a stock record, including those at zero",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM v_item_stock_position",
        "why": "the wider reading; 3,891 available + 871 out of stock = 4,762",
    },

    # ---------------------------------------------------------------- issues
    {
        "id": "issuance-lines",
        "question": "how many issuance lines are recorded in total",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM issuance",
        "why": "a unique constraint on issuance_code once dropped 61% of these",
    },
    {
        "id": "issuance-documents",
        "question": "how many separate issuance documents are there",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(DISTINCT issuance_code) FROM issuance",
        "why": "lines vs documents - issuance_code repeats by design",
    },
    {
        "id": "top-consumed-item",
        # Asks for the FIGURE, not the item. "Which item has the highest
        # consumption" correctly returns a row (name + quantity), which is not a
        # single value - the case was checking the wrong shape.
        "question": "what is the total consumed quantity of the single most consumed item, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT SUM(quantity) FROM v_item_consumption_monthly
            GROUP BY item_code ORDER BY 1 DESC LIMIT 1
        """,
        "why": "consumption must exclude Hold / HoldIssuence",
    },

    # --------------------------------------------------------------- imports
    {
        "id": "imports-in-transit",
        "question": "how many import consignments are in transit",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM consignments
            WHERE is_deleted = false AND current_status ILIKE '%in transit%'
        """,
        "why": "core status question; soft-delete filter must be applied",
    },
    {
        "id": "import-consignments-total",
        "question": "how many import consignments are there in total",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM consignments WHERE is_deleted = false",
        "why": "record_state is draft on all loaded rows and must NOT be filtered",
    },
    {
        "id": "import-item-lines",
        "question": "how many item lines are on our import consignments",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM consignment_items WHERE is_deleted = false",
        "why": "INNER JOIN to items drops the 3 lines with a NULL item_id",
    },

    # --------------------------------------------------------------- exports
    {
        "id": "exports-sailing",
        "question": "how many export orders are currently sailing",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM logistics_consignments
            WHERE is_deleted = false AND current_status = 'On Water'
        """,
        "why": ("the user's word is 'sailing'; the stored value is 'On Water'. "
                "There is no 'Sailing' row in this column - an earlier version "
                "of this case asserted 0 because it trusted the ERP enum names "
                "over the loaded data, and marked the correct answer wrong."),
    },
    {
        "id": "export-orders-total",
        "question": "how many logistics orders do we have in total",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM logistics_consignments WHERE is_deleted = false",
        "why": "includes the 707 local orders with no export number",
    },
    {
        "id": "export-local-split",
        "question": "how many local logistics orders are there",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM logistics_consignments
            WHERE is_deleted = false AND order_type = 'Local'
        """,
        "why": "order_type Export vs Local vs untyped",
    },
    {
        "id": "containers",
        "question": "how many containers have been booked in total",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM logistics_containers WHERE is_deleted = false",
        "why": "expanded from per-type counts, not one row per booking",
    },

    # -------------------------------------------------------------- trucking
    {
        "id": "trucking-outbound",
        "question": "how many trucking jobs were outbound, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM trucking_consignments
            WHERE is_deleted = false AND movement_type = 'Outbound'
        """,
        "why": "movement_type is NULL on 191 jobs and must not be counted as outbound",
    },
    {
        "id": "trucking-vehicles",
        "question": "how many vehicles have been used across all trucking jobs",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM trucking_vehicles WHERE is_deleted = false",
        "why": "39 rows were silently dropped by an over-strict spacer filter",
    },
    {
        "id": "trucking-delivered",
        "question": "how many trucking vehicles have been delivered",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM trucking_vehicles
            WHERE is_deleted = false AND tracking_status = 'Delivered'
        """,
        "why": "status lives on the vehicle, not the job",
    },

    # ------------------------------------------------------------ purchasing
    {
        "id": "purchase-lines",
        "question": "how many purchase lines are recorded",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM purchases_data",
        "why": "the loader once read only the first workbook of two",
    },
    {
        "id": "suppliers-with-purchases",
        "question": "how many different suppliers have we purchased from, all dates",
        "check": "scalar",
        # Local purchases AND import suppliers. The truth query used to count
        # purchases_data alone (976) and marked the assistant wrong for
        # answering 1,011 - but imports are purchases too, and the 35 extra are
        # import suppliers never used for a local purchase. The assistant was
        # right and the case was wrong.
        "truth_sql": """
            SELECT COUNT(*) FROM (
                SELECT lower(trim(supplier)) AS s
                FROM purchases_data WHERE supplier IS NOT NULL
                UNION
                SELECT lower(trim(su.name))
                FROM consignments c
                JOIN suppliers su ON su.id = c.supplier_id
                WHERE c.is_deleted = false AND su.name IS NOT NULL
            ) t
        """,
        "why": "supplier was landing in item_name from a column-order bug",
    },
    {
        "id": "suppliers-local-only",
        "question": "how many different suppliers appear on our local purchase records, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(DISTINCT lower(trim(supplier)))
            FROM purchases_data WHERE supplier IS NOT NULL
        """,
        "why": "the narrower reading, pinned separately so both stay honest",
    },
    {
        "id": "pending-requisitions",
        "question": "how many requisitions are still pending",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM store_requisition WHERE pending_quantity > 0
        """,
        "why": "there is no status value 'Pending'; must filter the quantity",
    },

    # ----------------------------------------------------------------- items
    {
        "id": "item-types-total",
        "question": "how many distinct item types are in the catalogue",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM v_item_types",
        "why": "a type is a distinct NAME, not an item_code",
    },
    {
        "id": "items-total",
        "question": "how many items are in the item master",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM items",
        "why": "baseline; catches a broken items load",
    },

    # ------------------------------------------------------- must NOT answer
    {
        "id": "export-paperwork-absent",
        "question": "which export documents are still pending",
        "check": "refuses",
        "truth_sql": None,
        "why": "no table holds a document status; must decline, not substitute status",
    },
    {
        "id": "nonsense-item",
        "question": "how much unobtainium do we have in stock",
        "check": "refuses",
        "truth_sql": None,
        "why": "must not invent a match for something that does not exist",
    },

    # ------------------------------------------------ branch naming traps
    {
        "id": "branch-purchases-by-legal-name",
        # purchases_data.branch holds CODES. Asking by legal name must resolve
        # through v_branch_aliases, not filter the name directly (which returns 0).
        "question": "how many purchase lines are there for Qadri Engineering, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM purchases_data p
            JOIN v_branch_aliases b ON b.alias = p.branch
            WHERE b.branch_code = 'QEN'
        """,
        "why": "QE is QadBROS; reading 'Qadri Engineering' as QE gives another company",
    },
    {
        "id": "branch-issuance-by-code",
        # The mirror image: issuance.branch holds LEGAL NAMES, so a code has to
        # be resolved the other way.
        "question": "how many issuance lines are there for branch QCL, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM issuance i
            JOIN v_branch_aliases b ON b.alias = i.branch
            WHERE b.branch_code = 'QCL'
        """,
        "why": "issuance stores the legal name; a bare code filter matches nothing",
    },
    {
        "id": "branch-qe-is-qadbros",
        # "Qadbros Engineering" is genuinely ambiguous between QE alone and QE
        # plus its Unit-II (QE-II, 567 lines) - the assistant answered 26,547
        # including Unit-II, which is defensible. Asking by CODE removes the
        # ambiguity while still testing the thing that matters: that QE resolves
        # to Qadbros and not to Qadri.
        "question": "how many purchase lines are there for branch code QE, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM purchases_data WHERE branch = 'QE'",
        "why": "the two Engineering companies must not be swapped",
    },
    {
        "id": "branch-qadbros-not-qadri",
        # The real trap, stated as a difference: whatever scope is chosen for
        # Qadbros, it must not return Qadri Engineering's 20,208.
        "question": "how many purchase lines are there for Qadbros Engineering, all dates",
        "check": "not_equal",
        "truth_sql": """
            SELECT COUNT(*) FROM purchases_data p
            JOIN v_branch_aliases b ON b.alias = p.branch
            WHERE b.branch_code = 'QEN'
        """,
        "why": "must never return the OTHER Engineering company's figure",
    },

    # ------------------------------------------------ unclassified rows
    {
        "id": "trucking-total-vs-classified",
        # 158 Outbound + 50 Inbound = 208, but there are 399 jobs. The total
        # must not silently become the classified subset.
        "question": "how many trucking jobs are there in total, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM trucking_consignments WHERE is_deleted = false",
        "why": "movement_type is NULL on 191 of 399; total != inbound + outbound",
    },

    # ------------------------------------------------ spelling variants
    {
        "id": "mode-of-shipment-sea",
        # 'Sea' and 'By Sea' are the same thing typed twice.
        "question": "how many import consignments came by sea, all dates",
        "check": "scalar",
        "truth_sql": """
            SELECT COUNT(*) FROM consignments
            WHERE is_deleted = false AND mode_of_shipment ILIKE '%sea%'
        """,
        "why": "'Sea'(52) and 'By Sea'(18) - an equality filter loses 18",
    },

    # -------------------------------------------------- imported shafts
    {
        "id": "import-shaft-types",
        # The business rule: imports carry exactly three shaft types. They exist
        # only on the import LINES - searching the item master finds none of
        # them, because the catalogue spells its equivalents without "Steel".
        "question": "how many types of shafts do we import, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(DISTINCT shaft_type) FROM v_import_shafts",
        "why": "imported shafts are 3 types on consignment_items, not the item master",
    },
    {
        "id": "import-shaft-lines",
        "question": "what is the total number of import lines for shafts, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM v_import_shafts",
        "why": "82 lines across 19 consignments; must not answer from the catalogue",
    },

    # ------------------------------------------- relative date windows
    {
        "id": "last-12-months-is-12",
        # Asked on the 4th of a month, a window anchored on the CURRENT month
        # start returned 11 months: the current month was empty and a real
        # month was pushed out of the other end to make room for it.
        "question": "show total monthly issuance for the last 12 months",
        "check": "rowcount",
        "truth_sql": """
            SELECT COUNT(*) FROM (
                SELECT DISTINCT period FROM v_item_consumption_monthly
                WHERE period >= date_trunc('month', CURRENT_DATE) - INTERVAL '12 months'
                  AND period <  date_trunc('month', CURRENT_DATE)
            ) t
        """,
        "why": "a relative window must end at the last COMPLETE period, not today's",
    },

    # ----------------------------------------- counting vs summing NULLs
    {
        "id": "shafts-in-transit-is-a-count",
        # Answered "14 shafts currently in transit" when there are 12 movements.
        # The query used SUM(quantity) on a column that is NULL on 10 of the 12
        # rows; 14 was the total of the other two, presented as a count.
        "question": "how many shaft shipments are currently in transit, all dates",
        "check": "scalar",
        "truth_sql": """
            -- A SHIPMENT IS A CONSIGNMENT, NOT A LINE, on all three sides.
            -- The previous version counted logistics LINES against trucking
            -- CONSIGNMENTS and left imports out entirely, so it asserted 13
            -- and marked the correct answer (18) wrong.
            SELECT COUNT(*) FROM (
                SELECT DISTINCT 'imports' AS side, v.consignment_id AS id
                FROM v_import_shafts v
                WHERE v.current_status = 'In Transit'
                UNION ALL
                SELECT DISTINCT 'exports', lc.id
                FROM logistics_consignments lc
                JOIN logistics_items li ON li.consignment_id = lc.id
                 AND li.is_deleted = false
                WHERE lc.is_deleted = false
                  AND li.item_detail ~* '[[:<:]]shafts?[[:>:]]'
                  AND lc.current_status IN ('Transportation', 'On Water')
                UNION ALL
                SELECT DISTINCT 'road', tc.id
                FROM trucking_consignments tc
                WHERE tc.is_deleted = false
                  AND tc.item_details ~* '[[:<:]]shafts?[[:>:]]'
                  AND EXISTS (SELECT 1 FROM trucking_vehicles tv
                              WHERE tv.consignment_id = tc.id
                                AND tv.is_deleted = false
                                AND tv.tracking_status <> 'Delivered')
            ) t
        """,
        "why": "SUM over a mostly-NULL column must never be reported as a count",
    },
    {
        "id": "shafts-in-transit-not-the-sum",
        "question": "how many shafts are in transit right now, all dates",
        "check": "not_equal",
        "truth_sql": """
            SELECT COALESCE(SUM(li.quantity), 0)
            FROM logistics_items li
            JOIN logistics_consignments lc ON lc.id = li.consignment_id
             AND lc.is_deleted = false
            WHERE li.is_deleted = false
              AND li.item_detail ~* '[[:<:]]shafts?[[:>:]]'
              AND lc.current_status IN ('Transportation', 'On Water')
        """,
        "why": "must not return 14, the partial quantity sum, for a count question",
    },

    # ------------------------------------------------ plural vs singular
    {
        "id": "shipment-status-shows-the-lines",
        # "status of resin shipments" was answered with EXISTS over
        # consignment_items and a SELECT from consignments only: 15 matching
        # lines rolled up into 13 headers, with no item column at all. One
        # consignment (ref 42700) hid three resin lines behind a single row.
        "question": "what is the status of resin shipments, all dates",
        "check": "rowcount",
        # 15 import lines + 0 export + 6 road. My first version of this truth
        # counted only the import arm (15) and marked the correct all-arms
        # answer wrong - the same mistake as the shafts-in-transit truth.
        "truth_sql": """
            SELECT (
                SELECT COUNT(*)
                FROM consignments c
                JOIN consignment_items ci ON ci.consignment_id = c.id
                 AND ci.is_deleted = false
                WHERE c.is_deleted = false
                  AND ci.item_name ~* '[[:<:]]resins?[[:>:]]'
            ) + (
                SELECT COUNT(*)
                FROM logistics_consignments lc
                JOIN logistics_items li ON li.consignment_id = lc.id
                 AND li.is_deleted = false
                WHERE lc.is_deleted = false
                  AND li.item_detail ~* '[[:<:]]resins?[[:>:]]'
            ) + (
                SELECT COUNT(*)
                FROM trucking_consignments tc
                WHERE tc.is_deleted = false
                  AND tc.item_details ~* '[[:<:]]resins?[[:>:]]'
            )
        """,
        "why": "filtering a child table with EXISTS hid the lines it matched",
    },
    {
        "id": "distinct-does-not-eat-a-line",
        # A consignment carries TWO separate "Curing Agent for Phenolic Resin"
        # lines. They agree on item_name, reference and status, so a
        # SELECT DISTINCT over just those columns merges them and the answer
        # comes back one short - silently. 15 import lines, not 14.
        "question": "list every import line whose item name mentions resin, all dates",
        "check": "rowcount",
        "truth_sql": """
            SELECT COUNT(*)
            FROM consignments c
            JOIN consignment_items ci ON ci.consignment_id = c.id
             AND ci.is_deleted = false
            WHERE c.is_deleted = false
              AND ci.item_name ~* '[[:<:]]resins?[[:>:]]'
        """,
        "why": "SELECT DISTINCT silently merged two real lines into one",
    },
    {
        "id": "plural-resins",
        # "resins" matched 0 real items - the master stores singular names, and
        # the two it DID return were accidents of punctuation-stripped matching
        # ("Epoxy Re[sin Set]" -> epoxyresinset contains "resins").
        "question": "how many item codes in the item master have resin in the item name, all dates",
        "check": "scalar",
        "truth_sql": "SELECT COUNT(*) FROM items WHERE name ILIKE '%resin%'",
        "why": "a plural query must find singular item names - 19 codes, not 2",
    },

    # ----------------------------------------------------------- must ASK
    {
        "id": "ambiguous-kerosene",
        "question": "show me stock of kerosene oil",
        "check": "clarifies",
        "truth_sql": None,
        "why": "two item codes share the name; one has 6,304 issuances, one has none",
    },
]
