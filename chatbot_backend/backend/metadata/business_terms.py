"""
Company terminology: what a business word means and where it lives in the
database.

This is the seed corpus for the vector store (see backend/tools/vector_tools.py)
and the fallback the context agent uses when the vector store is unavailable.

Add a new entry whenever someone asks a question the bot misreads because it
did not know a company-specific word.

Editing this file is enough to re-teach the bot: ensure_seeded() hashes it at
backend startup and re-embeds only when it has changed, so a restart is all
that is needed.
"""

BUSINESS_TERMS = [
    {
        "term": (
            "how are we doing on <item> / item position / days of cover / "
            "how long will stock last / should we buy more / item status"
        ),
        "meaning": (
            "The standing question about a single material: what have we got, "
            "how fast is it going, how long will it last, is anyone waiting for "
            "it, and is more on the way. One row per item answers all of it."
        ),
        "maps_to": (
            "v_item_demand_picture(item_code, item_name, available_qty, "
            "stock_qty, hold_qty, issued_qty_3m, issue_lines_3m, "
            "last_issued_on, issued_since, data_through, daily_burn, "
            "days_of_cover, open_demand_qty, open_requisitions, "
            "earliest_required_date, demand_statuses, demand_purchased_qty, "
            "demand_overdue, incoming_qty, incoming_consignments, "
            "earliest_eta, incoming_statuses, suggested_buy_qty).\n"
            "'THE STATUS OF <MATERIAL>' MEANS THIS VIEW. A settled ruling: it "
            "is the item's POSITION - stock, cover, demand, inbound - not a "
            "list of its shipments. Do not answer it by unioning imports, "
            "issuance and trucking rows.\n"
            "USE THIS VIEW for any question about how an item is doing, how "
            "long stock lasts, whether to reorder, or what is coming. Filter "
            "with:  WHERE item_name ~* '[[:<:]]<word>s?[[:>:]]'  or by "
            "item_code. Do NOT reassemble these figures from issuance, stock, "
            "store_requisition and consignments by hand - that produced a "
            "different number every run.\n"
            "SELECT THE WHOLE ROW for an item question. The answer needs all "
            "three lenses at once: stock + issued_qty_3m + days_of_cover "
            "(descriptive), open_demand_qty + earliest_eta (diagnostic), "
            "suggested_buy_qty (prescriptive)."
        ),
        "notes": (
            "issued_qty_3m is the last 3 months from TODAY. days_of_cover "
            "divides by the days in that window that could actually hold data, "
            "because issuance currently ends before today - dividing by the "
            "full 90 days would overstate cover, which is the direction that "
            "causes a stockout. `data_through` is the last issuance date; say "
            "it when the figures are not current.\n"
            "days_of_cover is NULL when the item has not moved in 3 months. "
            "That means 'no recent consumption to measure', NOT 'infinite "
            "cover' - say so plainly rather than implying the item is fine.\n"
            "suggested_buy_qty = open demand MINUS stock MINUS what is already "
            "on the way. It covers committed demand only; it is not a reorder "
            "policy and assumes no safety stock, because the business has not "
            "set one. If asked for a cover target, multiply daily_burn by the "
            "days wanted and add that.\n"
            "WHEN DEMAND IS PLACED, ITS STATE MATTERS AS MUCH AS ITS SIZE. "
            "`demand_statuses` says where each open requisition has got to, "
            "with counts - 'Sourced x2, Procuring x1'. `demand_purchased_qty` "
            "is how much of it has ALREADY been bought (open_demand_qty is the "
            "REMAINING pending quantity, so the two never double-count). "
            "`demand_overdue` is true when a required date has already passed. "
            "`incoming_statuses` says where the inbound consignments have got "
            "to ('In Transit', 'Ready Awaiting Sailing'). Telling someone to "
            "buy 18,660 kg without saying the requisition is already at "
            "'Procuring' invites a duplicate order."
        ),
    },
    {
        "term": "stock / inventory on hand",
        "meaning": (
            "Current quantity physically held, per item per branch. "
            "available_qty is stock_qty minus hold_qty (reserved stock)."
        ),
        "maps_to": (
            "WHICH VIEW DEPENDS ON THE QUESTION:\n"
            "* ASKING ABOUT A NAMED MATERIAL ('how much hardner do we have', "
            "'resin stock', 'are we short of lime stone', 'should we buy X') - "
            "use v_item_demand_picture. It carries available_qty AND the things "
            "the answer has to say next: issued_qty_3m, days_of_cover, "
            "open_demand_qty, earliest_eta, suggested_buy_qty. SELECT THE WHOLE "
            "ROW. Returning available_qty alone forces an answer that cannot "
            "say how long the stock lasts, whether anyone is waiting for it, or "
            "whether more is coming - which is most of what was actually being "
            "asked.\n"
            "* COUNTING OR RANKING ACROSS THE PORTFOLIO ('how many items are "
            "out of stock', 'top 10 by value') - use v_item_stock_position"
            "(item_code, item_name, branches_held_at, stock_qty, hold_qty, "
            "available_qty, available_amount, is_out_of_stock), one row per "
            "ITEM with branches summed.\n"
            "* A PER-BRANCH BREAKDOWN - only then go to the raw stock table."
        ),
        "notes": (
            "stock is a snapshot with no date column - it cannot be trended.\n"
            "THREE DIFFERENT COUNTS, so read the question carefully:\n"
            "  4,762  items with a stock RECORD (we carry the line)\n"
            "  3,891  items with available_qty > 0 (we actually have some)\n"
            "    871  items out of stock (record exists, nothing available)\n"
            "3,891 + 871 = 4,762. 'How many items do we stock' means the widest "
            "(4,762); 'how many do we have available / in stock right now' means "
            "3,891. State which one the answer used whenever the phrasing could "
            "go either way.\n"
            "A further 22,987 catalogue items have NO stock record at all - "
            "never stocked. They belong in none of the three counts unless the "
            "user asks about the catalogue as a whole."
        ),
    },
    {
        "term": "out of stock / stocked out / nothing available",
        "meaning": (
            "An ITEM with no usable quantity left anywhere - available_qty is "
            "zero or below across EVERY branch that holds it. An item sitting "
            "at zero in one branch while another branch still has it is NOT out "
            "of stock; it is out at that branch."
        ),
        "maps_to": (
            "SELECT FROM THE VIEW v_out_of_stock_items - 871 rows, already one "
            "per ITEM rather than per item-branch. For stock levels generally "
            "use v_item_stock_position, which carries available_qty summed "
            "across branches plus an is_out_of_stock flag."
        ),
        "notes": (
            "COUNT THE ITEM, NOT THE ROW. stock holds one row per item PER "
            "BRANCH, so COUNT(*) FROM stock WHERE available_qty <= 0 counts an "
            "item held in four branches four times - it returns 1,407 where the "
            "real answer is 871. Always aggregate to item_code first.\n"
            "Use available_qty (stock_qty minus hold_qty), not stock_qty: 1,133 "
            "items have physical stock that is entirely reserved, and they are "
            "unavailable in practice. Filtering stock_qty = 0 instead returns "
            "35 and badly understates it.\n"
            "'Out of stock at BRANCH X' is the different, per-branch question: "
            "filter available_qty <= 0 AND branch ILIKE '%X%' without the "
            "GROUP BY.\n"
            "Items with NO stock row at all (22,987 of them) are NOT out of "
            "stock - they are simply not stocked items. Never include them "
            "unless the user explicitly asks about uncatalogued or never-held "
            "items."
        ),
    },
    {
        "term": "consumption / issuance / burn rate",
        "meaning": (
            "Material issued out of the store to a department or job. "
            "This is the demand signal used for forecasting."
        ),
        "maps_to": (
            "SELECT FROM THE VIEW v_item_consumption_monthly(item_code, period, "
            "quantity, value, issue_lines) - already one row per item per "
            "month and already restricted to status 'Issue'. Use it for trends, "
            "burn rate and any forecast series. Go to the raw issuance table "
            "only when the question needs a column the view does not carry "
            "(department, job number, who issued it)."
        ),
        "notes": (
            "Group by item_code and month for a consumption trend. ~260k rows "
            "covering Dec 2022 onwards. issuance.status values are 'Issue' "
            "(the normal completed issue), 'Hold' and 'HoldIssuence' - there is "
            "NO status called 'Issued'. Held rows are not consumption; exclude "
            "them with status = 'Issue' when measuring burn rate."
        ),
    },
    {
        "term": "issuance code / issuance document",
        "meaning": (
            "issuance_code is the issuance DOCUMENT number. One document issues "
            "many different items - it is not one row per document."
        ),
        "maps_to": "issuance.issuance_code",
        "notes": (
            "NOT unique: thousands of documents cover more than one item code "
            "and the largest covers 222. COUNT(*) on issuance counts issue "
            "LINES; for the number of documents use "
            "COUNT(DISTINCT issuance_code). Never join on issuance_code "
            "expecting one row back."
        ),
    },
    {
        "term": "reorder level",
        "meaning": (
            "Stock level at which a replenishment should be raised, computed as "
            "average daily consumption x (lead_time_days + safety_days)."
        ),
        "maps_to": (
            "issuance.quantity for the consumption rate; lead time is OBSERVED "
            "from purchases_data (purchase - required_d)"
        ),
        "notes": (
            "Not stored anywhere - always calculated. There is no planning "
            "table in this schema: the old ab_items (lead_time_days, "
            "safety_days, ABC rank) no longer exists. Safety days have no "
            "source at all, so say so rather than assuming a number."
        ),
    },
    {
        "term": "procurement lead time",
        "meaning": (
            "How long a purchase actually takes: from the date it was needed to "
            "the date it landed."
        ),
        "maps_to": (
            "purchases_data.purchase - purchases_data.required_d, per item:\n"
            "  percentile_cont(0.5) WITHIN GROUP (ORDER BY (purchase - required_d))\n"
            "  GROUP BY item_code, with purchase and required_d both NOT NULL\n"
            "  and purchase >= required_d.\n"
            "See the schema's TWO PATTERNS TO WRITE YOURSELF block for the full "
            "query."
        ),
        "notes": (
            "Use the MEDIAN, never the average - one stalled order otherwise "
            "sets the planning figure for the whole item.\n"
            "Exclude purchase < required_d (arrived before it was needed): "
            "those are data-entry errors, not negative lead times, and they "
            "pull an average below zero.\n"
            "This is OBSERVED, not planned. There is no planning table in this "
            "schema - the old ab_items carrying lead_time_days and safety_days "
            "is gone, and safety days have no source at all, so say so rather "
            "than assuming a number."
        ),
    },
    {
        "term": "pending requisition / open requisition",
        "meaning": "Demand raised by a department that has not been fully supplied yet.",
        "maps_to": "store_requisition.pending_quantity > 0",
        "notes": (
            "Filter on pending_quantity > 0 ONLY. There is no status value "
            "called 'Pending' - adding status ILIKE '%pending%' returns zero rows."
        ),
    },
    {
        "term": "store requisition status values",
        "meaning": (
            "The workflow stage of a requisition. Actual values are: Issued, "
            "InStock, Partial Issued, GatePass, Sourced, Procuring, Preparing, "
            "PartialInStock, VCDelivered, Delivered, PartialGatePass, OutSourcing."
        ),
        "maps_to": "store_requisition.status",
        "notes": (
            "Still open: Preparing, Procuring, Sourced, OutSourcing. Fulfilled: "
            "Issued, Delivered, GatePass, VCDelivered. Never invent a status "
            "value not in this list."
        ),
    },
    {
        "term": "branch / site / unit / company",
        "meaning": (
            "One of the group's operating companies. SEVEN, confirmed by the "
            "business:\n"
            "  QBL2  Qadri Brothers Unit 2      (also written QB2, QBL-II)\n"
            "  QBL   Qadri Brothers\n"
            "  QCL   Qadcast\n"
            "  QE    Qadbros Engineering\n"
            "  QE2   Qadbros Engineering Unit 2 (also written QE-II)\n"
            "  QEN   Qadri Engineering\n"
            "  IOL   Izmir Office Lahore        (also 'Corporate Office Izmir')"
        ),
        "maps_to": (
            "THE SAME BRANCH IS SPELLED DIFFERENTLY IN DIFFERENT TABLES:\n"
            "  stock.branch, issuance.branch, store_requisition.branch\n"
            "      the FULL LEGAL NAME - 'Qadri Engineering (Pvt) Ltd.'\n"
            "  purchases_data.branch, branches.name (the imports master)\n"
            "      a SHORT CODE - 'QEN', 'QB2', 'QBL-II'\n"
            "TWO views resolve this. ALWAYS join the ALIAS one to a raw column:\n"
            "  v_branch_aliases(alias, branch_code)   one row per SPELLING, 20\n"
            "  v_branches(branch_code, branch_name)   one row per BRANCH, 9\n"
            "    JOIN v_branch_aliases a ON a.alias = issuance.branch\n"
            "    JOIN v_branch_aliases a ON a.alias = purchases_data.branch\n"
            "    JOIN v_branch_aliases a ON a.alias = br.name   -- imports, via "
            "consignments.branch_id -> branches br\n"
            "then GROUP BY a.branch_code to combine the spellings, and join "
            "v_branches ON b.branch_code = a.branch_code only when you need the "
            "display name.\n"
            "NEVER join a raw branch column to v_branches directly. The alias "
            "map is what knows that 'Qadri Engineering (Pvt) Ltd.' and 'QEN' "
            "are the same place; v_branches does not carry spellings at all, so "
            "that join silently drops every legal-name row.\n"
            "Every branch value in every table resolves - a row that does not "
            "join is a bug, not an unknown branch.\n"
            "Accept either form from the user by resolving to a code first:\n"
            "    a.branch_code ILIKE :x OR a.alias ILIKE '%' || :x || '%'\n"
            "    OR a.branch_code IN (SELECT branch_code FROM v_branches\n"
            "                         WHERE branch_name ILIKE '%' || :x || '%')\n"
            "There is no `legal_name` or `short_name` column anywhere."
        ),
        "notes": (
            "THESE NAMES ARE OUR OWN COMPANIES, NEVER SUPPLIERS OR CUSTOMERS. "
            "'Qadri Engineering', 'Qadbros Engineering', 'Qadcast', 'Qadri "
            "Brothers', 'Qadbros', 'QFL', and any QE / QEN / QCL / QB2 / QBL / "
            "QE-II code, always mean a BRANCH. A question phrased 'purchases "
            "for Qadri Engineering' or 'issuances at Qadcast' is about the "
            "branch column - never filter supplier or customer_name on one of "
            "these. Doing so returned 31 rows for a branch that has 20,208.\\n"
            "QE IS NOT QADRI. QE is Qad**bros** Engineering and QEN is "
            "Qad**ri** Engineering - reading 'Qadri Engineering' as QE returns "
            "a DIFFERENT COMPANY's numbers, with no error and a plausible "
            "figure. This is the single most dangerous ambiguity in the "
            "database.\n"
            "Never filter purchases_data.branch with a legal name (matches "
            "nothing, returns 0) and never filter issuance/stock/"
            "store_requisition with a code (same). Go through v_branches.\n"
            "The `branches` master table is NOT the mapping - its `name` column "
            "contains codes not names and its `code` column is NULL on every "
            "row. It is the imports FK target, so join it to reach a "
            "consignment's branch, then resolve THAT through the alias map:\n"
            "    consignments c -> branches br ON br.id = c.branch_id\n"
            "                   -> v_branch_aliases a ON a.alias = br.name\n"
            "'Corporate Office Izmir' (492 store_requisition rows) is IOL, and "
            "'Qadbros Engineering (Pvt) Ltd. (Unit-II)' (179) is QE2 - both are "
            "real branches and both resolve through v_branches. Do not drop "
            "them from an 'all branches' total."
        ),
    },
    {
        "term": "import consignment / import status",
        "meaning": (
            "One inbound import shipment. Its stage in the pipeline from order "
            "to arrival at works."
        ),
        "maps_to": "consignments.current_status",
        "notes": (
            "Actual values present: 'Arrived at Works', 'In Transit', 'Under "
            "Production', 'Ready Awaiting Sailing', 'Under Custom Clearance', "
            "'Costing in Process'. The full ordered list also includes 'TT/LC "
            "in Process', 'Arrived at Port', 'Under Examination', 'Under "
            "Assessment', 'Arrived at QFL', 'On Road'. Always add "
            "is_deleted = false.\n"
            "STATUS IS INDEPENDENT OF EVERYTHING ELSE ON THE CONSIGNMENT. Mode "
            "of shipment, origin, currency, supplier and payment instrument are "
            "separate facts - a question about any of them is NOT a question "
            "about status. 'Consignments that came by sea' means "
            "mode_of_shipment ILIKE '%sea%' and nothing more; adding "
            "current_status ILIKE '%arrived%' turned 70 into 42. Only filter "
            "current_status when the user actually asks about where things are.\n"
            "mode_of_shipment spellings: 'Sea'(52) and 'By Sea'(18) are the "
            "same; 'Air'(10) and 'By  Air'(1, two spaces) are the same. Match "
            "with ILIKE '%sea%' / ILIKE '%air%', never with equality."
        ),
    },
    {
        "term": "on water / in transit / sailing / dispatched",
        "meaning": (
            "Goods have left and are en route, not yet arrived. Inbound and "
            "outbound are tracked in DIFFERENT tables with different words - "
            "consider both unless the user restricts to one direction."
        ),
        "maps_to": (
            "THREE SIDES, THREE VOCABULARIES. No status string is shared "
            "between them, so one filter cannot serve all three:\n"
            "  INBOUND (imports)  consignments.current_status = 'In Transit'\n"
            "  OUTBOUND (exports) logistics_consignments.current_status IN\n"
            "                     ('Transportation', 'On Water')\n"
            "  ROAD (trucking)    a trucking_consignments row with ANY vehicle\n"
            "                     whose tracking_status <> 'Delivered'\n"
            "THERE IS NO 'Sailing' AND NO 'Gate Out' IN THE DATA. Those are the "
            "ERP's enum names; the loaders wrote the values above. Filtering on "
            "them matches zero rows and raises no error, so the answer comes "
            "back as a confident 0."
        ),
        "notes": (
            "IN TRANSIT MEANS STILL MOVING - RULED BY THE BUSINESS. For exports "
            "that is EXACTLY 'Transportation' and 'On Water'.\n"
            "'AT PORT' AND 'AT QFL' ARE ARRIVED, NOT IN TRANSIT. They have "
            "landed; the order is simply not closed yet. Do not count them as "
            "goods on the move, and do not describe them as 'still in transit' "
            "in the wording of an answer either.\n"
            "Not-yet-shipped ('Under Production', 'Under Packing') and closed "
            "('Delivered') are excluded as well. So of the seven export "
            "statuses only TWO are in transit.\n"
            "The user's word rarely matches the stored value. 'Sailing' means "
            "'On Water'; 'dispatched' or 'left the works' covers all four. "
            "Translate the word onto the values above rather than filtering on "
            "what the user typed.\n"
            "A question about goods in transit generally should UNION all three "
            "sides with a literal label column saying which side each row came "
            "from - answering from one side and presenting it as the whole "
            "picture is the standing trap here. IMPORTS COUNT TOO: an inbound "
            "consignment 'In Transit' is a shipment in transit just as much as "
            "an export on the water.\n"
            "A SHIPMENT IS A CONSIGNMENT, NOT A LINE. Count DISTINCT "
            "consignment ids on every side - v_import_shafts.consignment_id, "
            "logistics_consignments.id, trucking_consignments.id - never the "
            "item lines. One consignment carrying eight shaft lines is ONE "
            "shipment. Counting lines on one side and consignments on another "
            "is how the same question returned 19, 5, 18 and 13 on four "
            "consecutive runs; the arms were right every time, only the unit "
            "moved. Fix the unit and the number stops moving."
        ),
    },
    {
        "term": "where item names live (master vs free text)",
        "meaning": (
            "An item is identified either by item_code against the master, or "
            "by free-text description. Always consider both when searching for "
            "an item or commodity."
        ),
        "maps_to": (
            "BY item_code: stock, issuance, store_requisition, purchases_data, "
            "consignment_items (which also has item_id -> items.id). "
            "FREE TEXT ONLY (no item_code column): logistics_items.item_detail, "
            "trucking_consignments.item_details, consignment_items.description."
        ),
        "notes": (
            "The old import_details.file_no commodity category ('Shafts', "
            "'Foundry Material', ...) NO LONGER EXISTS - imports are now "
            "itemised in consignment_items. For a whole-business item search, "
            "UNION the item-master search with the free-text searches, because "
            "some export/road part names exist only as free text and were never "
            "catalogued in items."
        ),
    },
    {
        "term": "type / kind / variety of an item (how many types of X)",
        "meaning": (
            "A TYPE is a distinct item NAME, not a distinct item_code. One name "
            "carries many codes because each code is a name + spec variant: "
            "'Round Bar' alone is over a thousand codes but it is ONE type. "
            "Asking 'how many types of shafts' means how many differently-named "
            "shaft items exist, not how many catalogue entries."
        ),
        "maps_to": (
            "SELECT count(*) FROM v_item_types - one row per distinct item "
            "name already. Filter it by joining to whichever item view the "
            "question is about (e.g. v_import_shafts) on item_code, or "
            "by its own item_type / category columns."
        ),
        "notes": (
            "SCOPE IS FIXED: count types from the items master ONLY. Do not "
            "UNION in the free-text item columns "
            "(consignment_items.item_name/description, "
            "logistics_items.item_detail, trucking_consignments.item_details) "
            "unless the user EXPLICITLY asks to include shipped or exported "
            "items - wording like 'in the data', 'we have' or 'in total' is NOT "
            "such a request and must still mean the item master.\n"
            "This rule exists because the scope was previously left to "
            "judgement, and the same conversation answered '145 types' to the "
            "count and then listed 55 names, because the count unioned four "
            "sources and the listing did not. One fixed scope is worth more "
            "than a marginally more complete number.\n"
            "Use COUNT(DISTINCT lower(trim(name))) - lowercased and trimmed, "
            "because the master holds the same name typed several ways. NEVER "
            "answer a 'how many types' question with COUNT(DISTINCT item_code) "
            "or COUNT(*): those count variants and overstate the answer by more "
            "than twentyfold.\n"
            "A follow-up that LISTS what was just counted ('write their names', "
            "'show them') must use exactly the same FROM and WHERE as the count "
            "it follows, so the list length always equals the number just given."
        ),
    },
    {
        "term": "naming an item by a word in its name (shaft, scrap, resin, bar)",
        "meaning": (
            "Most material questions name a KIND of item - shafts, scrap, "
            "resin, electrodes, sand. There is no table or flag for these: they "
            "are simply items whose NAME contains that word. Derive it in SQL "
            "and do not look for a dedicated table."
        ),
        "maps_to": (
            "items.name ~* '[[:<:]]<word>s?[[:>:]]', joined to stock, issuance, "
            "purchases_data or store_requisition on item_code.\n"
            "Use the WHOLE-WORD bracket form, never ILIKE '%word%': "
            "'%bar%' also matches Barrel, Barbed Wire and Wheelbarrow, which is "
            "how a shaft count once came back as 74 instead of 15. The 's?' "
            "covers singular and plural, because the master stores singular "
            "names while users type plurals."
        ),
        "notes": (
            "State in the answer WHICH rule was used - 'items whose name "
            "contains shaft' - so the user can correct it. If they say the set "
            "is wrong, ASK what should be included rather than guessing a "
            "wider or narrower pattern.\n"
            "The word may also appear in free text that was never catalogued: "
            "logistics_items.item_detail and trucking_consignments.item_details "
            "carry shipment descriptions like 'Shaft & Cone of Boiler ID Fan'. "
            "The item master cannot see those. Search them too when the "
            "question is about what has SHIPPED or MOVED rather than what is "
            "stocked, and say which side each row came from.\n"
            "Never answer that a material is not recorded because there is no "
            "table for it. Scrap has 93 item codes and over 10,000 issuance "
            "lines; replying 'scrap is not tracked' was flatly wrong."
        ),
    },
    {
        "term": (
            "forged shaft material in the item master / shaft material in the "
            "catalogue / forged bar stock"
        ),
        "meaning": (
            "The shaft material the CATALOGUE carries, as opposed to what the "
            "import documents list. FOUR names, 88 item codes, confirmed by the "
            "business:\n"
            "  Forged Round Bar                 28 codes\n"
            "  Forged Round Bar Stepped         30 codes\n"
            "  Forged Drill Bar Hollow          15 codes\n"
            "  Forged Drill Bar Stepped Hollow  15 codes"
        ),
        "maps_to": (
            "v_import_shaft_material(id, item_code, name, "
            "default_specification, uom, category, is_active) - the four names "
            "already matched exactly. SELECT count(*) FROM "
            "v_import_shaft_material is the answer to 'how many item codes are "
            "forged shaft material'.\n"
            "DO NOT write your own pattern for this. "
            "`name ~* 'forged' AND name ~* 'shaft'` looks right and returns "
            "1 - it finds only 'Shaft (Forged)', because the four real names "
            "say 'Bar', not 'Shaft'. The category 'Shaft Material(Temp)' is "
            "not a reliable filter on its own either."
        ),
        "notes": (
            "EXCLUDED ON PURPOSE, though their names look like matches: "
            "'Shaft (Forged)' (1 code) and 'Shaft Black Tank Plate' (1 code, a "
            "plate, not shaft material). An earlier definition let both in and "
            "answered 90.\n"
            "THIS TERM IS NOT THE ANSWER TO A PLAIN 'SHAFT' QUESTION. "
            "'How many item codes have shaft in the name', 'list our shafts', "
            "'shafts in stock' are NOT about this view - they mean "
            "items.name ~* '[[:<:]]shafts?[[:>:]]' (29 codes), derived in SQL. "
            "Use this view ONLY when the question says forged, or shaft "
            "MATERIAL, or bar stock, or names the catalogue explicitly. "
            "Answering a plain shaft question from here returns 88 instead of "
            "29 - the four forged-bar names do not even contain the word "
            "'shaft'.\n"
            "This is the CATALOGUE side. The IMPORT side is v_import_shafts - "
            "3 types, 82 lines, different wording ('Forged Steel Round Bar' "
            "there vs 'Forged Round Bar' here). Neither answers the other: "
            "'what shaft material is in the catalogue' is 4 names / 88 codes; "
            "'how many shaft types do we import' is 3.\n"
            "This material genuinely has NO stock - a total available quantity "
            "of 0 is the correct answer, not a reason to widen the search."
        ),
    },
    {
        "term": "shafts in imports / imported shafts",
        "meaning": (
            "What we IMPORT as shafts. Exactly THREE types, per the business:\n"
            "  Forged Steel Round Bar          79 import lines\n"
            "  Forged Alloy Steel Round Bar     2 import lines\n"
            "  Forged Steel Hollow Drill Bar    1 import line\n"
            "82 lines in total across 19 consignments. Nothing else counts as a "
            "shaft in the imports context."
        ),
        "maps_to": (
            "v_import_shafts(id, consignment_id, item_code, item_name, "
            "shaft_type, specification, quantity, uom, unit_price, "
            "current_status, origin, eta, etd, supplier). shaft_type already "
            "normalises the three spellings, so GROUP BY shaft_type gives "
            "exactly three groups.\n"
            "Soft-deleted lines and consignments are already excluded, so do "
            "NOT add is_deleted filters on top."
        ),
        "notes": (
            "THESE LIVE ON THE IMPORT LINES, NOT IN THE ITEM MASTER. Searching "
            "`items` for 'Forged Steel Round Bar' returns NOTHING - the master "
            "spells its equivalents differently ('Forged Round Bar', no "
            "'Steel'), and the imported ones were never catalogued. A query "
            "that starts from items and joins to imports will answer zero.\n"
            "The catalogue's own shaft material is a DIFFERENT set with "
            "different wording - see the shaft material term and "
            "v_import_shaft_material. 'How many shaft types do we import' is "
            "3 (this view); 'what shaft material is in the catalogue' is 4 "
            "names / 88 codes (that one). Neither answers the other.\n"
            "For shafts generally - not imports - match items.name against the "
            "shaft stem in SQL; there is no view for that on purpose."
        ),
    },
    {
        "term": "export order / logistics consignment",
        "meaning": (
            "One outbound order. Export orders ship abroad; Local orders serve "
            "domestic sugar and cement customers."
        ),
        "maps_to": (
            "logistics_consignments.order_type ('Export' / 'Local'), "
            ".department ('Sugar' / 'Cement'), .mo_no (the EXPORT NUMBER), "
            ".batch_label (the batch)"
        ),
        "notes": (
            "mo_no holds the export number the business quotes ('2360', "
            "'25-018'), not a separate MO. current_status runs 'Under "
            "Production' -> 'Packed' -> 'Gate Out' -> 'Sailing' -> 'Delivered'; "
            "some rows carry variants like 'Un Packed', 'Un-Packed', 'Size "
            "Pending', 'At QFL', 'At Port'. Always add is_deleted = false."
        ),
    },
    {
        # Deliberately NOT titled "(NOT AVAILABLE)". That label made the term a
        # magnet for any question containing the word "available" and turned a
        # narrow "we do not track this" note into a general-purpose refusal.
        "term": "export paperwork status: invoice, packing list, certificate of origin, bill of lading, GD",
        "meaning": (
            "Whether each document for an export (invoice, packing list, "
            "certificate of origin, B/L, GD) has been completed for customs, "
            "the customer and the bank. This is tracked in the source workbook "
            "but is NOT loaded into the database."
        ),
        "maps_to": "nothing - no table holds a document status",
        "notes": (
            "There is no table for export paperwork. Questions about pending "
            "documents, document completion percentages, or which paperwork is "
            "outstanding CANNOT be answered from this database - say so plainly. "
            "Do NOT substitute logistics_consignments.current_status: that is "
            "the shipment stage ('Packed', 'Sailing', 'Delivered') and says "
            "nothing about paperwork."
        ),
    },
    {
        "term": "RFD",
        "meaning": "Ready for dispatch - packing complete and cargo can move.",
        "maps_to": "logistics_items.planned_rfd_date, logistics_items.actual_rfd_date",
        "notes": "actual minus planned is the dispatch-readiness delay.",
    },
    {
        "term": "packing / packing delay",
        "meaning": "Physical packing of an export order into packages.",
        "maps_to": (
            "logistics_packages.packing_date, .packing_ready_date, .status, "
            ".quoted_packing_cost, .actual_packing_cost, .gross_weight"
        ),
        "notes": (
            "status is 'Packed' / 'Pending' / 'Gate Out'. Packing costs are "
            "sparsely filled - only ~25 packages carry a figure - so a cost "
            "question over all packages will mostly return NULLs; say so rather "
            "than reporting a total as if it were complete."
        ),
    },
    {
        "term": "container",
        "meaning": "A shipping container booked for an export order.",
        "maps_to": "logistics_containers.container_type, .container_no",
        "notes": (
            "ONE ROW IS ONE CONTAINER. Count rows: 157 containers across 106 "
            "orders. container_type values look like \"20' Standard\", "
            "\"40' Flat Rack\", \"20' Open Top\", \"40' Out of Gauge\", 'LCL', "
            "'AIR'.\\n"
            "container_no IS NULL ON EVERY ROW, and that is expected, not "
            "missing data - the source recorded a COUNT per container type, not "
            "individual container numbers, so the loader created one row per "
            "container with the type and no number. This does NOT prevent "
            "counting containers and is NOT a reason to say container data is "
            "unavailable. Refusing to answer 'how many containers' because the "
            "numbers are absent is wrong; the containers are right there, one "
            "per row. Only a question about a SPECIFIC container number cannot "
            "be answered."
        ),
    },
    {
        "term": "trucking / road movement / transporter",
        "meaning": (
            "Road movement of cargo by a transporter, inbound or outbound, "
            "including the vehicles used and the freight paid."
        ),
        "maps_to": (
            "trucking_consignments.movement_type ('Inbound' / 'Outbound' / "
            "'Intrafactory'), .transporter_name, .execution_date, "
            ".reference_no; trucking_vehicles.vehicle_number, .vehicle_type, "
            ".tracking_status"
        ),
        "notes": (
            "Header plus vehicle lines: one job moves on several trucks and "
            "each truck carries its own tracking_status ('Delivered' / 'Going "
            "to load'). There is NO job-level status column - a job is only "
            "closed when EVERY vehicle is 'Delivered'. Trucking has no foreign "
            "key to logistics or imports; the only link is reference_no text, "
            "so do not invent a join.\\n"
            "COUNT VEHICLE ROWS, NOT DISTINCT VEHICLE NUMBERS. There are 464 "
            "vehicle rows but vehicle_number is NULL on 251 of them, so "
            "COUNT(DISTINCT vehicle_number) returns 204 and silently discards "
            "more than half the movements. 'How many vehicles', 'how many "
            "trucks' and 'how many vehicles were used' all mean the 464 rows - "
            "each row is one truck on one job. Only use DISTINCT "
            "vehicle_number when the user explicitly asks how many DIFFERENT "
            "or UNIQUE physical trucks, and say that it covers only the 213 "
            "rows that carry a registration.\\n"
            "movement_type is NULL on 191 of 399 jobs, so Inbound + Outbound "
            "(208) is not the job total (399)."
        ),
    },
    {
        "term": "freight overrun / freight savings",
        "meaning": "Actual freight cost against what was quoted.",
        "maps_to": (
            "trucking_consignments.actual_freight - quoted_freight (negative = "
            "saving); logistics_packages.actual_packing_cost vs "
            "quoted_packing_cost"
        ),
        "notes": (
            "Export shipping costs are a set of named columns on "
            "logistics_consignments (sea_air_freight, trucking_lhr_to_khi, "
            "fumigation_cost, lashing, qfl_charges, custom_clearance_charges, "
            "port_charges, dhl_charges, insurance, packing_cost). Total "
            "shipping cost is their SUM - there is no stored total column."
        ),
    },
    {
        "term": "landed cost / ELC / ALC",
        "meaning": (
            "ELC is the estimated landed cost of an imported line, ALC the "
            "actual. Both are typed in by a user per line, never calculated."
        ),
        "maps_to": (
            "consignment_items.elc, consignment_items.alc, "
            ".variance_absolute, .variance_percentage"
        ),
        "notes": "Variance is ALC minus ELC, stored both absolute and as a percentage.",
    },
    {
        "term": "ETA slippage",
        "meaning": (
            "How much an import's arrival estimate has moved since the first "
            "promise."
        ),
        "maps_to": (
            "consignments.eta compared with the earliest "
            "eta_revision_history.previous_eta for that consignment"
        ),
        "notes": (
            "Every ETA change is a row in eta_revision_history, so slippage is "
            "reconstructed from that table rather than from numbered eta_1st.."
            "eta_4th columns, which no longer exist."
        ),
    },
    {
        "term": "demurrage / detention risk",
        "meaning": "Container held past its free days at port, which triggers charges.",
        "maps_to": (
            "consignments.free_days_allowed, .gate_out_date, "
            ".demurrage_or_detention_paid, .container_detention"
        ),
        "notes": "At risk when gate_out_date is null and the free days are nearly used.",
    },
    {
        "term": "LC / letter of credit / payment instrument",
        "meaning": "Bank instrument used to pay a foreign supplier.",
        "maps_to": (
            "consignments.payment_instrument, .instrument_number, "
            ".opening_or_retirement_date; payments.value, .status, "
            ".retirement_date, .bank_charges"
        ),
        "notes": (
            "'Retirement' is the final settlement of the LC. Partial payments "
            "are normal - payments is a child table, so sum it per consignment."
        ),
    },
    {
        "term": "supplier / vendor",
        "meaning": (
            "Anyone we buy from. Suppliers sit in TWO places that do not join: "
            "local purchases record a free-text name, imports point at a small "
            "master table."
        ),
        "maps_to": (
            "LOCAL purchases: purchases_data.supplier, free text, 976 distinct "
            "names.\\n"
            "IMPORTS: suppliers.name joined via consignments.supplier_id, 36 "
            "rows, of which 35 never appear in local purchases.\\n"
            "'Suppliers we have purchased from' means BOTH - 1,011 distinct "
            "names once unioned on lower(trim(name)). Imports are purchases.\\n"
            "NARROW TO ONE SIDE whenever the user names it. Anything mentioning "
            "local, purchase records, purchases_data, or purchase lines means "
            "purchases_data ALONE (976). Anything mentioning imports, "
            "consignments or foreign suppliers means the master ALONE (36). "
            "Only an unqualified 'suppliers we buy from' takes both. Always say "
            "which scope the answer used."
        ),
        "notes": (
            "Fixed at BOTH by default. Left to judgement this answered 976 on "
            "one run and 1,011 on the next - a 35-supplier swing on identical "
            "wording. A slightly broader answer that is always the same beats a "
            "narrower one that changes.\\n"
            "The two sides do not join on a key: purchases_data.supplier is "
            "free text and there is no supplier_id on it. Match by name with "
            "lower(trim(...)) when crossing them, and expect near-duplicates "
            "from spelling.\\n"
            "For performance questions, use purchase vs required_d on local "
            "purchases (see procurement lead time) - imports have no equivalent "
            "pair of dates."
        ),
    },
    {
        "term": "soft delete / deleted records",
        "meaning": (
            "Nothing is ever physically deleted in the ERP tables; deleting "
            "only sets a flag."
        ),
        "maps_to": "is_deleted on consignments, consignment_items, logistics_*, trucking_*",
        "notes": (
            "ALWAYS add 'AND <alias>.is_deleted = false' to those tables or "
            "deleted records inflate every count. The stores tables (stock, "
            "issuance, store_requisition, purchases_data) have NO is_deleted "
            "column - adding the filter there is a SQL error."
        ),
    },
    {
        "term": "draft vs submitted records",
        "meaning": (
            "ERP records carry a completeness state: a draft may be missing "
            "fields, a submitted one passed validation."
        ),
        "maps_to": "record_state on consignments, logistics_consignments, trucking_consignments",
        "notes": (
            "Everything loaded from the workbooks is 'draft'. Do NOT filter on "
            "record_state unless the user is specifically asking about "
            "incomplete records - filtering to 'submitted' hides essentially "
            "all historical data."
        ),
    },
    {
        "term": "spelling variants in free-text columns",
        "meaning": (
            "Most descriptive columns were typed by hand over years, so the "
            "same real-world value appears under several spellings. Filtering "
            "on one exact spelling silently drops the rest."
        ),
        "maps_to": (
            "Known variant groups, verified against the data:\n"
            "  consignments.mode_of_shipment  'Sea'(52) AND 'By Sea'(18); "
            "'Air'(10) AND 'By  Air'(1, TWO spaces)\n"
            "  consignments.payment_instrument  'LC'(27) AND '100%LC'(1)\n"
            "  consignments.origin  'South Africa'(5) AND 'SA'(2); "
            "'Korea'(3) AND 'South Korea'(1)\n"
            "  logistics_consignments.clearing_agent  'H & H'(64) AND "
            "'H&H'(36); 'Eastern Freigher'(2) AND 'Eastern'(2)\n"
            "  logistics_consignments.current_status  'Un Packed'(14) AND "
            "'Un-Packed'(5)\n"
            "  logistics_packages.status  'Gate Out'(211) AND 'Gateout'(1)\n"
            "  trucking_vehicles.vehicle_type  \"40' Flat Bed\"(109), "
            "\"40' Flatbed\"(5), \"40' Flat bed\"(3)\n"
            "  items.default_unit_of_measurement  'No.'(17,427) AND 'Nos.'(594)"
        ),
        "notes": (
            "Match these with ILIKE on a distinctive STEM rather than equality "
            "on one spelling: mode_of_shipment ILIKE '%sea%' catches both 'Sea' "
            "and 'By Sea'; clearing_agent with the spaces stripped "
            "(replace(clearing_agent,' ','') ILIKE '%h&h%') catches both H&H "
            "forms. For status columns where the exact set matters, list every "
            "variant explicitly - IN ('Un Packed','Un-Packed') - rather than "
            "picking one.\n"
            "When a count looks suspiciously round or low for something the "
            "business plainly does a lot of, an unmatched spelling variant is a "
            "likely cause."
        ),
    },
    {
        "term": "unit of measure / mixed units",
        "meaning": (
            "Quantities are recorded in whatever unit the paperwork used. The "
            "same column mixes weights, counts and pieces, so adding them "
            "together produces a number that means nothing."
        ),
        "maps_to": (
            "items.default_unit_of_measurement AS uom (join on item_code); "
            "consignment_items.unit_of_measurement AS uom"
        ),
        "notes": (
            "consignment_items mixes SEVEN units across 161 lines: Pcs(64), "
            "Ton(55), Kgs(12), Kg(12), Tons(10), MT(7), Set(1). "
            "SUM(quantity) over those adds tonnes to pieces - NEVER do it for a "
            "cross-item or cross-line total. Either GROUP BY the unit and "
            "report each separately, or restrict to one unit and say so.\n"
            "'Ton', 'Tons' and 'MT' are the same unit typed three ways, as are "
            "'Kg' and 'Kgs' - normalise before grouping or you get six groups "
            "where there are three.\n"
            "For a single item this is safe, because one item has one unit. "
            "Always return the uom column alongside any quantity so the number "
            "is readable."
        ),
    },
    {
        "term": "how far back the data goes (date coverage)",
        "meaning": (
            "The tables do NOT all cover the same period. A question spanning "
            "'the last 3 years' gets a full answer from issuance and a "
            "seven-month answer from requisitions, and nothing warns you."
        ),
        "maps_to": (
            "Verified coverage:\n"
            "  issuance.from_date            2022-12-01 -> 2026-07-28  (full)\n"
            "  purchases_data.purchase       2023-01-02 -> 2026-07-09  (full)\n"
            "  purchases_data.po_date        2022-05-09 -> 2026-07-09\n"
            "  store_requisition.prepare_date 2026-01-01 -> 2026-07-01  "
            "(7 MONTHS ONLY)\n"
            "  trucking_consignments.execution_date 2026-01-01 -> 2026-07-08  "
            "(2026 ONLY)\n"
            "  logistics_consignments.etd_sailing_date 2025-10-08 -> 2026-07-19\n"
            "  consignments.eta              2025-01-21 -> 2026-09-22  "
            "(filled on only 77 of 91 consignments)"
        ),
        "notes": (
            "Say the period the data actually covers whenever it is NARROWER "
            "than the period asked about. 'Requisitions over the last 3 years' "
            "can only be answered for 2026 - reporting the 2026 figure as a "
            "three-year total is wrong even though the SQL is right.\n"
            "Never compare a rate or total across two tables with different "
            "coverage without saying so: requisitions per month against "
            "issuances per month is 7 months against 44.\n"
            "stock has NO date column at all - it is today's snapshot and "
            "cannot be trended or filtered by period."
        ),
    },
    {
        "term": "unclassified rows (NULL categories)",
        "meaning": (
            "Several classification columns are blank on a large share of rows. "
            "Those rows are real records that were never categorised - not "
            "records that belong to some other category."
        ),
        "maps_to": (
            "trucking_consignments.movement_type  NULL on 191 of 399 jobs "
            "(Outbound 158, Inbound 50)\n"
            "logistics_consignments.order_type    NULL on 403 of 1,424 "
            "(Local 707, Export 314)\n"
            "logistics_consignments.department     NULL on 614 of 1,424\n"
            "consignments.consignment_type        NULL on 58 of 91\n"
            "logistics_consignments.incoterm      NULL on 1,232 of 1,424"
        ),
        "notes": (
            "Inbound + Outbound is 208, NOT the 399 total - the other 191 are "
            "unclassified. So 'how many trucking jobs' and 'how many "
            "inbound plus outbound jobs' are different questions with different "
            "answers, and neither is wrong.\n"
            "When a breakdown by one of these columns does not add up to the "
            "total, say how many were unclassified rather than quietly "
            "reporting a smaller total or forcing them into a bucket. Never "
            "treat NULL as the majority value."
        ),
    },
    {
        "term": "counting: rows versus things",
        "meaning": (
            "Most tables are LINE-level. COUNT(*) counts lines, which is "
            "usually not what a business question means."
        ),
        "maps_to": (
            "Measured grain of each table:\n"
            "  stock                 6,070 rows  ->  4,762 items "
            "(one row per item PER BRANCH)\n"
            "  issuance            260,715 rows  -> 100,779 documents\n"
            "  purchases_data       68,298 rows  ->  63,246 ref_no\n"
            "  consignment_items       161 lines ->      91 consignments\n"
            "  logistics_items       1,399 lines ->   1,387 orders\n"
            "  trucking_vehicles       464 rows  ->     399 jobs\n"
            "  logistics_containers    157 rows  ->     106 orders"
        ),
        "notes": (
            "Decide what the user is counting before writing COUNT(*). "
            "'How many items are out of stock' means items (871), not stock "
            "rows (1,407). 'How many issuances' almost always means documents "
            "(COUNT(DISTINCT issuance_code)), not lines. 'How many trucks' "
            "means vehicle ROWS (464); 'how many trucking jobs' means "
            "COUNT(DISTINCT consignment_id) (399).\n"
            "DISTINCT IS NOT AUTOMATICALLY SAFER - it silently drops NULLs, so "
            "on a sparsely filled column it undercounts badly. "
            "COUNT(DISTINCT vehicle_number) returns 204 of 464 vehicles, "
            "because 251 rows have no registration recorded. Reach for DISTINCT "
            "only when the user asked how many DIFFERENT or UNIQUE things there "
            "are, and check the column is actually populated before you do.\n"
            "For per-item stock questions use v_item_stock_position, which is "
            "already one row per item."
        ),
    },
    {
        "term": "when the honest answer is 'I cannot tell'",
        "meaning": (
            "Things this database genuinely does not hold. Saying so is "
            "correct; inventing a near-miss column is not."
        ),
        "maps_to": "nothing - these have no column anywhere",
        "notes": (
            "NOT IN THE DATABASE:\n"
            "  * export paperwork status (invoice / packing list / certificate "
            "of origin / BL / GD completion) - no table has a document status\n"
            "  * safety stock days, reorder points, ABC class - the old "
            "planning table is gone; lead time can only be OBSERVED from "
            "purchase history\n"
            "  * production output, scrap generated as waste, machine "
            "downtime, quality rejects\n"
            "  * selling prices or customer invoicing - purchases and landed "
            "cost only\n"
            "  * stock history - stock is a snapshot with no date\n"
            "When asked for one of these, say plainly that it is not recorded "
            "and name the nearest thing that IS. Do NOT substitute a column "
            "that sounds similar: logistics_consignments.current_status is the "
            "shipment stage and says nothing about paperwork.\n"
            "Equally: do not refuse for something that IS present. Materials, "
            "products and commodities are ITEMS found by name (scrap, resin, "
            "shafts, sand); statuses and branches are VALUES in a column. The "
            "absence of a table named after the thing is not the absence of "
            "the thing."
        ),
    },
]


def as_documents() -> list[str]:
    """Flatten the terms into plain text chunks for embedding."""
    docs = []
    for entry in BUSINESS_TERMS:
        parts = [
            f"TERM: {entry['term']}",
            f"MEANING: {entry['meaning']}",
            f"DATABASE MAPPING: {entry['maps_to']}",
        ]
        if entry.get("notes"):
            parts.append(f"NOTES: {entry['notes']}")
        docs.append("\n".join(parts))
    return docs


# Words that appear in half the questions ever asked and carry no meaning for
# term matching. Without this, "show scrap DATA for ALL AVAILABLE DATES" scores
# on every term that happens to mention data or availability.
_STOPWORDS = {
    "the", "and", "for", "all", "any", "our", "his", "her", "its", "was",
    "are", "were", "how", "what", "which", "when", "who", "why", "show",
    "give", "list", "tell", "have", "has", "had", "with", "from", "into",
    "that", "this", "these", "those", "there", "here", "data", "record",
    "records", "available", "date", "dates", "please", "many", "much",
    "some", "each", "per", "total", "count", "number", "info", "detail",
    "details", "get", "see", "want", "need", "can", "you", "me", "us",
}

# A single incidental word in common is not evidence a term is relevant. Two
# distinct content words is a low bar that still filters out the noise.
_MIN_KEYWORD_SCORE = 2


def keyword_search(query: str, top_k: int = 4) -> list[str]:
    """
    Cheap fallback used when the vector store is not available, or when it
    finds nothing close enough.

    Matches WHOLE WORDS and requires at least two of them. It used to do a bare
    substring test on any word over two characters, which is how "show scrap
    data for all available dates" ended up retrieving the export-paperwork term:
    "data" matched inside "database" and "available" matched inside the term's
    own "(NOT AVAILABLE)" label. The SQL agent was then told, with apparent
    authority, that the thing it was being asked about is not in the database -
    and refused, for a material with 10,311 issuance lines against it.

    Returning nothing is the RIGHT answer when nothing matches: the graph reads
    an empty context as "undocumented" and routes to the Knowledge Agent, which
    derives the mapping from the schema instead of guessing from noise.
    """
    import re as _re

    tokens = {
        word
        for word in _re.split(r"[^a-z0-9]+", (query or "").lower())
        if len(word) > 2 and word not in _STOPWORDS
    }
    if not tokens:
        return []

    scored = []
    for entry, document in zip(BUSINESS_TERMS, as_documents()):
        haystack = set(
            _re.split(r"[^a-z0-9]+", f"{entry['term']} {entry['meaning']}".lower())
        )
        score = len(tokens & haystack)
        if score >= _MIN_KEYWORD_SCORE:
            scored.append((score, document))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [document for _, document in scored[:top_k]]
