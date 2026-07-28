# database/schemas/stores_schemas.py
#
# STORES module tables: stock, issuance, store_requisition.
#
# IMPORTANT: run this AFTER imports_schemas, because these tables reference
# items(item_code), which is created in imports_schemas.
#
# Note: store_requisition.ref_no logically references purchases(ref_no), but
# purchases is not owned here, so ref_no is left as a plain TEXT column for now.
# Whoever owns the purchases table can add that FK later if required.
#
# Style follows logistics_schemas.py.


items_query = '''CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    item_code VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    default_specification VARCHAR(500),
    default_unit_of_measurement VARCHAR(50),
    category VARCHAR(255),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);'''


stock_query = '''CREATE TABLE IF NOT EXISTS stock(
    id                  BIGSERIAL PRIMARY KEY,
    item_code           TEXT,
    item_name           TEXT,
    branch              TEXT,
    hold_qty            NUMERIC(14,3),
    stock_qty           NUMERIC(14,3),
    stock_qty_amount    NUMERIC(18,2),
    available_qty       NUMERIC(14,3),
    available_amount    NUMERIC(18,2)
);'''


# ---------------------- ISSUANCE (consumption transactions) --------------
issuance_query = '''CREATE TABLE IF NOT EXISTS issuance(
    id                  BIGSERIAL PRIMARY KEY,
    issuance_code       TEXT UNIQUE,
    item_code           TEXT,
    item_name           TEXT,
    specification       TEXT,
    department          TEXT,
    branch              TEXT,
    issue_to_others     TEXT,
    authorized_by       TEXT,
    issued_by           TEXT,
    received_by         TEXT,
    description         TEXT,
    ref_no              TEXT,
    demand_ref_no       TEXT,
    quantity            NUMERIC(14,3),
    status              TEXT,
    from_date           DATE,
    unit_price          NUMERIC(14,3),
    total_price         NUMERIC(18,2),
    job_number          TEXT
);'''

# ---------------------- STORE REQUISITION --------------------------------
store_requisition_query = '''CREATE TABLE IF NOT EXISTS store_requisition(
    id              BIGSERIAL PRIMARY KEY,
    item_code           TEXT, 
    item_name           TEXT,
    ref_no              TEXT,               -- logically references purchases(ref_no)
    department          TEXT,
    branch              TEXT,
    prepare_date        DATE,
    description         TEXT,
    required_by         TEXT,
    req_quantity        NUMERIC(14,3),
    pur_quantity        NUMERIC(14,3),
    pending_quantity    NUMERIC(14,3),
    last_purchase       DATE,
    previous_price      TEXT,
    required_date       DATE,
    status              TEXT,
    sourced_by          TEXT,
    previous_supplier   TEXT,
    original_required_date   DATE,
    stock_in_date       DATE
);'''

#------------------------- PURCHASES DATA ------------------------------
purchases_query = '''CREATE TABLE IF NOT EXISTS purchases_data(
    id          BIGSERIAL PRIMARY KEY,
    item_code   TEXT,
    item_name   TEXT,
    specification   TEXT,
    po_number   TEXT,
    po_date     DATE,
    ref_no      TEXT, 		
    qty         INT,	
    branch      TEXT,
    amount      NUMERIC(14,3),	
    ppc_store   DATE,	
    required_d  DATE,		
    purchase    DATE, 		
    mop	        TEXT,
    dc_no       TEXT,
    bill_no     TEXT,	
    sourcing_o  TEXT,
    supplier    TEXT
);
'''

stores_schemas_queries = [stock_query, purchases_query, issuance_query, store_requisition_query]