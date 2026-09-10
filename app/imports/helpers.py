from app.imports.models import (
    Consignment, ConsignmentItem, Payment, ConsignmentChangeHistory,
    ConsignmentBatchGroup, ConsignmentOrderItem,
)
from sqlalchemy import select, func, or_, and_, not_
from sqlalchemy.orm import joinedload, selectinload
from app.imports.serializers import serialize_many
from app.imports.models import ConsignmentChangeHistory, EtaRevisionHistory, StatusUpdateHistory

from app.enums import Status
from app.masters.models import Branch, Item, Supplier
from sqlalchemy import select
from datetime import datetime, timezone, date
from sqlalchemy.inspection import inspect
from decimal import Decimal

#-------------------------------------
# THE SIX-STAGE PIPELINE
#
# The list view rolls the eleven statuses into six stages. Kept as stored
# Status values so a stage filter maps straight to an IN clause. "Arrived at
# works" is the one closed status, hidden from the list by default.
#-------------------------------------

STAGE_GROUPS = {
    "Pre-shipment": [Status.TT_LC_IN_PROCESS.value],
    "Production": [Status.UNDER_PRODUCTION.value, Status.READY_AWAITING_SAILING.value],
    "In transit": [Status.IN_TRANSIT.value],
    "Clearance": [
        Status.ARRIVED_AT_PORT.value,
        Status.UNDER_CUSTOM_CLEARANCE.value,
        Status.UNDER_EXAMINATION.value,
        Status.UNDER_ASSESSMENT.value,
        Status.UNDER_DE_STUFFING.value,
    ],
    "Inbound": [Status.ARRIVED_AT_QFL.value, Status.ON_ROAD.value],
    # Both terminal states live here so the strip can reach a cancelled order.
    # Only ARRIVED_AT_WORKS locks a record, though — see is_closed below.
    "Closed": [Status.ARRIVED_AT_WORKS.value, Status.ORDER_CANCELLED.value],
}

CLOSED_STATUS_VALUE = Status.ARRIVED_AT_WORKS.value


def coerce_value(model, field, value):
    if value is None:
        return value
    col_type = model.__table__.columns[field].type.__class__.__name__
    if col_type == "Date" and isinstance(value, str):
        return date.fromisoformat(value)
    if col_type == "DateTime" and isinstance(value, str):
        return datetime.fromisoformat(value)
    if col_type == "Numeric" and not isinstance(value, Decimal):
        return Decimal(str(value))
    return value


#-------------------------------------------------
# CONVERTING AN OBJECT FROM SCHEMA
# THAT CAN BE ENTERED
# INTO DATABSE TABLE USING SQL ALCHEMY ORM
#-------------------------------------------------
def create_consignment_object(consignment_data, user):
    consignment_data_dict = consignment_data.model_dump(exclude_none=True, exclude={"items", "payments"}) #--> Convert pydantic schema to python dictionary

    consignment_data_dict["created_by_id"] = user.id

    consignment = Consignment(**consignment_data_dict)
    return consignment


#--------------------------------------
# CREATING AN OBJECT FOR 
# CONSIGNMENT ITEM
#--------------------------------------

def create_consignment_item_object(consignment_data):
    # Items are coming as a list in data so
    # create object for each item in the
    # list and return a list of objects

    consignment_items = consignment_data.items

    objects = []

    for item in consignment_items:
        item_dict = item.model_dump() #--> Convert pydantic schema to python dictionary
        objects.append(
            ConsignmentItem(**item_dict)
        )

    return objects


#--------------------------------------
# CREATING AN OBJECT FOR 
# PAYMENT
#--------------------------------------

def create_payment_object(consignment_data):
    # Payments are coming as a list in data so
    # create object for each payment in the
    # list and return a list of objects

    payments = consignment_data.payments

    objects = []

    for payment in payments:
        payment_dict = payment.model_dump()#--> Convert pydantic schema to python dictionary
        objects.append(
            Payment(**payment_dict)
        )

    return objects

#-------------------------------------
# FETCH CONSIGNMENT FROM DB BASED ON
# ON ID (SPECIFIC CONSIGNMENT)
#-------------------------------------

def fetch_consignment(db, consignment_id):
    query = select(Consignment).where(
        Consignment.id == consignment_id
    ).options(
        joinedload(Consignment.branch),
        joinedload(Consignment.supplier),
        joinedload(Consignment.loading_port),
        joinedload(Consignment.delivery_port),
        joinedload(Consignment.clearing_agent),

        selectinload(Consignment.items),
        selectinload(Consignment.payments),
        selectinload(Consignment.status_updates),
        selectinload(Consignment.eta_revisions),
        selectinload(Consignment.change_history),

        joinedload(Consignment.created_by),
        joinedload(Consignment.deleted_by)
    )
    

    return db.execute(query).scalar_one_or_none()


#-------------------------------------
# FETCH ONE PAGE OF CONSIGNMENTS, FILTERED
#
# The list screen filters and pages, so the filters are applied in SQL and
# only one page is loaded, rather than pulling every consignment and cutting
# it down in python. The total count is worked out with the same filters so
# the caller can say how many pages there are. requisition type lives on the
# item line, so it is filtered through a sub query on the items.
#-------------------------------------

ORDER_CANCELLED_VALUE = Status.ORDER_CANCELLED.value


def fetch_consignments_page(db, include_deleted, include_closed, status, stage,
                            branch_id, supplier_id, requisition_type,
                            drafts_only, etd_from, etd_to, q, page, page_size,
                            sent_only=False):
    # status, branch_id, supplier_id and requisition_type are lists (the list
    # screen filters are multi-select), so each is an IN filter, not an equals.
    conditions = []

    if not include_deleted:
        conditions.append(Consignment.is_deleted == False)

    # "Closed" is the STATUS ALONE — the same one-part test helpers.is_closed
    # now applies, spelled in SQL. "Order Cancelled" is the other terminal
    # state and is treated as closed here too.
    #
    # This used to read `status == CLOSED AND is_locked == True`, the two-part
    # test written out by hand. It has to change WITH is_closed, not after it:
    # with the lock no longer written by /submit, that condition would match
    # almost nothing, and `include_closed=False` — the DEFAULT — would quietly
    # stop hiding closed consignments from the list. Not a crash; "closed
    # consignments started showing up in the default list" a week later.
    closed_statuses = (CLOSED_STATUS_VALUE, ORDER_CANCELLED_VALUE)
    is_truly_closed = Consignment.current_status.in_(closed_statuses)

    # A stage is a group of statuses (the six-stage pipeline strip); it narrows
    # to that group's statuses. The Closed stage specifically means truly
    # closed records, not just any record sitting at a terminal status.
    if stage and stage != "all":
        if stage == "Closed":
            conditions.append(is_truly_closed)
        else:
            stage_statuses = STAGE_GROUPS.get(stage)
            if stage_statuses:
                conditions.append(Consignment.current_status.in_(stage_statuses))

    if status:
        conditions.append(Consignment.current_status.in_(status))

    # Closed records are hidden by default, unless the caller asks to include
    # them, is looking at the Closed stage, or explicitly filters to that
    # status. Mirrors the list view's own rule.
    if (
        not include_closed and stage != "Closed"
        and not (status and (CLOSED_STATUS_VALUE in status or ORDER_CANCELLED_VALUE in status))
    ):
        conditions.append(not_(is_truly_closed))

    if branch_id:
        conditions.append(Consignment.branch_id.in_(branch_id))

    if supplier_id:
        conditions.append(Consignment.supplier_id.in_(supplier_id))

    if requisition_type:
        conditions.append(
            Consignment.id.in_(
                select(ConsignmentItem.consignment_id).where(
                    ConsignmentItem.requisition_type.in_(requisition_type)
                )
            )
        )

    # "Drafts only" — records nobody has marked finished.
    #
    # RENAMED FROM `missing_only`, and only the name changed: it always filtered
    # on record_state and never on the rule set. But "Missing information only"
    # was an honest label only while a record could leave draft solely by
    # passing that rule set. It no longer can, so a draft says nothing about
    # completeness and the old name promised something the filter cannot
    # deliver. The question it answers — "show me what nobody has marked
    # finished" — is still a real one, which is why this is a rename and not a
    # removal.
    if drafts_only:
        conditions.append(Consignment.record_state == "draft")

    # The "Forwarded" view: consignments handed to logistics and/or trucking.
    # Either timestamp counts — the two hand-offs are independent.
    if sent_only:
        conditions.append(
            or_(
                Consignment.sent_to_logistics_at.is_not(None),
                Consignment.sent_to_trucking_at.is_not(None),
            )
        )

    if etd_from:
        conditions.append(Consignment.etd >= etd_from)

    if etd_to:
        conditions.append(Consignment.etd <= etd_to)

    # Free-text search across everything the list screen shows as identifying:
    # the id, the instrument/GD numbers, origin, the two master names, and the
    # item lines (name / code / reference). Matching only the header fields
    # made searching for a supplier or an item — the two most obvious things to
    # type — silently return nothing.
    if q:
        needle = q.strip()
        pattern = "%" + needle + "%"

        searches = [
            Consignment.origin.ilike(pattern),
            Consignment.gd_number.ilike(pattern),
            Consignment.instrument_number.ilike(pattern),
            Consignment.works.ilike(pattern),
            Consignment.supplier.has(Supplier.name.ilike(pattern)),
            Consignment.branch.has(Branch.name.ilike(pattern)),
            Consignment.items.any(
                (ConsignmentItem.is_deleted == False) &  # noqa: E712
                or_(
                    ConsignmentItem.item_name.ilike(pattern),
                    ConsignmentItem.item_code.ilike(pattern),
                    ConsignmentItem.reference_number.ilike(pattern),
                )
            ),
        ]

        # Typing a bare number is looking for that consignment id.
        if needle.isdigit():
            searches.append(Consignment.id == int(needle))

        conditions.append(or_(*searches))

    # how many match, for the page count
    total = db.execute(
        select(func.count(Consignment.id)).where(*conditions)
    ).scalar()

    # the page itself, newest first
    query = select(Consignment).where(*conditions).options(
        joinedload(Consignment.branch),
        joinedload(Consignment.supplier),
        joinedload(Consignment.loading_port),
        joinedload(Consignment.delivery_port),
        joinedload(Consignment.clearing_agent),

        selectinload(Consignment.items),
        selectinload(Consignment.payments),
        selectinload(Consignment.status_updates),
        selectinload(Consignment.eta_revisions),

        joinedload(Consignment.created_by),
        joinedload(Consignment.deleted_by)
    ).order_by(
        Consignment.id.desc()
    ).limit(page_size).offset((page - 1) * page_size)

    rows = db.execute(query).scalars().all()

    return rows, total


#----------------------------------------
# ONE PAGE OF CHANGE HISTORY, NEWEST FIRST
#
# Mirrors fetch_consignments_page's shape: filter conditions built once and
# reused for both the count and the page itself, so they can never disagree.
# Ordered by id (not just created_at) so paging is deterministic even when two
# rows share a timestamp — created_at alone was not a stable sort key.
#----------------------------------------

def fetch_all_consignment_history(db, include_reverted, consignment_id, page=1, page_size=20):
    conditions = [ConsignmentChangeHistory.consignment_id == consignment_id]

    if not include_reverted:
        conditions.append(ConsignmentChangeHistory.is_reverted == False)

    total = db.execute(
        select(func.count(ConsignmentChangeHistory.id)).where(*conditions)
    ).scalar()

    query = select(ConsignmentChangeHistory).where(*conditions).options(
        joinedload(ConsignmentChangeHistory.consignment),
        joinedload(ConsignmentChangeHistory.changed_by),
        joinedload(ConsignmentChangeHistory.reverted_by)
    ).order_by(
        ConsignmentChangeHistory.id.desc()
    ).limit(page_size).offset((page - 1) * page_size)

    rows = db.execute(query).scalars().all()

    return rows, total

def fetch_latest_consignment_history(db, consignment_id):
    query = select(ConsignmentChangeHistory).where(
            ConsignmentChangeHistory.is_reverted == False
    )
        
    query = query.where(
        ConsignmentChangeHistory.consignment_id == consignment_id
    ).options(
        joinedload(ConsignmentChangeHistory.consignment),
        joinedload(ConsignmentChangeHistory.changed_by),
        joinedload(ConsignmentChangeHistory.reverted_by)
    ).order_by(ConsignmentChangeHistory.created_at.desc())
    

    return db.execute(query).scalars().first()


#----------------------------------------
# FETCH CONSIGNMENT HISTORY BY ID
# FROM DB (SPECIFIC HISTORY)
#----------------------------------------

def fetch_consignment_history(db, consignment_id, history_id):
    query = select(ConsignmentChangeHistory).where(
        ConsignmentChangeHistory.consignment_id == consignment_id
    ).where(
        ConsignmentChangeHistory.id == history_id
    ).options(
        joinedload(ConsignmentChangeHistory.consignment),
        joinedload(ConsignmentChangeHistory.changed_by),
        joinedload(ConsignmentChangeHistory.reverted_by)
    ) 

    return db.execute(query).scalar_one_or_none()


#---------------------------------------
# GET ALL THE FIELDS THAT ARE TO BE
# UPDATED IN THE ALREADY CREATED
# CONSIGNMENT
#---------------------------------------

def updated_fields(consignment, update_consignment_data, db):
    updation_dict = {} #--> will contain which field to update and
    #its old and new value

    fields_to_update = update_consignment_data.model_dump(exclude_none=True, exclude={"items", "payments", "consignment_id"}) #--> exclude fields which are none because it means user did not update them

    columns = {c.key for c in Consignment.__mapper__.column_attrs}

    for field, new_value in fields_to_update.items():
        if field not in columns:          
            continue

        old_value = getattr(consignment, field)

        if new_value == old_value:
            continue

        updation_dict[field] = {
            "old_value" : old_value,
            "new_value" : new_value
        }

    return updation_dict

#----------------------------------
# FINDING NEW ITEMS AND PAYMENTS
# TO ADD
#----------------------------------

def new_items_to_add(consignment, update_consignment_data):
    new_items = []
    items_in_updated_data = update_consignment_data.items
    items_in_consignment = consignment.items

    consignment_items_ids = [item.id for item in items_in_consignment]

    for item in items_in_updated_data:
        if item.id not in consignment_items_ids:
            new_items.append(item)

    return new_items

def new_payments_to_add(update_consignment_data):
    new_payments = []
    payments_in_updated_data = update_consignment_data.payments

    for payment in payments_in_updated_data:
        if payment.id is None: #--> since payment is new so no id should come
            new_payments.append(payment)

    return new_payments


#--------------------------------------
# DELETING ITEMS AND PAYMENTS FROM
# DATABASE THAT ARE NOT COMING
# IN REQUEST BODY (ASSIMING USER 
# HAS DELETED THEM)
#--------------------------------------

def delete_missing(consignment, present_ids, id_column,db, model):
    query = select(model).where(
            model.consignment_id == consignment.id
    ).where(
        model.is_deleted == False
    )

    if present_ids:
        query = query.where(
            id_column.not_in(present_ids)
        )

    rows_to_delete = db.execute(query).scalars().all()

    for row in rows_to_delete:
        row.is_deleted = True
        row.deleted_at = datetime.now(timezone.utc)

    return rows_to_delete
    


def updated_items(consignment, update_consignment_data, db):
    updated_items_list = []
    items_in_updated_data = update_consignment_data.items
    items_in_consignment = consignment.items

    serialized_consignment_items = serialize_many(items_in_consignment)

    serialized_dict = {item["id"]: item for item in serialized_consignment_items}

    for item in items_in_updated_data:
        updation_dict = {}
        consignment_item = None
        item_dict = item.model_dump()
        consignment_item = serialized_dict.get(item_dict["id"])

        if consignment_item is not None:

            for field in list(item_dict.keys()):
                if item_dict[field] != consignment_item[field]:
                
                    updation_dict[field] = {
                        "old_value" : consignment_item[field],
                        "new_value" : item_dict[field]
                    }

        if updation_dict:
            updation_dict["id"] = item_dict["id"]
            updated_items_list.append(updation_dict)

    return updated_items_list


def updated_payments(consignment, update_consignment_data, db):
    updated_payments_list = []
    payments_in_updated_data = update_consignment_data.payments
    payments_in_consignment = consignment.payments

    serialized_consignment_payments = serialize_many(payments_in_consignment)

    serialized_dict = {payment["id"]: payment for payment in serialized_consignment_payments}

    for payment in payments_in_updated_data:
        updation_dict = {}
        consignment_payment = None

        payment_dict = payment.model_dump()

        if payment_dict["id"] is None:
            continue

        consignment_payment = serialized_dict.get(payment_dict["id"])      

        if consignment_payment is not None:

            for field in list(payment_dict.keys()):
                if payment_dict[field] != consignment_payment[field]:
                
                    updation_dict[field] = {
                        "old_value" : consignment_payment[field],
                        "new_value" : payment_dict[field]
                    }

        if updation_dict:
            updation_dict["id"] = payment_dict["id"]
            updated_payments_list.append(updation_dict)

    return updated_payments_list


#------------------------------------
# APPLY ALL THE UPDATES
#------------------------------------

def apply_updates(updation_dict, consignment):

    for field, change_data in updation_dict.items():
        # An item or payment update dict also carries a plain "id" so the row
        # can be matched. Skip anything that is not an {old_value, new_value}
        # change, so the id is left alone rather than popped, which would also
        # strip it out of the copy already stored in the change history and
        # break reverting that line's fields.
        if not isinstance(change_data, dict) or "new_value" not in change_data:
            continue

        setattr(consignment, field, change_data["new_value"])


#------------------------------------
# ADD UPDATES IN CONSIGNMENT CHANGE
# HISTORY TO KEEP TRACK
#------------------------------------

def add_in_consignment_change_history(
        updation_dict, 
        new_items_added,
        new_payments_added,
        deleted_items,
        deleted_payments,
        item_updates,
        payment_updates,
        consignment,
        user,
        db
):

    serialized_deleted_items = serialize_many(deleted_items)

    serialized_deleted_payments = serialize_many(deleted_payments)

    updates_history = {
        "fields" : updation_dict, 
        "items" : item_updates, 
        "payments" : payment_updates,
        "new_items": new_items_added,
        "new_payments" : new_payments_added,
        "deleted_items" : serialized_deleted_items,
        "deleted_payments" : serialized_deleted_payments 
    }

    change_history = ConsignmentChangeHistory(
        consignment_id = consignment.id,
        change_type = "update",
        history = updates_history,
        changed_by_id = user.id,

    )

    db.add(change_history)
    return change_history


#-------------------------------
# IF ETA CHANGES, ADD NEW AND 
# OLD ETA IN REVISION HISTORY
# TO KEEP TRACK OF ALL ETA 
# CHANGES
#-------------------------------

def create_eta_object(updation_dict, consignment, user, eta_type):
    eta_revision = EtaRevisionHistory(
        consignment_id = consignment.id,
        eta_type = eta_type,
        previous_eta = updation_dict.get(eta_type, {}).get("old_value"),
        new_eta = updation_dict.get(eta_type, {}).get("new_value"),
        cause_of_revision = updation_dict.get("cause_of_revision", {}).get("new_value"),
        user_id = user.id
    )

    return eta_revision
    
def add_in_eta_revision_history(updation_dict, consignment, user, db):
    if updation_dict.get("eta"):
        eta_revision = create_eta_object(updation_dict, consignment, user, "eta")
        db.add(eta_revision)

    if updation_dict.get("eta_works"):
        eta_revision = create_eta_object(updation_dict, consignment, user, "eta_works")
        db.add(eta_revision)




#----------------------------------
# IF STATUS CHANGES, ADD NEW AND 
# OLD STATUS IN STATUS CHANGE
# HISTORY TO KEEP TRACK OF ALL  
# STAUSES
#----------------------------------

def add_in_status_change_history(updation_dict, consignment, user, db):
    if updation_dict.get("current_status"):

        # effective_date is only in updation_dict when it differs from what's
        # already stored — on same-day status changes the frontend's "today"
        # matches the existing value and gets dropped from the diff, so this
        # falls back to today rather than refusing the update (mirrors
        # logistics' add_in_status_change_history).
        effective_date = updation_dict.get("effective_date", {}).get("new_value") or date.today()

        status_change = StatusUpdateHistory(
            consignment_id = consignment.id,
            previous_status = updation_dict.get("current_status", {}).get("old_value"),
            new_status = updation_dict.get("current_status", {}).get("new_value"),
            remarks = updation_dict.get("remarks", {}).get("new_value"),
            effective_date = effective_date,
            user_id = user.id
        )

        db.add(status_change)
        

#---------------------------------
# HELPERS REQUIRED FOR REVERTING
# UPDATES
#---------------------------------

def revert(consignment_history, consignment, db):
    history = consignment_history.history
    fields = history["fields"]
    items_updates = history["items"]
    payments_updates = history["payments"]
    new_items = history["new_items"]
    new_payments = history["new_payments"]
    deleted_items = history["deleted_items"]
    deleted_payments = history["deleted_payments"]

    # Reverting local fields
    revert_local_fields(consignment, fields)

    # Deletig new items added in update
    add_or_delete(new_items, ConsignmentItem, consignment.id, ConsignmentItem.id, db, delete=True)

    # Deleting new payments added in update
    add_or_delete(new_payments, Payment, consignment.id, Payment.id, db, delete=True)

    # Adding deleted items back
    add_or_delete(deleted_items, ConsignmentItem, consignment.id, ConsignmentItem.id, db, delete=False)

    # Adding deleted payments back
    add_or_delete(deleted_payments, Payment, consignment.id, Payment.id, db, delete=False)

    # Reverting already existing items updates
    revert_old_values(items_updates, ConsignmentItem, consignment.id, ConsignmentItem.id, db)

    # Reverting already existing payments updates
    revert_old_values(payments_updates, Payment, consignment.id, Payment.id, db)


def revert_local_fields(consignment, fields):
    consignment_columns = inspect(consignment).mapper.column_attrs
    for column in consignment_columns:
        change = fields.get(column.key)
        if isinstance(change, dict) and "old_value" in change:
            old_value = coerce_value(Consignment, column.key, change["old_value"])
            setattr(consignment, column.key, old_value)

    # A HISTORY KEY THAT MATCHES NO ATTRIBUTE IS A DEFECT, AND MUST NOT BE
    # SILENT.
    #
    # The loop above is driven by the MAPPER, not by the history: it walks the
    # model's columns and picks up whichever of them the stored history mentions.
    # A key the model does NOT have is therefore never looked at, and the revert
    # reports success having restored nothing for it. In a feature whose entire
    # purpose is undo, half-succeeding quietly is worse than failing.
    #
    # This matters now because fields are about to MOVE. Once the shared values
    # (supplier, currency, exchange rate...) live on the batch group and their
    # attributes come off Consignment, every history row written before that
    # change still carries them under these keys — and every one would be
    # skipped without a word. Routing those keys to the group is a later change;
    # this is the part that makes the boundary visible instead of assumed, and
    # it goes in FIRST so the routing can be seen to be needed rather than
    # taken on trust.
    known = {column.key for column in consignment_columns}
    unknown = sorted(
        key for key, change in fields.items()
        if isinstance(change, dict) and "old_value" in change and key not in known
    )
    if unknown:
        raise ValueError(
            "Change history for consignment "
            f"{getattr(consignment, 'id', '?')} holds field(s) that no longer "
            f"exist on Consignment: {', '.join(unknown)}. Reverting would have "
            "restored the rest and silently dropped these."
        )


def add_or_delete(data, model, consignment_id, id_column, db, delete = False):
    for data in data:
        data_id = data.get("id")
        if data_id:
            consignment_data = db.execute(
                    select(model).where(
                        model.consignment_id == consignment_id
                    ).where(
                        id_column == data_id
                )
            ).scalar_one_or_none()
            if consignment_data:
                if delete:
                    consignment_data.is_deleted = True
                    consignment_data.deleted_at = datetime.now(timezone.utc)
                else:  
                    consignment_data.is_deleted = False
                    consignment_data.deleted_at = None


def revert_old_values(updated_data, model, consignment_id, id_column, db):
    for data in updated_data:
        data_id = data.get("id")
        if data_id:
            consignment_data = db.execute(
                    select(model).where(
                        model.consignment_id == consignment_id
                    ).where(
                        id_column == data_id
                )
            ).scalar_one_or_none()
            if consignment_data:
                consignment_data_columns = inspect(consignment_data).mapper.column_attrs
                for column in consignment_data_columns:
                    change = data.get(column.key)
                    if isinstance(change, dict) and "old_value" in change:   # <-- skips "id" (a bare int)
                        old_value = coerce_value(model, column.key, change["old_value"])  # <-- see #6
                        setattr(consignment_data, column.key, old_value)


#---------------------------------------
# THE CLOSED LOCK
#
# A consignment closes when its status reaches "Arrived at works". That is the
# WHOLE test — being submitted is no longer half of it.
#
# "Arrived at works" is a statement about the world: the goods are at the
# factory. Completion follows from that fact, not from somebody remembering to
# press Submit afterwards. Under the old two-part test a consignment whose goods
# had demonstrably arrived stayed editable until an administrative gesture was
# made, which put the lock on the gesture rather than on the event it is
# supposed to represent.
#
# Submit now means only "I am finished editing this" and sets `record_state`
# alone — it locks nothing, so there is nothing irreversible about it and
# nothing to warn about at submit time.
#
# THE LOCK IS WRITTEN BY THE UPDATE ROUTE, on the transition into this status
# (update_consignment.py), and nowhere else. It used to be written by /submit
# and nowhere else, so this is not a rule that moved on its own — deleting the
# write from one place without adding it to the other removes the closed lock
# from the system entirely, silently, leaving is_locked false for ever.
#
# While closed the record cannot be edited by anyone until an admin reopens it.
# The check lives here so the one condition that means "closed" is written once.
#---------------------------------------

def is_closed(consignment):
    return consignment.current_status == Status.ARRIVED_AT_WORKS.value


#---------------------------------------
# THERE IS NO SUBMIT VALIDATION IN IMPORTS ANY MORE
#
# `submission_errors()`, `REQUISITION_REQUIRED` and `ITEM_CODE_NOT_REQUIRED_FOR`
# used to live here. All three are deleted, along with the 422 path in
# /submit, the `missing_fields` key in the serializer and the three front-end
# mirrors of the same rules. `POST /{id}/submit` now always succeeds, subject
# only to the closed lock.
#
# WHY, since deleting a rule set is the kind of thing that looks like a
# regression later: data quality moves to the INPUT layer — dropdowns, masters
# and required-at-entry — rather than being asserted at a gate the user reaches
# after the typing is done. The rule set encoded the same requirements three
# times (here, the wizard's zod submit schema, and the requirements banner) in
# two languages, and the three could and did disagree. There is nothing left to
# keep in agreement.
#
# WHAT IS LOST, stated rather than discovered as an absence: nothing replaces
# the "N fields missing" tag, the row highlight, the disabled Submit or the
# pending-information banner. If quality is enforced at entry then a record
# cannot be incomplete in the ways those surfaces reported, and a tag that can
# never fire is worse than no tag.
#
# THIS IS AN IMPORTS-ONLY DIVERGENCE. app/logistics/helpers.py and
# app/trucking/helpers.py still have their own submission_errors() and still
# block submit; the shared SubmitRequirements component stays for them. A user
# working across all three modules will find imports behaves differently. That
# is a cost of the decision, deliberately accepted, not an oversight.
#
# `record_state` survives, and means something weaker than it did: "a user has
# marked this record finished. Nothing verifies that claim." It drives exactly
# one thing, the drafts_only list filter, and is otherwise informational.
#---------------------------------------


#---------------------------------------
# THE ITEM MASTER IS THE AUTHORITY ON NAME AND SPECIFICATION
#
# A line whose item_code matches an ACTIVE master item takes that item's name
# (and specification) FROM THE MASTER, overwriting whatever the payload sent.
# One code cannot describe two different things, or item-wise reporting stops
# agreeing with itself — which is the same reason free text is banned for
# anything reported on.
#
# The wizard also locks those two inputs the moment a code matches
# (Step1Consignment's ItemDetailFields), but that is a convenience for the
# person typing. THIS is the guarantee: a hand-rolled request, an older
# client or a replayed payload all come through here.
#
# Run on every WRITE (create and update). Same call sites as recompute_derived.
#
# A code matching nothing is left completely alone. That covers the "Others"
# requisition type, where a line often has no code to give because it is not
# drawn from the item master at all, and the loaded rows carrying a generated
# IMP-<hash> code the catalogue never held (loading/imports/item_codes.py).
# Both are legitimately free text.
#
# SPECIFICATION IS ONLY OVERWRITTEN WHERE THE MASTER STATES ONE. Writing an
# empty value over a specification the operator typed, to agree with a master
# that does not have one, would destroy information to enforce nothing.
#
# Interaction with rule 12 ("the line stores its own copy; changing the master
# later never rewrites past consignments"): the line still holds its own
# snapshot and nothing rewrites history in place. But a line RE-SAVED after
# its master changed does now pick up the new values, because this runs on
# every write. That is the intended trade for codes and names never
# disagreeing.
#---------------------------------------

def apply_item_master_values(consignment, db):
    codes = {
        item.item_code.strip().lower()
        for item in consignment.items
        if not item.is_deleted and item.item_code and item.item_code.strip()
    }

    if not codes:
        return

    # One query for the whole consignment rather than one per line.
    rows = db.execute(
        select(Item)
        .where(Item.is_active == True)
        .where(func.lower(Item.item_code).in_(codes))
    ).scalars().all()

    by_code = {row.item_code.strip().lower(): row for row in rows}

    for item in consignment.items:
        if item.is_deleted or not item.item_code or not item.item_code.strip():
            continue

        master = by_code.get(item.item_code.strip().lower())

        if master is None:
            continue

        item.item_name = master.name

        if master.default_specification:
            item.specification = master.default_specification


#---------------------------------------
# STORED COMPUTED VALUES
#
# Calculated values are never keyed in, but the money totals are STORED (not
# recomputed on read) so a later rate change or edit can never restate what a
# printed report showed. Recomputed on every save from the fields it derives
# from — line quantities x unit prices for the foreign total, the booked rate
# for the PKR total, and ALC - ELC per line for variance.
#---------------------------------------

def recompute_derived(consignment):
    active_items = [item for item in consignment.items if not item.is_deleted]

    foreign_total = Decimal("0")
    for item in active_items:
        if item.quantity is not None and item.unit_price is not None:
            foreign_total += item.quantity * item.unit_price

    consignment.foreign_total = foreign_total

    rate = consignment.exchange_rate
    consignment.pkr_total = (foreign_total * rate) if rate is not None else None

    for item in active_items:
        if item.elc is not None and item.alc is not None:
            variance = item.alc - item.elc
            item.variance_absolute = variance
            item.variance_percentage = (variance / item.elc * 100) if item.elc else None
        else:
            item.variance_absolute = None
            item.variance_percentage = None


#---------------------------------------
# ELC / ALC AUDIT
#
# Stamp who entered each landed-cost figure and when, on the line, only for
# the figure that actually changed. Called from create (a figure supplied at
# entry) and update (a figure that changed).
#---------------------------------------

def stamp_landed_cost_audit(item, user, stamp_elc, stamp_alc):
    now = datetime.now(timezone.utc)
    if stamp_elc:
        item.elc_updated_by_id = user.id
        item.elc_updated_at = now
    if stamp_alc:
        item.alc_updated_by_id = user.id
        item.alc_updated_at = now


#---------------------------------------
# HOW A CONSIGNMENT IS NAMED IN A MESSAGE
#
# The payment instrument number is what the list, the reports and the
# notifications all show as the consignment's reference; IMP-{id} is the
# fallback for a draft that has not been given one yet. One definition,
# because a notification naming a consignment differently from the screen the
# reader then opens is a notification they cannot act on.
#---------------------------------------

def consignment_reference(consignment):
    return consignment.instrument_number or f"IMP-{consignment.id}"



#---------------------------------------
# THE ORDER ABOVE A CONSIGNMENT
#
# A consignment is a BATCH of an order. Every consignment created here is a
# group of ONE - it founds its own group and is batch 1 of it - which is exactly
# the shape the migration left every pre-existing consignment in, and the shape
# the Excel loader writes. Splitting an order across several batches, allocating
# quantities between them and the numbering suffix are a later phase; nothing
# here does any of that.
#
# WHY THIS IS NOT OPTIONAL. `consignments.batch_group_id` and
# `consignment_items.order_item_id` are both NOT NULL, so without these helpers
# a create is a 500 rather than a missing feature.
#
# THE INSERT ORDER IS THE WHOLE DIFFICULTY, and it is why `new_batch_group`
# looks the way it does. consignments and consignment_batch_groups reference
# each other with NOT NULL columns, so neither row can be written first: the
# group needs a consignment that does not exist yet and the consignment needs a
# group that does not exist yet. Verified against the database in all three
# orderings, all three fail. The FK on `consignments.batch_group_id` is
# therefore DEFERRABLE INITIALLY DEFERRED, and the sequence below is the one
# that works:
#
#   1. take the group's id from its sequence, before either row exists
#   2. INSERT the consignment carrying that id - the FK is deferred, so
#      pointing at a group that is not there yet is allowed until COMMIT
#   3. INSERT the group, now that the consignment id it must reference exists
#   4. everything else (order items, lines) goes after, with no cycle left
#
# COMMIT then checks the deferred constraint, with both halves present. A
# transaction that leaves either half missing still fails - deferring moves the
# check, it does not remove it.
#---------------------------------------

# The values that belong to the ORDER rather than to a shipment, copied onto the
# group. `branch_id` becomes `works_branch_id`. Identical to the list the
# migration copies, deliberately: the two must not be able to disagree about
# what is shared.
GROUP_SHARED_FIELDS = [
    "supplier_id",
    "origin",
    "currency",
    "consignment_type",
    "incoterm",
    "payment_instrument",
    "instrument_number",
    "exchange_rate",
    "rate_booked_on",
    "rate_source",
]


def new_batch_group(consignment, user, db):
    """Create the order this consignment is the first batch of, and link them.

    Flushes twice, in the only order the constraints allow - see the block
    comment above. Returns the group.
    """
    group_id = db.execute(
        select(func.nextval("consignment_batch_groups_id_seq"))
    ).scalar()

    consignment.batch_group_id = group_id
    consignment.batch_sequence = 1

    # The consignment goes in FIRST, pointing at a group that does not exist
    # yet. Only the deferred foreign key makes this legal.
    db.add(consignment)
    db.flush()

    group = ConsignmentBatchGroup(
        id=group_id,
        founding_consignment_id=consignment.id,
        batches_ever=1,
        works_branch_id=consignment.branch_id,
        created_by_id=user.id if user is not None else None,
        **{field: getattr(consignment, field) for field in GROUP_SHARED_FIELDS},
    )

    db.add(group)
    db.flush()

    return group


#---------------------------------------
# THE ORDER LINE ABOVE A SHIPMENT LINE
#
# While a group holds ONE batch, "what was ordered" and "what this shipment
# carries" are the same quantity, so the order item mirrors its line. That is
# what the migration back-filled and what the loader writes.
#
# It is mirrored on every write rather than snapshotted at creation, because
# `allocated_quantity` is the denormalised sum the over-allocation CHECK is
# built on. Left unmirrored, editing a line's quantity would leave that column
# describing a quantity the line no longer has - the exact drift `post_load`'s
# "Allocation totals" check exists to catch.
#
# When allocation arrives, ordered_quantity stops following the line and starts
# being entered against the order; this mirroring is what that replaces.
#---------------------------------------

# Copied straight off the line: identity, price and the requisition details.
ORDER_ITEM_LINE_FIELDS = [
    "item_id",
    "item_code",
    "item_name",
    "placeholder_name",
    "specification",
    "hs_code",
    "unit_of_measurement",
    "unit_price",
    "requisition_type",
    "reference_number",
    "job_number",
    "mo_number",
    "description",
]

# Taken from the CONSIGNMENT: header columns today, per-item columns once the
# requirements land. The header value is the true one for every line under it,
# which is the same reasoning the migration back-fills them on.
ORDER_ITEM_HEADER_FIELDS = {
    "branch_id": "branch_id",
    "requisition_date": "requisition_date",
    "required_date": "required_date",
}


def sync_order_item_from_line(item, consignment):
    """Mirror a shipment line onto the order line above it.

    Creates the order item if the line has none, which is the case for every
    line on a create and every line added by an update.
    """
    order_item = item.order_item

    if order_item is None:
        order_item = ConsignmentOrderItem(batch_group_id=consignment.batch_group_id)
        item.order_item = order_item

    for field in ORDER_ITEM_LINE_FIELDS:
        setattr(order_item, field, getattr(item, field, None))

    for target, source in ORDER_ITEM_HEADER_FIELDS.items():
        setattr(order_item, target, getattr(consignment, source, None))

    # NOT NULL, and a line can legitimately carry no quantity at draft. A line
    # that orders nothing orders zero - the same COALESCE the migration and the
    # loader apply, for the same reason.
    quantity = item.quantity if item.quantity is not None else Decimal("0")
    order_item.ordered_quantity = quantity
    order_item.allocated_quantity = quantity

    # The pair is one thing while a group holds one batch, so it is deleted as
    # one. Without this the order item outlives its line and
    # `allocated_quantity` stops matching the lines it is the sum of.
    order_item.is_deleted = item.is_deleted
    order_item.deleted_at = item.deleted_at

    return order_item


def sync_order_items(consignment, db):
    """Mirror every line of a consignment onto its order line.

    RUNS WITH AUTOFLUSH OFF, and that is not a precaution — without it this
    function cannot work at all.

    Attaching a line to its order line writes a relationship, and SQLAlchemy
    reads the attribute's previous value before it writes the new one. On a
    consignment that has already been flushed — which it has, because the group
    could not be written otherwise — that read is a lazy load, a lazy load
    emits a SELECT, and a SELECT autoflushes the session first. The session at
    that moment holds lines whose `order_item_id` is still NULL, so the
    autoflush inserts them and the NOT NULL constraint rejects the lot:

        NotNullViolation: null value in column "order_item_id"
        (raised as a result of Query-invoked autoflush)

    Deferring the flush to the end of this loop means every line already has
    its order line by the time anything is written, and SQLAlchemy inserts the
    order items first because the lines depend on them.

    The suppression lives HERE rather than in the routes so that a future caller
    cannot forget it. It is the helper that creates the transient state, so it
    is the helper that has to hold it off the database.
    """
    with db.no_autoflush:
        for item in consignment.items:
            sync_order_item_from_line(item, consignment)
