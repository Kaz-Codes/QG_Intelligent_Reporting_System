# from app.imports.helpers import fetch_consignment
from sqlalchemy.inspection import inspect
from datetime import date

from app.imports.demand_dates import (
    earliest_required_date, line_required_date, line_requisition_date,
)
from app.imports.allocation import allocation_view
from app.imports.order_view import (
    consignment_number,
    order_branch, order_currency, order_exchange_rate, order_incoterm,
    order_instrument_number, order_origin, order_payment_instrument,
    order_rate_booked_on, order_rate_source, order_supplier, order_type,
    payment_reference,
    order_branch_name,
)


#----------------------------------------
# AUTO-GENERATED SYSTEM REMARKS
#
# Built from the ETA revision and status history, never stored and never
# editable, so a user edit cannot wipe it and it is always current. Shown
# alongside the user's own remarks in reports. Kept in the serializer (not
# helpers) so serializers stays free of a helpers import cycle.
#----------------------------------------

_ORDINALS = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"]


def build_system_remarks(consignment):
    parts = []

    # ETA chain, oldest first, from the revision log.
    eta_rows = sorted(
        [r for r in consignment.eta_revisions if r.eta_type == "eta"],
        key=lambda r: r.id,
    )
    if eta_rows:
        chain = []
        first = eta_rows[0].previous_eta or eta_rows[0].new_eta
        if first:
            chain.append(first)
        for r in eta_rows:
            if r.new_eta:
                chain.append(r.new_eta)
        # collapse repeats
        seq = []
        for d in chain:
            if not seq or seq[-1] != d:
                seq.append(d)
        if len(seq) == 1:
            parts.append(f"ETA {seq[0]}.")
        elif len(seq) > 1:
            labelled = ", ".join(
                f"{_ORDINALS[i] if i < len(_ORDINALS) else str(i + 1) + 'th'} ETA {d}"
                for i, d in enumerate(seq)
            )
            parts.append(f"{labelled}.")

    # Current status and when it took effect.
    if consignment.current_status:
        status_rows = sorted(
            consignment.status_updates,
            key=lambda u: (u.effective_date or date.min, u.id),
        )
        latest = status_rows[-1] if status_rows else None
        if latest and latest.effective_date:
            parts.append(f"Currently {consignment.current_status} since {latest.effective_date}.")
        else:
            parts.append(f"Currently {consignment.current_status}.")

    return " ".join(parts)


#---------------------------------------
# CONVERT SQL ALCHEMY MODEL OBJECTS
# INTO PYTHON DICTIONARIES THAT 
# THAT CAN BE SENT IN RESPONSE
#---------------------------------------

def serialize_consignment(consignment, db, include_change_history=True,
                          has_pending_allocation=None):
    #saved_consignment = fetch_consignment(db, consignment.id)

    data = {
        "id" : consignment.id,

        # WHICH ORDER THIS CONSIGNMENT IS A BATCH OF, and where in it.
        #
        # Published because a list row that cannot say which order it belongs to
        # cannot show two batches of one LC as anything but two unrelated rows.
        # Both are server-controlled: `batch_sequence` is assigned at creation
        # and never reused, so 177-2 identifies one shipment for ever.
        #
        "batch_group_id" : consignment.batch_group_id,
        "batch_sequence" : consignment.batch_sequence,

        # DOES THIS ORDER STILL HAVE QUANTITY NOBODY HAS BATCHED?
        #
        # `None` means "not asked for", which is NOT the same as False and the
        # front end must not read it as such - the list sends
        # `include_batch_context=true` and gets a boolean; every other caller
        # gets null and renders no highlight rather than a confident "fully
        # allocated". Computed for a whole page in one query by the list route
        # (helpers.pending_allocation_ids), never by this function, because
        # deriving it here would mean loading `group.order_items` per row.
        "has_pending_allocation" : has_pending_allocation,

        # THE SHIPMENT'S NUMBER: "177" while an order holds one batch, "177-2"
        # once it has split.
        #
        # Published for exactly the reason `payment_reference` was (revision
        # 11): the rule has existed on the server since step 1 and nothing a
        # person looks at obeyed it. The list's top line is still
        # `String(c.id)`, so the moment this change creates a real second batch
        # the screen would show `184` - a number belonging to no consignment
        # anyone can look up. Rendering it is step 8; having it to render is
        # this step's job.
        #
        # DERIVED ON THE SERVER, NOT ASSEMBLED IN THE BROWSER. Three values
        # feed it (the founding batch's id, `batches_ever`, this row's
        # sequence) and the rule that combines them - a suffix only once an
        # order has EVER held two - is the one thing about numbering that a
        # front-end copy would get wrong first.
        "consignment_number" : consignment_number(consignment) or None,
        "branch" : serialize_master(order_branch(consignment)),
        "supplier" : serialize_master(order_supplier(consignment)),
        # `works` was free text and is RETIRED - the order's `works_branch_id`
        # replaced it, and that is what `branch` above already reports. The key
        # is still emitted so the wizard's Works input has something to bind to
        # until step 8 turns it into a branch dropdown, but it now carries the
        # branch NAME rather than a separately-typed string that could disagree
        # with it. The write path accepts and discards it
        # (RETIRED_PAYLOAD_FIELDS).
        "works" : order_branch_name(consignment),
        "clearing_agent" : serialize_master(consignment.clearing_agent),
        "loading_port" : serialize_master(consignment.loading_port),
        "delivery_port" : serialize_master(consignment.delivery_port),

        "items" : serialize_items(consignment.items),
        "eta_revisions" : serialize_many(consignment.eta_revisions),
        "status_updates" : serialize_many(consignment.status_updates),
        # THE ORDER'S PAYMENTS, not the batch's - step 9, section 4.4.
        #
        # `Consignment.payments` was REMOVED rather than left working, so this
        # line had to move or fail to compile. That is the point: the orphaned
        # `payments.consignment_id` is still populated, so the old relationship
        # would have gone on returning correct data until Revision B dropped the
        # column, weeks later and in a different change.
        #
        # One LC, one payment history: every batch of an order publishes the
        # same list, which is what the requirements ask for and what makes
        # Step 4 read-only on a later batch honest rather than merely disabled.
        # LC-LEVEL, beside the payments it belongs with. Read off the group
        # rather than the batch - insurance is taken out on the order.
        "insurance_amount" : (
            consignment.batch_group.insurance_amount
            if consignment.batch_group else None
        ),
        "payments" : serialize_many(
            consignment.batch_group.payments if consignment.batch_group else []
        ),

        "created_by" : consignment.created_by.username if consignment.created_by else None,
        "created_by_id" : consignment.created_by_id if consignment.created_by_id else None,
        "created_at" : consignment.created_at,

        "origin" : order_origin(consignment),
        "po_date" : consignment.po_date,

        # THE TWO DEMAND DATES, TREATED DIFFERENTLY ON PURPOSE.
        #
        # Both moved onto the order line, because one order can carry lines
        # requisitioned and needed months apart. What they need from the header
        # payload is not the same, though:
        #
        # `required_date` KEEPS a header-level value, and it is the EARLIEST
        # across this batch's lines. The list's delay column is a header-level
        # comparison that has to show ONE number and be sortable, and the list
        # payload carries no item lines at all — so the server has to supply the
        # minimum or the front end's `requiredDelayDays` silently reads nothing
        # while keeping its signature. Earliest, not latest: the column exists to
        # say "something in here is late", and the first date to pass is the
        # first thing that is late.
        #
        # `requisition_date` is GONE from the header and appears per line below.
        # It has no header-level consumer — it was a filter and a display, and
        # both are better per line — so nothing aggregates it and nothing should.
        # The requirements remove both from the main list anyway.
        "required_date" : earliest_required_date(consignment),
        "currency" : order_currency(consignment),
        "consignment_type" : order_type(consignment),
        "incoterm" : order_incoterm(consignment),
        "mode_of_shipment" : consignment.mode_of_shipment,
        "etd" : consignment.etd,
        "eta" : consignment.eta,
        "eta_works" : consignment.eta_works,
        "cargo_readiness_date" : consignment.cargo_readiness_date,
        "payment_instrument" : order_payment_instrument(consignment),
        "instrument_number" : order_instrument_number(consignment),

        # THE ORDER'S PAYMENT REFERENCE, mode + number concatenated: `lc68756`.
        #
        # Published because step 1 unified TEN backend call sites onto one rule
        # and then no screen used it - the list and the detail header both took
        # `instrument_number` raw and rendered `68756`. So the rule existed and
        # nothing a person looks at obeyed it.
        #
        # CONCATENATED HERE RATHER THAN IN THE BROWSER, deliberately. The
        # alternative is the front end joining `payment_instrument` and
        # `instrument_number` itself, which is an eleventh spelling of the rule
        # in a language where nothing can check it against the other ten - no
        # test can compare a TypeScript expression to a Python function. It
        # would also have to re-implement the `cadCAD` guard (see
        # `payment_reference_from`), and a duplicated guard is the half that
        # gets dropped when someone simplifies the expression.
        #
        # NULL rather than "" when the order has no instrument number, so the
        # front end's `?? fallback` works and a missing reference cannot render
        # as a bare mode or a stray separator.
        "payment_reference" : payment_reference(consignment) or None,
        "opening_or_retirement_date" : consignment.opening_or_retirement_date,
        "exchange_rate" : order_exchange_rate(consignment),
        "rate_booked_on" : order_rate_booked_on(consignment),
        "rate_source" : order_rate_source(consignment),
        "foreign_total" : consignment.foreign_total,
        "pkr_total" : consignment.pkr_total,
        "current_status" : consignment.current_status,
        "effective_date" : consignment.effective_date,
        "remarks" : consignment.remarks,
        "system_remarks" : build_system_remarks(consignment),
        "gd_number" : consignment.gd_number,
        "gd_filing_date" : consignment.gd_filing_date,
        "free_days_allowed" : consignment.free_days_allowed,
        "gate_out_date" : consignment.gate_out_date,
        "demurrage_or_detention_paid" : consignment.demurrage_or_detention_paid,
        "container_detention" : consignment.container_detention,

        # NO `missing_fields` KEY. Imports has no submit rule set any more (see
        # app/imports/helpers.py, "THERE IS NO SUBMIT VALIDATION IN IMPORTS ANY
        # MORE"), so there are no named gaps to publish and nothing on the front
        # end blocks or badges on them. Logistics and trucking still publish
        # theirs; this is the imports-only divergence, deliberately.

        # Cross-module hand-off. NULL = not sent; the list shows a "Sent"
        # column from these and disables each Send button once its own
        # timestamp is set.
        "sent_to_logistics_at" : consignment.sent_to_logistics_at,
        "sent_to_trucking_at" : consignment.sent_to_trucking_at,

        "record_state" : consignment.record_state,
        "is_locked" : consignment.is_locked,

        "is_deleted" : consignment.is_deleted,
        "deleted_at" : consignment.deleted_at,
        "deleted_by_id" : consignment.deleted_by_id if consignment.deleted_by_id else None,
        "deleted_by" : consignment.deleted_by.username if consignment.deleted_by else None
    }

    # The list screen never renders change history — it has its own /history
    # route — so the list route skips it here, and fetch_consignments_page
    # (app/imports/helpers.py) doesn't eager-load it either. Without both
    # halves of that split, accessing consignment.change_history below would
    # lazy-load ONE extra query per row on every page of the list, pulling
    # each consignment's entire unbounded history into a response that never
    # uses it. The detail fetch (fetch_consignment) still eager-loads it, so
    # this stays free there.
    if include_change_history:
        data["change_history"] = serialize_many(consignment.change_history)

        # THE ORDER'S ALLOCATION - what was bought, what is spoken for, and
        # what is still outstanding, per item.
        #
        # ON THE DETAIL PAYLOAD ONLY, and behind the same flag as the change
        # history for the same reason: it reads `group.order_items`, which the
        # list query deliberately does not load. Publishing it from the list
        # would lazy-load one query per row for a panel the list does not draw
        # - which is precisely the N+1 the eager loads beside it just closed.
        #
        # It is what the Step 3 allocation screen and the "pending allocation"
        # highlight are built from (step 8). Outstanding is derived here rather
        # than stored, because a stored copy of `ordered - allocated` is a
        # third number that can disagree with the two it comes from.
        data["allocation"] = allocation_view(consignment.batch_group)

        # THE GROUP FREEZE, so the wizard does not render an editable rate
        # field that 423s on save (design 3.9). The same treatment
        # `missing_fields` used to get, for the same reason: a disabled control
        # and a failed save must not disagree.
        #
        # DETAIL ONLY, in this block, for the reason `allocation` is - it reads
        # `group.batches`, which the list query does not load, so publishing it
        # from the list would be one query per row for a panel the list does
        # not draw.
        #
        # IT PUBLISHES THE ORDER'S FACTS, NOT THE CALLER'S EFFECTIVE SET.
        # `hard` and `admin` are properties of the ORDER; which of them applies
        # is a property of the VIEWER, and the front end already holds
        # `user.isAdmin` (it renders the Reopen button from it). Threading a
        # user through eleven serializer call sites to compute a set union the
        # client can do from data it already has would be the larger change and
        # the more fragile one. What must not move to the browser is the FIELD
        # LISTS, and they do not - they come from helpers.HARD_FROZEN and
        # helpers.ADMIN_FROZEN, in payload-key form so the wizard can match
        # them to its own inputs directly.
        # IMPORTED INSIDE THE FUNCTION, like `item_current_values` above and
        # for the same reason: `helpers` imports this module, so a module-level
        # import here is a cycle.
        from app.imports.helpers import (
            ADMIN_FROZEN, HARD_FROZEN, freezing_batch,
        )

        blocking = freezing_batch(consignment.batch_group)
        data["group_frozen"] = {
            "is_frozen": blocking is not None,
            # Which batch settled the terms - named, because "this order is
            # frozen" without saying why is a dead end for whoever reads it.
            "frozen_by": None if blocking is None else {
                "consignment_id": blocking.id,
                "consignment_number": consignment_number(blocking) or None,
            },
            # Payload keys, not column names: `branch_id`, which the wizard
            # posts, rather than `works_branch_id`, which it has never heard of.
            "hard": sorted(_payload_keys_for(HARD_FROZEN)),
            "admin": sorted(_payload_keys_for(ADMIN_FROZEN)),
        }

    return data


def _payload_keys_for(columns):
    """Group COLUMN names -> the PAYLOAD keys the wizard posts them under.

    One asymmetry, and it is the whole reason this exists: `works_branch_id` is
    posted as `branch_id`. A front end handed the column name would disable an
    input that is not there and leave the real one editable.
    """
    from app.imports.helpers import PAYLOAD_TO_GROUP

    return {key for key, column in PAYLOAD_TO_GROUP.items() if column in columns}

#---------------------------------------------
# A SINGLE DYNAMIC FUNCTION THAT
# CAN SERIALIZE ALL THE MASTER TABLES MODELS
#---------------------------------------------

def serialize_master(master):
    master_dict = (
        {
            column.key : getattr(master, column.key)
            for column in inspect(master).mapper.column_attrs
        }
        if master
        else
        None
    )

    return master_dict

#---------------------------------------------
# SERIALIZE MODELS THAT ARE A COLLECTION
#---------------------------------------------

def serialize_many(models_list):
    serialized_models = []

    for model in models_list:
        serialized_models.append(
            {
                column.key : getattr(model, column.key)
                for column in inspect(model).mapper.column_attrs
            }
        )

    return serialized_models


#----------------------------------
# SHIPMENT LINES, WITH THE DEMAND THEY CAME FROM
#
# `serialize_many` above is MAPPER-DRIVEN: it emits one key per column attribute
# of whatever it is given. That is why it cannot do this on its own — the demand
# dates are not columns of `consignment_items`, they are columns of the ORDER
# LINE above it, and a mapper walk over the shipment line will never see them.
#
# So the two are added explicitly, per line. They are the per-item half of the
# header change: `required_date` also appears on the header payload as the
# earliest across the batch (the delay column needs one sortable number), while
# `requisition_date` appears ONLY here, because nothing wants a batch-level
# version of it.
#----------------------------------

def serialize_items(items):
    """A shipment line and its order line, flattened into one payload row.

    THIS MERGE IS NOT COSMETIC. WITHOUT IT A NORMAL SAVE DESTROYS DATA.

    `serialize_many` walks the MAPPER, so once the thirteen identity, price and
    requisition fields moved to `consignment_order_items` it stopped emitting
    them - no error, just thirteen keys quietly missing from every item. The
    client then posts the draft back as the wizard always does,
    `ConsignmentItemSchema` defaults the absent keys to None, `updated_items`
    sees None against a stored 7650.0000 and calls it a change, and the update
    writes NULL over the price.

    Measured, not imagined: order items 40, 41 and 42 on the split fixture had
    their `unit_price` wiped by exactly this route, which is what made the
    consistency suite report one batch worth 128,172.35 and its sibling 0.

    The client sees ONE item, because that is what an item is to the person
    editing it. Which row each field lives on is the server's business, and
    `item_current_values` is the single definition of that flattening - shared
    with the update diff, so the shape sent out and the shape diffed on the way
    back in cannot drift.
    """
    from app.imports.helpers import item_current_values

    return [item_current_values(item) for item in items]


#----------------------------------
# SERIALIZE CONSIGNMENT HISTORY
#----------------------------------

def serialize_consignment_history(consignment_history):
    return {
        "id":consignment_history.id,
        "consignment_id":consignment_history.consignment_id,
        "change_type":consignment_history.change_type,
        "history":consignment_history.history,
        "changed_by_id":consignment_history.changed_by_id,
        "changed_by":consignment_history.changed_by.username if consignment_history.changed_by else None,
        # When the change was made (TimestampMixin). The history screen orders
        # and dates every card by this, so it has to go out with the row.
        "changed_at":consignment_history.created_at,

        "is_reverted":consignment_history.is_reverted,
        "reverted_by_id":consignment_history.reverted_by_id,
        "reverted_by":consignment_history.reverted_by.username if consignment_history.reverted_by else None,

        "reverted_at":consignment_history.reverted_at,
        "is_revert":consignment_history.is_revert
    }