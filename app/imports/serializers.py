from app.imports.calculations import (
    ETA_TYPE, clearance_time, foreign_total, free_days_left,
    landed_cost_totals, line_total, missing_on_consignment, missing_on_item,
    pkr_total, slippage, stage_ageing, stage_group, system_remarks,
    transit_time, variance,
)
from app.imports.helpers import to_json

#-----------------------------------------------------
# TURNING ROWS INTO SOMETHING THE SCREEN CAN USE
#
# SQLAlchemy rows do not turn into JSON on their own, and a
# half written one would leak the internals of the table
# anyway. Every field the frontend gets is listed here on
# purpose.
#
# Anything worked out rather than typed in is sent already
# calculated, so the list view, the detail page and a
# printed report all show the same number.
#-----------------------------------------------------


#--------------------------------
# A MASTER TABLE ROW SHRUNK TO WHAT A DROPDOWN NEEDS
#--------------------------------

def serialize_master(row):
    if row is None:
        return None

    return {
        "id": row.id,
        "name": row.name
    }


def serialize_user(user):
    if user is None:
        return None

    return {
        "id": user.id,
        "username": user.username
    }


#--------------------------------
# AN ITEM LINE
#--------------------------------

def serialize_item(item):
    difference, percentage = variance(item.elc, item.alc)

    return {
        "id": item.id,
        "consignment_id": item.consignment_id,
        "item_id": item.item_id,

        "item_code": item.item_code,
        "item_name": item.item_name,
        "specification": item.specification,
        "hs_code": item.hs_code,

        "quantity": to_json(item.quantity),
        "unit_price": to_json(item.unit_price),
        "unit_of_measurement": item.unit_of_measurement,
        "batch_no": item.batch_no,

        "requisition_type": item.requisition_type,
        "reference_number": item.reference_number,
        "job_number": item.job_number,
        "mo_number": item.mo_number,
        "description": item.description,

        "elc": to_json(item.elc),
        "alc": to_json(item.alc),

        #--- worked out, never keyed in ---
        "line_total": to_json(line_total(item)),
        "variance": to_json(difference),
        "variance_percentage": to_json(percentage),
        "missing": missing_on_item(item)
    }


#--------------------------------
# A PAYMENT
#
# A payment with no rate of its own settles at the rate
# booked on the consignment, and the row says which of the
# two was used so the screen can grey out a borrowed one.
#--------------------------------

def serialize_payment(payment, header_rate):
    own_rate = payment.exchange_rate is not None
    rate = payment.exchange_rate if own_rate else header_rate

    if payment.value is None or rate is None:
        equivalent = None
    else:
        equivalent = payment.value * rate

    return {
        "id": payment.id,
        "consignment_id": payment.consignment_id,
        "retirement_date": to_json(payment.retirement_date),
        "value": to_json(payment.value),
        "exchange_rate": to_json(payment.exchange_rate),
        "bank_charges": to_json(payment.bank_charges),
        "status": payment.status,
        "bank_reference": payment.bank_reference,

        #--- worked out ---
        "rate_used": to_json(rate),
        "uses_own_rate": own_rate,
        "equivalent_pkr": to_json(equivalent)
    }


#--------------------------------
# HISTORY ROWS
#--------------------------------

def serialize_eta_revision(revision):
    return {
        "id": revision.id,
        "consignment_id": revision.consignment_id,
        "eta_type": revision.eta_type,
        "previous_eta": to_json(revision.previous_eta),
        "new_eta": to_json(revision.new_eta),
        "cause_of_revision": revision.cause_of_revision,
        "user": serialize_user(revision.user),
        "changed_at": to_json(revision.created_at)
    }


def serialize_status_update(update):
    return {
        "id": update.id,
        "consignment_id": update.consignment_id,
        "previous_status": update.previous_status,
        "new_status": update.new_status,
        "effective_date": to_json(update.effective_date),
        "remarks": update.remarks,
        "user": serialize_user(update.user),
        "changed_at": to_json(update.created_at)
    }


def serialize_change(change):
    return {
        "id": change.id,
        "consignment_id": change.consignment_id,
        "change_type": change.change_type,
        "previous_values": change.previous_values,
        "new_values": change.new_values,
        "changed_by": serialize_user(change.changed_by),
        "changed_at": to_json(change.created_at),
        "is_reverted": change.is_reverted,
        "reverted_by": serialize_user(change.reverted_by),
        "reverted_at": to_json(change.reverted_at),
        "is_revert": change.is_revert
    }


#--------------------------------
# ONE ROW OF THE LIST VIEW
#
# Deliberately lighter than the detail page. The list loads
# hundreds of these at a time, so it carries a summary of
# the items rather than every line.
#--------------------------------

def serialize_list_row(consignment, today):
    items = consignment.items
    total, priced = foreign_total(items)

    requisition_types = []

    for item in items:
        if item.requisition_type and item.requisition_type not in requisition_types:
            requisition_types.append(item.requisition_type)

    paid = None
    unpaid = None

    for payment in consignment.payments:
        if payment.value is None:
            continue

        if payment.status == "Paid":
            paid = (paid or 0) + payment.value
        else:
            unpaid = (unpaid or 0) + payment.value

    eta_revisions = [
        row for row in consignment.eta_revisions if row.eta_type == ETA_TYPE
    ]

    cleared_in, basis, basis_kind = clearance_time(consignment, consignment.status_updates)

    return {
        "id": consignment.id,
        "branch": serialize_master(consignment.branch),
        "supplier": serialize_master(consignment.supplier),
        "origin": consignment.origin,
        "currency": consignment.currency,
        "consignment_type": consignment.consignment_type,

        "current_status": consignment.current_status,
        "stage_group": stage_group(consignment.current_status),

        "etd": to_json(consignment.etd),
        "eta": to_json(consignment.eta),
        "eta_works": to_json(consignment.eta_works),

        "item_count": len(items),
        "requisition_types": requisition_types,
        "first_item": serialize_item(items[0]) if items else None,

        #--- worked out ---
        "foreign_total": to_json(total),
        "items_priced": priced,
        "is_provisional_total": priced != len(items),
        "exchange_rate": to_json(consignment.exchange_rate),
        "rate_booked_on": to_json(consignment.rate_booked_on),
        "pkr_total": to_json(pkr_total(items, consignment.exchange_rate)),

        "eta_revision_count": len(eta_revisions),
        "slippage_days": slippage(consignment, consignment.eta_revisions),
        "transit_days": transit_time(consignment),

        "payment_instrument": consignment.payment_instrument,
        "paid_to_date": to_json(paid),
        "recorded_unpaid": to_json(unpaid),

        "clearing_agent": serialize_master(consignment.clearing_agent),
        "gate_out_date": to_json(consignment.gate_out_date),
        "free_days_allowed": consignment.free_days_allowed,
        "free_days_left": free_days_left(consignment, consignment.status_updates, today),
        "clearance_days": cleared_in,

        "missing": missing_on_consignment(consignment, items),
        "is_deleted": consignment.is_deleted
    }


#--------------------------------
# THE WHOLE CONSIGNMENT
#
# Everything the detail page and all seven wizard steps
# need, in one call, so the wizard does not fire seven
# requests to draw one record.
#--------------------------------

def serialize_consignment(consignment, today):
    items = consignment.items
    total, priced = foreign_total(items)
    total_elc, counted_elc, total_alc, counted_alc = landed_cost_totals(items)

    cleared_in, basis, basis_kind = clearance_time(consignment, consignment.status_updates)

    eta_revisions = sorted(consignment.eta_revisions, key=lambda row: row.id)
    status_updates = sorted(
        consignment.status_updates,
        key=lambda row: (row.effective_date, row.id)
    )

    bank_charges = None

    for payment in consignment.payments:
        if payment.bank_charges is not None:
            bank_charges = (bank_charges or 0) + payment.bank_charges

    return {
        "id": consignment.id,

        #--- step 1, consignment ---
        "branch": serialize_master(consignment.branch),
        "supplier": serialize_master(consignment.supplier),
        "origin": consignment.origin,
        "currency": consignment.currency,
        "consignment_type": consignment.consignment_type,
        "po_date": to_json(consignment.po_date),

        #--- step 2, finance ---
        "payment_instrument": consignment.payment_instrument,
        "instrument_number": consignment.instrument_number,
        "opening_or_retirement_date": to_json(consignment.opening_or_retirement_date),
        "works": serialize_master(consignment.works),
        "exchange_rate": to_json(consignment.exchange_rate),
        "rate_booked_on": to_json(consignment.rate_booked_on),
        "rate_source": consignment.rate_source,

        #--- step 3, shipping ---
        "mode_of_shipment": consignment.mode_of_shipment,
        "loading_port": serialize_master(consignment.loading_port),
        "delivery_port": serialize_master(consignment.delivery_port),
        "cargo_readiness_date": to_json(consignment.cargo_readiness_date),
        "etd": to_json(consignment.etd),
        "eta": to_json(consignment.eta),
        "eta_works": to_json(consignment.eta_works),

        #--- step 5, status ---
        "current_status": consignment.current_status,
        "stage_group": stage_group(consignment.current_status),

        #--- step 6, clearance ---
        "clearing_agent": serialize_master(consignment.clearing_agent),
        "gd_number": consignment.gd_number,
        "gd_filing_date": to_json(consignment.gd_filing_date),
        "free_days_allowed": consignment.free_days_allowed,
        "gate_out_date": to_json(consignment.gate_out_date),
        "demurrage_or_detention_paid": to_json(consignment.demurrage_or_detention_paid),

        #--- who and when ---
        "created_by": serialize_user(consignment.created_by),
        "created_at": to_json(consignment.created_at),
        "updated_at": to_json(consignment.updated_at),
        "is_deleted": consignment.is_deleted,
        "deleted_at": to_json(consignment.deleted_at),
        "deleted_by": serialize_user(consignment.deleted_by),

        #--- children ---
        "items": [serialize_item(item) for item in items],
        "payments": [
            serialize_payment(payment, consignment.exchange_rate)
            for payment in consignment.payments
        ],
        "eta_revisions": [serialize_eta_revision(row) for row in eta_revisions],
        "status_updates": [serialize_status_update(row) for row in status_updates],

        #--- worked out, never keyed in ---
        "foreign_total": to_json(total),
        "items_priced": priced,
        "is_provisional_total": priced != len(items),
        "pkr_total": to_json(pkr_total(items, consignment.exchange_rate)),
        "bank_charges_total": to_json(bank_charges),

        "transit_days": transit_time(consignment),
        "slippage_days": slippage(consignment, consignment.eta_revisions),

        "arrival_basis": to_json(basis),
        "arrival_basis_kind": basis_kind,
        "clearance_days": cleared_in,
        "free_days_left": free_days_left(consignment, consignment.status_updates, today),

        "elc_total": to_json(total_elc),
        "items_with_elc": counted_elc,
        "alc_total": to_json(total_alc),
        "items_with_alc": counted_alc,

        "stage_ageing": stage_ageing(consignment.status_updates, today),
        "system_remarks": system_remarks(
            consignment, consignment.eta_revisions, consignment.status_updates, today
        ),
        "missing": missing_on_consignment(consignment, items)
    }
