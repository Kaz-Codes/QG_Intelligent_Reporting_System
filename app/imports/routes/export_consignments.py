from app.imports.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.imports.helpers import fetch_consignments_page
from app.export_utils import xlsx_response
from typing import Optional
from datetime import date
import logging
from app.imports.order_view import (
    order_branch_name, order_currency, order_exchange_rate, order_incoterm,
    order_instrument_number, order_of, order_origin, order_payment_instrument,
    order_rate_booked_on, order_rate_source, order_supplier_name, order_type,
    consignment_number, payment_reference,
)

logger = logging.getLogger(__name__)

#===========================================================================
# THE IMPORTS EXPORT - ONE ITEM, ONE ROW
#
# Requirements lines 163-173, finding 12, build-order step 2:
#
#   "One item = one row. Every item gets its own row, carrying all of its
#    consignment's and batch's details alongside it."
#   "Every field entered anywhere in the module must appear as a column - all
#    five steps, consignment-level, batch-level and item-level."
#   "Excel export must exclude: deleted consignments, drafts."
#
# WHAT THIS REPLACES. One row per consignment, with the items folded into a
# comma-joined summary string and the requisition types into another. That
# sheet could not answer a question about an item - no quantity, no price, no
# HS code, no landed cost - which is most of what the module records. It also
# carried a "Marked finished" column listing drafts rather than excluding them.
#
# THE FOUR SOURCES, and why a column's home matters more than it looks.
# A row is a LINE, and the values around it come from four different rows:
#
#   [O]  the ORDER      consignment_batch_groups - the LC's commercial terms,
#                       shared by every batch of it
#   [B]  the BATCH      consignments - this shipment: its dates, its status,
#                       its clearance
#   [OL] the ORDER LINE consignment_order_items - what was BOUGHT: identity,
#                       specification, price, the demand dates
#   [SL] the SHIPMENT   consignment_items - what THIS batch carries of it:
#        LINE           the allocated quantity, weights, dimensions, landed cost
#
# Get one wrong and the sheet is still 81 columns of plausible-looking data.
# Every column below is tagged, and `drive_export.py` asserts each against SQL.
#
# WHY THE SPEC IS ONE TABLE. Header and value live in the same tuple, so a
# column cannot be inserted in one list and forgotten in the other - which is
# how a 20-column sheet silently shifts every value one place left.
#===========================================================================


def _money(value):
    return float(value) if value is not None else None


def _name(obj):
    return obj.name if obj is not None else None


def _user(obj):
    return obj.username if obj is not None else None


def _line_value(line, order_line):
    """quantity x unit price, in the order's currency. None if either is absent.

    NOT zero: a line with no price is unpriced, and a zero would sum into a
    total as though the goods were free.
    """
    if line is None or order_line is None:
        return None
    if line.quantity is None or order_line.unit_price is None:
        return None
    return float(line.quantity) * float(order_line.unit_price)


def _line_value_pkr(line, order_line, consignment):
    foreign = _line_value(line, order_line)
    rate = order_exchange_rate(consignment)
    if foreign is None or rate is None:
        return None
    return foreign * float(rate)


def _payment_count(consignment):
    return len([p for p in (consignment.payments or []) if not p.is_deleted])


def _payment_total(consignment):
    paid = [p.value for p in (consignment.payments or [])
            if not p.is_deleted and p.value is not None]
    return float(sum(paid)) if paid else None


#---------------------------------------------------------------------------
# THE COLUMNS. (header, extractor) where extractor takes (c, line, ol).
#
#   c    the consignment  [B]   - and its order reached via order_* accessors
#   line the shipment line [SL] - None for a consignment with no live lines
#   ol   the order line   [OL]  - None likewise
#
# ORDER OF THE GROUPS: identity, then the item (the row's subject), then its
# quantities and money, then the terms it was bought under, then dates, status,
# clearance, packing, landed cost, and finally the consignment-level totals and
# admin. An 81-column sheet is navigable only if the columns arrive in the
# order a person reads a shipment.
#---------------------------------------------------------------------------

COLUMNS = [
    # --- identity ------------------------------------------------------ [O][B]
    ("Consignment no.",        lambda c, l, o: consignment_number(c)),
    ("Payment reference",      lambda c, l, o: payment_reference(c) or None),
    ("Batch",                  lambda c, l, o: c.batch_sequence),

    # --- the item: what this row is about ------------------------------- [OL]
    ("Item code",              lambda c, l, o: o.item_code if o else None),
    ("Item name",              lambda c, l, o: o.item_name if o else None),
    ("Placeholder name",       lambda c, l, o: o.placeholder_name if o else None),
    ("Specification",          lambda c, l, o: o.specification if o else None),
    ("H.S. code",              lambda c, l, o: o.hs_code if o else None),
    ("Requisition type",       lambda c, l, o: o.requisition_type if o else None),
    ("Reference no.",          lambda c, l, o: o.reference_number if o else None),
    ("Job no.",                lambda c, l, o: o.job_number if o else None),
    ("MO no.",                 lambda c, l, o: o.mo_number if o else None),
    ("Item description",       lambda c, l, o: o.description if o else None),
    ("Item branch",            lambda c, l, o: _name(o.branch) if o else None),

    # --- quantity and value --------------------------------------- [OL][SL][D]
    ("Ordered qty",            lambda c, l, o: _money(o.ordered_quantity) if o else None),
    ("Allocated qty",          lambda c, l, o: _money(o.allocated_quantity) if o else None),
    ("This batch qty",         lambda c, l, o: _money(l.quantity) if l else None),
    ("UoM",                    lambda c, l, o: o.unit_of_measurement if o else None),
    ("Unit price",             lambda c, l, o: _money(o.unit_price) if o else None),
    ("Price basis",            lambda c, l, o: o.price_basis if o else None),
    ("Weight unit price",      lambda c, l, o: _money(o.weight_unit_price) if o else None),
    ("Unit weight",            lambda c, l, o: _money(o.unit_weight) if o else None),
    ("Line value (foreign)",   lambda c, l, o: _line_value(l, o)),
    ("Line value (PKR)",       lambda c, l, o: _line_value_pkr(l, o, c)),

    # --- the order's terms ------------------------------------------------- [O]
    ("Supplier",               lambda c, l, o: order_supplier_name(c)),
    ("Works / Branch",         lambda c, l, o: order_branch_name(c)),
    ("Country of origin",      lambda c, l, o: order_origin(c)),
    ("Currency",               lambda c, l, o: order_currency(c)),
    ("Type",                   lambda c, l, o: order_type(c)),
    ("Incoterm",               lambda c, l, o: order_incoterm(c)),
    ("Payment instrument",     lambda c, l, o: order_payment_instrument(c)),
    ("Instrument no.",         lambda c, l, o: order_instrument_number(c)),
    ("Exchange rate",          lambda c, l, o: _money(order_exchange_rate(c))),
    ("Rate booked on",         lambda c, l, o: order_rate_booked_on(c)),
    ("Rate source",            lambda c, l, o: order_rate_source(c)),
    ("Insurance amount",       lambda c, l, o: _money(
        getattr(order_of(c), "insurance_amount", None))),

    # --- the demand dates, per line --------------------------------------- [OL]
    ("Requisition date",       lambda c, l, o: o.requisition_date if o else None),
    ("Required date",          lambda c, l, o: o.required_date if o else None),

    # --- shipment ----------------------------------------------------- [B][SL]
    ("PO date",                lambda c, l, o: c.po_date),
    ("Mode of shipment",       lambda c, l, o: c.mode_of_shipment),
    ("Cargo readiness",        lambda c, l, o: c.cargo_readiness_date),
    ("ETD",                    lambda c, l, o: c.etd),
    ("ETA",                    lambda c, l, o: c.eta),
    ("ETA works",              lambda c, l, o: c.eta_works),
    ("Line ETA works",         lambda c, l, o: l.eta_works if l else None),
    ("Loading port",           lambda c, l, o: _name(c.loading_port)),
    ("Delivery port",          lambda c, l, o: _name(c.delivery_port)),
    ("Opening / retirement",   lambda c, l, o: c.opening_or_retirement_date),

    # --- status ------------------------------------------------------------ [B]
    ("Status",                 lambda c, l, o: c.current_status),
    ("Status effective date",  lambda c, l, o: c.effective_date),
    ("Sent to logistics at",   lambda c, l, o: c.sent_to_logistics_at),
    ("Sent to trucking at",    lambda c, l, o: c.sent_to_trucking_at),

    # --- clearance ---------------------------------------------------------- [B]
    ("Clearing agent",         lambda c, l, o: _name(c.clearing_agent)),
    ("GD number",              lambda c, l, o: c.gd_number),
    ("GD filing date",         lambda c, l, o: c.gd_filing_date),
    ("Free days allowed",      lambda c, l, o: c.free_days_allowed),
    ("Gate out",               lambda c, l, o: c.gate_out_date),
    ("Demurrage / detention",  lambda c, l, o: _money(c.demurrage_or_detention_paid)),
    ("Container detention",    lambda c, l, o: _money(c.container_detention)),

    # --- packing, per shipment line ---------------------------------------- [SL]
    ("Batch no.",              lambda c, l, o: l.batch_no if l else None),
    ("Net weight",             lambda c, l, o: _money(l.net_weight) if l else None),
    ("Gross weight",           lambda c, l, o: _money(l.gross_weight) if l else None),
    ("Length",                 lambda c, l, o: _money(l.length) if l else None),
    ("Width",                  lambda c, l, o: _money(l.width) if l else None),
    ("Height",                 lambda c, l, o: _money(l.height) if l else None),

    # --- landed cost, with its audit trail ---------------------------------[SL]
    #
    # ELC and ALC are manual, per item, entered weeks apart, and rule 11 exists
    # because somebody has to be accountable for each figure. A sheet showing
    # the number without who entered it is the wrong half of that rule.
    ("ELC",                    lambda c, l, o: _money(l.elc) if l else None),
    ("ELC entered by",         lambda c, l, o: _user(l.elc_updated_by) if l else None),
    ("ELC entered at",         lambda c, l, o: l.elc_updated_at if l else None),
    ("ALC",                    lambda c, l, o: _money(l.alc) if l else None),
    ("ALC entered by",         lambda c, l, o: _user(l.alc_updated_by) if l else None),
    ("ALC entered at",         lambda c, l, o: l.alc_updated_at if l else None),
    ("Variance",               lambda c, l, o: _money(l.variance_absolute) if l else None),
    ("Variance %",             lambda c, l, o: _money(l.variance_percentage) if l else None),

    # --- consignment totals, payments and admin ------------------------- [B][D]
    #
    # PAYMENTS ARE SUMMARISED, NOT FOLDED IN. A consignment has many payments,
    # so joining them would multiply every item row by every payment and break
    # "one item = one row". Two order-level facts an operator reading the sheet
    # will want; the payment DETAIL stays where it is entered.
    ("Payments recorded",      lambda c, l, o: _payment_count(c)),
    ("Total paid",             lambda c, l, o: _payment_total(c)),
    ("Consignment foreign total", lambda c, l, o: _money(c.foreign_total)),
    ("Consignment PKR total",  lambda c, l, o: _money(c.pkr_total)),
    ("User remarks",           lambda c, l, o: c.remarks),
    ("Created by",             lambda c, l, o: _user(c.created_by)),
    ("Created at",             lambda c, l, o: c.created_at),
    ("Batch record id",        lambda c, l, o: c.id),
]

HEADERS = [header for header, _ in COLUMNS]


def _rows_for(consignment):
    """One row per LIVE line - or ONE row with the item columns blank.

    A consignment with no live lines still appears. Dropping it would make the
    sheet's consignment count disagree with the list screen with nothing to say
    why, and a submitted consignment carrying no items is an anomaly worth
    seeing rather than one worth hiding. This is the LEFT JOIN, in Python.
    """
    # SORTED BY LINE ID, so the sheet has a STABLE row order. Relationship
    # iteration order is not guaranteed, and an export people re-run and
    # compare between weeks must not reshuffle its rows for no reason - a
    # diff of two runs should show what changed, not the loading order.
    lines = sorted(
        (line for line in (consignment.items or []) if not line.is_deleted),
        key=lambda line: line.id,
    )

    if not lines:
        return [[extract(consignment, None, None) for _, extract in COLUMNS]]

    return [
        [extract(consignment, line, line.order_item) for _, extract in COLUMNS]
        for line in lines
    ]


#-----------------------------------------------------
# EXPORT THE FILTERED CONSIGNMENTS TO EXCEL
#
# Same query parameters as the list endpoint, so the export always matches the
# filtered set on screen - EXCEPT for the two exclusions the requirements make
# unconditional, below. Runs the shared list query with no page limit.
#-----------------------------------------------------

@router.get("/export")
def export_consignments(
    request : Request,
    status : Optional[list[str]] = Query(None),
    stage : Optional[str] = None,
    branch_id : Optional[list[int]] = Query(None),
    supplier_id : Optional[list[int]] = Query(None),
    requisition_type : Optional[list[str]] = Query(None),
    drafts_only : bool = False,
    # DEFAULTS TO TRUE HERE, AND ONLY HERE. The list defaults to False.
    #
    # MEASURED, and the reason this is not a matching default: on the real
    # data 181 live consignments are 149 non-draft and 33 non-closed - but
    # only ONE is both. Almost everything submitted has reached "Arrived at
    # Works", and almost everything still open is a draft. Keeping the list's
    # default here would make the button produce a ONE-ROW file out of 342,
    # which reads as a broken export rather than as a filter.
    #
    # The requirement names exactly two exclusions - deleted and drafts
    # (line 173). A closed consignment is not either of those: it is completed
    # work, which is precisely what a record of imports should contain.
    #
    # THE COST, STATED: the export no longer matches the on-screen filter when
    # "Include completed" is unticked, and "what you see is what you export"
    # was the property this endpoint was built around. That is a deliberate
    # trade and it is ONE LINE to reverse. An explicit `include_closed=false`
    # is still honoured.
    include_closed : bool = True,
    include_deleted : bool = False,
    etd_from : Optional[date] = None,
    etd_to : Optional[date] = None,
    q : Optional[str] = None,
    ):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_IMPORTS, db)

        # DELETED AND DRAFTS ARE EXCLUDED, AND THE CALLER CANNOT ASK OTHERWISE.
        #
        # Requirements line 173. `include_deleted` is accepted so the signature
        # still matches the list endpoint's, and then ignored: the export is a
        # record of real, finished work, and a deleted or half-entered
        # consignment in a sheet that gets mailed around is worse than a
        # missing one. `drafts_only` becomes self-contradictory here and
        # returns nothing, which is the honest answer to asking a
        # drafts-excluding export for only its drafts.
        consignments, _ = fetch_consignments_page(
            db, False, include_closed, status, stage,
            branch_id, supplier_id, requisition_type,
            drafts_only, etd_from, etd_to, q, page=1, page_size=1_000_000,
        )

        rows = []
        for consignment in consignments:
            if consignment.record_state == "draft":
                continue
            rows.extend(_rows_for(consignment))

        return xlsx_response("consignments.xlsx", HEADERS, rows,
                             sheet_title="Consignments")

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.imports.routes.export_consignments")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
