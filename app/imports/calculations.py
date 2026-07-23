from decimal import Decimal

from app.enums import RequisitionType, Status

#-----------------------------------------------------
# THE FIGURES NOBODY TYPES IN
#
# Totals, transit time, clearance time, slippage, variance
# and the list of what is still missing. All of them are
# worked out here and handed to the frontend already done,
# so the screen and a printed report can never disagree.
#
# None of this is stored. The one exception is the exchange
# rate, which is saved on the consignment with the date it
# was taken, and the PKR total is always worked out from
# that stored rate and never from a live one.
#-----------------------------------------------------


#--------------------------------
# WHICH REQUISITION FIELDS APPLY TO WHICH TYPE
#
# Written once here. Adding a requisition type later is a
# one line change, not a hunt through if statements.
#--------------------------------

#--------------------------------
# THE TWO KINDS OF ETA REVISION
#
# One table logs both, so each row says which date it was
# about. Written once here so the routes and the reports
# cannot drift onto different spellings.
#--------------------------------

ETA_TYPE = "eta"
ETA_WORKS_TYPE = "eta_works"


REQUISITION_FIELDS = {
    RequisitionType.STORE.value: ["reference_number"],
    RequisitionType.ENGINEERING.value: ["reference_number", "job_number", "mo_number"],
    RequisitionType.OTHERS.value: ["description"],
}

FIELD_LABELS = {
    "reference_number": "Reference no.",
    "job_number": "Job no.",
    "mo_number": "MO no.",
    "description": "Description",
    "hs_code": "H.S. code",
    "batch_no": "Batch no.",
    "unit_price": "Unit price",
    "requisition_type": "Requisition type",
}


#--------------------------------
# THE SIX GROUPS THE LIST VIEW SHOWS
#
# The order of the statuses inside each group follows the
# order goods actually move in. Do not reorder it, reports
# depend on the sequence.
#--------------------------------

STAGE_GROUPS = [
    ("Pre-shipment", [Status.TT_LC_IN_PROCESS.value]),
    ("Production", [Status.UNDER_PRODUCTION.value, Status.READY_AWAITING_SAILING.value]),
    ("In transit", [Status.IN_TRANSIT.value]),
    ("Clearance", [Status.ARRIVED_AT_PORT.value, Status.UNDER_CUSTOM_CLEARANCE.value,
                   Status.UNDER_EXAMINATION.value, Status.UNDER_ASSESSMENT.value]),
    ("Inbound", [Status.ARRIVED_AT_QFL.value, Status.ON_ROAD.value]),
    ("Closed", [Status.ARRIVED_AT_WORKS.value]),
]

CLOSED_STATUS = Status.ARRIVED_AT_WORKS.value


def stage_group(status):
    for name, statuses in STAGE_GROUPS:
        if status in statuses:
            return name

    return STAGE_GROUPS[0][0]


#--------------------------------
# MONEY
#
# A line with no price is left out of the total rather than
# counted as zero, and the caller is told how many were left
# out so the screen can mark the figure as provisional.
#--------------------------------

def line_total(item):
    if item.unit_price is None or item.quantity is None:
        return None

    return item.quantity * item.unit_price


def foreign_total(items):
    total = Decimal("0")
    priced = 0

    for item in items:
        value = line_total(item)

        if value is not None:
            total = total + value
            priced = priced + 1

    return total, priced


def pkr_total(items, exchange_rate):
    if exchange_rate is None:
        return None

    total, priced = foreign_total(items)

    if priced == 0:
        return None

    return total * exchange_rate


#--------------------------------
# DAYS BETWEEN TWO DATES
#--------------------------------

def days_between(start, end):
    if start is None or end is None:
        return None

    return (end - start).days


#--------------------------------
# TRANSIT TIME
#--------------------------------

def transit_time(consignment):
    return days_between(consignment.etd, consignment.eta)


#--------------------------------
# WHEN THE GOODS ACTUALLY LANDED
#
# The day the status became "Arrived at port", read out of
# the status log. Free days and detention are billed from a
# real arrival, not from a predicted one. The ETA is only a
# fallback for while that status has not been recorded.
#--------------------------------

def arrival_date(consignment, status_updates):
    arrived = [
        row for row in status_updates
        if row.new_status == Status.ARRIVED_AT_PORT.value
    ]

    if arrived:
        arrived.sort(key=lambda row: row.effective_date)
        return arrived[0].effective_date, "arrival"

    return consignment.eta, "eta"


#--------------------------------
# CLEARANCE TIME
#
# Gate out minus the actual arrival date. Falls back to the
# ETA only when the arrival status was never recorded.
#--------------------------------

def clearance_time(consignment, status_updates):
    basis, basis_kind = arrival_date(consignment, status_updates)

    return days_between(basis, consignment.gate_out_date), basis, basis_kind


#--------------------------------
# FREE DAYS LEFT BEFORE DETENTION STARTS
#--------------------------------

def free_days_left(consignment, status_updates, today):
    if consignment.free_days_allowed is None:
        return None

    basis, basis_kind = arrival_date(consignment, status_updates)

    if basis is None:
        return None

    end = consignment.gate_out_date or today
    at_port = days_between(basis, end)

    if at_port is None:
        return None

    return consignment.free_days_allowed - at_port


#--------------------------------
# SLIPPAGE
#
# The current ETA against the very first one ever promised,
# read out of the revision log rather than out of a text
# field somebody could overwrite.
#--------------------------------

def slippage(consignment, eta_revisions):
    if consignment.eta is None:
        return None

    revisions = [
        row for row in eta_revisions
        if row.eta_type == ETA_TYPE and row.previous_eta is not None
    ]

    if not revisions:
        return None

    revisions.sort(key=lambda row: row.id)
    first_eta = revisions[0].previous_eta

    return days_between(first_eta, consignment.eta)


#--------------------------------
# LANDED COST VARIANCE
#
# Kept both as an amount and as a percentage, because a
# report shows one and the list view shows the other.
#--------------------------------

def variance(elc, alc):
    if elc is None or alc is None:
        return None, None

    difference = alc - elc

    if elc == 0:
        return difference, None

    percentage = (difference / elc) * Decimal("100")

    return difference, percentage


def landed_cost_totals(items):
    total_elc = Decimal("0")
    total_alc = Decimal("0")
    counted_elc = 0
    counted_alc = 0

    for item in items:
        if item.elc is not None:
            total_elc = total_elc + item.elc
            counted_elc = counted_elc + 1

        if item.alc is not None:
            total_alc = total_alc + item.alc
            counted_alc = counted_alc + 1

    return total_elc, counted_elc, total_alc, counted_alc


#--------------------------------
# WHAT IS STILL MISSING
#
# One list, so a field added to it shows up on the item
# badge, the step banner and the list view flag all at once
# instead of in one place and not the others.
#--------------------------------

def missing_on_item(item):
    missing = []

    if not item.item_name:
        missing.append("Item name")

    if not item.item_code:
        missing.append("Item code")

    if item.quantity is None:
        missing.append("Quantity")

    if not item.unit_of_measurement:
        missing.append("Unit of measure")

    if not item.hs_code:
        missing.append(FIELD_LABELS["hs_code"])

    if not item.batch_no:
        missing.append(FIELD_LABELS["batch_no"])

    if item.unit_price is None:
        missing.append(FIELD_LABELS["unit_price"])

    if not item.requisition_type:
        missing.append(FIELD_LABELS["requisition_type"])
    else:
        for field in REQUISITION_FIELDS.get(item.requisition_type, []):
            if not getattr(item, field):
                missing.append(FIELD_LABELS[field])

    return missing


def missing_on_consignment(consignment, items):
    missing = []

    header_fields = [
        ("branch_id", "Branch"),
        ("supplier_id", "Supplier"),
        ("origin", "Country of origin"),
        ("currency", "Currency"),
        ("consignment_type", "Consignment type"),
        ("po_date", "PO date"),
        ("payment_instrument", "Payment instrument"),
        ("instrument_number", "Instrument number"),
        ("works_id", "Works"),
        ("exchange_rate", "Exchange rate"),
        ("rate_booked_on", "Rate date"),
        ("mode_of_shipment", "Mode of shipment"),
        ("loading_port_id", "Port of loading"),
        ("delivery_port_id", "Port of delivery"),
        ("etd", "ETD"),
        ("eta", "ETA"),
    ]

    for field, label in header_fields:
        if getattr(consignment, field) is None:
            missing.append(label)

    if not items:
        missing.append("Items")

    for position, item in enumerate(items, start=1):
        for label in missing_on_item(item):
            missing.append(label + " on item " + str(position))

    return missing


#--------------------------------
# SYSTEM REMARKS
#
# Generated from the ETA and status history every time they
# are asked for. Storing them as text would let a user edit
# them and would destroy the delay analytics.
#--------------------------------

def ordinal(number):
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")

    return str(number) + suffix


def system_remarks(consignment, eta_revisions, status_updates, today):
    parts = []

    revisions = [row for row in eta_revisions if row.eta_type == ETA_TYPE]
    revisions.sort(key=lambda row: row.id)

    if revisions:
        chain = []

        if revisions[0].previous_eta is not None:
            chain.append(revisions[0].previous_eta)

        for row in revisions:
            chain.append(row.new_eta)

        written = []

        for position, value in enumerate(chain, start=1):
            text = ordinal(position) + " ETA " + value.isoformat()

            if position == len(chain):
                text = text + " (current)"

            written.append(text)

        parts.append(", ".join(written) + ".")
    else:
        parts.append("ETA has not been revised.")

    updates = sorted(status_updates, key=lambda row: (row.effective_date, row.id))

    if updates:
        current = updates[-1]
        held = days_between(current.effective_date, today)

        parts.append(
            "Currently " + current.new_status +
            " since " + current.effective_date.isoformat() +
            " (" + str(held) + (" day" if held == 1 else " days") + ")."
        )

        slowest_stage = None
        slowest_days = None

        for position, row in enumerate(updates):
            if position + 1 < len(updates):
                end = updates[position + 1].effective_date
            else:
                end = today

            spent = days_between(row.effective_date, end)

            if slowest_days is None or spent > slowest_days:
                slowest_days = spent
                slowest_stage = row.new_status

        if slowest_days is not None and slowest_days > 14:
            parts.append(
                "Longest stage so far: " + slowest_stage +
                ", " + str(slowest_days) + " days."
            )
    else:
        parts.append("Currently " + consignment.current_status + ".")

    return " ".join(parts)


#--------------------------------
# HOW LONG THE CONSIGNMENT SAT AT EACH STAGE
#
# Read off the status log, which is what makes "how long do
# we typically sit under examination" answerable at all.
#--------------------------------

def stage_ageing(status_updates, today):
    updates = sorted(status_updates, key=lambda row: (row.effective_date, row.id))
    ageing = []

    for position, row in enumerate(updates):
        if position + 1 < len(updates):
            end = updates[position + 1].effective_date
        else:
            end = today

        ageing.append({
            "status": row.new_status,
            "from": row.effective_date.isoformat(),
            "days": days_between(row.effective_date, end)
        })

    return ageing
