from fastapi import HTTPException
from app.imports.models import Consignment, ConsignmentItem, Payment, ConsignmentChangeHistory
from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload, selectinload
from app.imports.serializers import serialize_many
from app.imports.models import ConsignmentChangeHistory, EtaRevisionHistory, StatusUpdateHistory

from app.enums import Status
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
    ],
    "Inbound": [Status.ARRIVED_AT_QFL.value, Status.ON_ROAD.value],
    "Closed": [Status.ARRIVED_AT_WORKS.value],
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


def verify_entry_ownership(consignment, user, db):
    # Admins may touch any record; everyone else only what they created. `db` is
    # kept in the signature for call-site compatibility, though no longer needed.
    if user.is_admin:
        return

    if consignment.created_by_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="This entry does not belong to you"
        )


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

def fetch_consignments_page(db, include_deleted, include_closed, status, stage,
                            branch_id, supplier_id, requisition_type,
                            missing_only, etd_from, etd_to, q, page, page_size):
    # status, branch_id, supplier_id and requisition_type are lists (the list
    # screen filters are multi-select), so each is an IN filter, not an equals.
    conditions = []

    if not include_deleted:
        conditions.append(Consignment.is_deleted == False)

    # A stage is a group of statuses (the six-stage pipeline strip); it narrows
    # to that group's statuses.
    if stage and stage != "all":
        stage_statuses = STAGE_GROUPS.get(stage)
        if stage_statuses:
            conditions.append(Consignment.current_status.in_(stage_statuses))

    if status:
        conditions.append(Consignment.current_status.in_(status))

    # "Arrived at works" is closed and hidden by default, unless the caller
    # asks to include it, is looking at the Closed stage, or explicitly filters
    # to that status. Mirrors the list view's own rule.
    if not include_closed and stage != "Closed" and not (status and CLOSED_STATUS_VALUE in status):
        conditions.append(Consignment.current_status != CLOSED_STATUS_VALUE)

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

    # "Missing information only" — the server-side notion of an incomplete
    # record is a draft (a submitted one has passed the full rule set).
    if missing_only:
        conditions.append(Consignment.record_state == "draft")

    if etd_from:
        conditions.append(Consignment.etd >= etd_from)

    if etd_to:
        conditions.append(Consignment.etd <= etd_to)

    if q:
        pattern = "%" + q.strip() + "%"
        conditions.append(
            or_(
                Consignment.origin.ilike(pattern),
                Consignment.gd_number.ilike(pattern),
                Consignment.instrument_number.ilike(pattern)
            )
        )

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


#----------------------------------------------
# FETCH ALL CONSIGNMENTS HISTORY OF A SPECIFIC
# CONSIGNMENT FROM DB
#----------------------------------------------

def fetch_all_consignment_history(db, include_reverted, consignment_id):
    query = select(ConsignmentChangeHistory)

    if not include_reverted:
        query = query.where(
            ConsignmentChangeHistory.is_reverted == False
        )
        
    query = query.where(
        ConsignmentChangeHistory.consignment_id == consignment_id
    ).options(
        joinedload(ConsignmentChangeHistory.consignment),
        joinedload(ConsignmentChangeHistory.changed_by),
        joinedload(ConsignmentChangeHistory.reverted_by)
    )
    

    return db.execute(query).scalars().all()

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

        if updation_dict.get("effective_date") is None:
            raise HTTPException(
                status_code=400,
                detail="Effective date is required"
            )
        
        status_change = StatusUpdateHistory(
            consignment_id = consignment.id,
            previous_status = updation_dict.get("current_status", {}).get("old_value"),
            new_status = updation_dict.get("current_status", {}).get("new_value"),
            remarks = updation_dict.get("remarks", {}).get("new_value"),
            effective_date = updation_dict.get("effective_date", {}).get("new_value"),
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
# A consignment closes when its status reaches "Arrived at works". While
# closed it cannot be edited by anyone until an admin reopens it. The check
# lives here so the one status value that means "closed" is written once.
#---------------------------------------

def is_closed(consignment):
    return consignment.current_status == Status.ARRIVED_AT_WORKS.value


#---------------------------------------
# SUBMIT VALIDATION
#
# The full rule set, enforced only when a draft is submitted — never at the
# database level, because drafts and submitted rows share one table and a
# draft is allowed to be empty. Mirrors the front end's consignmentSubmitSchema
# so the two cannot drift. Returns a list of human readable messages; an empty
# list means the consignment is complete enough to submit.
#
# The requisition rules are a single dict, so adding a requisition type later
# is a one line change here (and its mirror in the front end), not a hunt
# through if-statements.
#---------------------------------------

REQUISITION_REQUIRED = {
    "Store": [("reference_number", "Reference no.")],
    "Engineering": [
        ("reference_number", "Reference no."),
        ("job_number", "Job no."),
        ("mo_number", "MO no."),
    ],
    "Others": [("description", "Description")],
}


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


def submission_errors(consignment):
    errors = []

    if not consignment.branch_id:
        errors.append("Branch is required")
    if not consignment.supplier_id:
        errors.append("Supplier is required")
    if not consignment.origin:
        errors.append("Country of origin is required")
    if not consignment.currency:
        errors.append("Currency is required")

    active_items = [item for item in consignment.items if not item.is_deleted]

    if not active_items:
        errors.append("Add at least one item")

    for index, item in enumerate(active_items, start=1):
        if not item.item_name:
            errors.append(f"Item {index}: item name is required")
        if not item.item_code:
            errors.append(f"Item {index}: item code is required")
        if item.quantity is None:
            errors.append(f"Item {index}: quantity is required")
        if not item.unit_of_measurement:
            errors.append(f"Item {index}: unit of measure is required")

        if not item.requisition_type:
            errors.append(f"Item {index}: requisition type is required")
        else:
            for field, label in REQUISITION_REQUIRED.get(item.requisition_type, []):
                if not getattr(item, field):
                    errors.append(
                        f"Item {index}: {label} is required for a {item.requisition_type} item"
                    )

    if not consignment.payment_instrument:
        errors.append("Payment instrument is required")
    if not consignment.instrument_number:
        errors.append("Instrument number is required")
    if not consignment.works:
        errors.append("Works is required")
    if consignment.exchange_rate is None:
        errors.append("Exchange rate is required")
    if not consignment.rate_booked_on:
        errors.append("The date the rate was booked is required")
    if not consignment.current_status:
        errors.append("Status is required")

    if consignment.etd and consignment.eta and consignment.eta < consignment.etd:
        errors.append("ETA cannot be before ETD")

    return errors