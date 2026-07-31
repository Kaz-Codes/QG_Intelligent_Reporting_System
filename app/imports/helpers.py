from fastapi import HTTPException
from app.imports.models import Consignment, ConsignmentItem, Payment, ConsignmentChangeHistory
from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload, selectinload
from app.imports.serializers import serialize_many
from app.imports.models import ConsignmentChangeHistory, EtaRevisionHistory, StatusUpdateHistory

from app.accounts.models import Role
from sqlalchemy import select
from datetime import datetime, timezone, date
from sqlalchemy.inspection import inspect
from decimal import Decimal

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

    role = db.execute(
        select(Role).where(
            Role.id == user.role_id
        )
    ).scalar_one_or_none()

    if role and role.name in ("admin", "manager"):
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

def fetch_consignments_page(db, include_deleted, status, branch_id, supplier_id, consignment_type, requisition_type, q, page, page_size):
    conditions = []

    if not include_deleted:
        conditions.append(Consignment.is_deleted == False)

    if status:
        conditions.append(Consignment.current_status == status)

    if branch_id is not None:
        conditions.append(Consignment.branch_id == branch_id)

    if supplier_id is not None:
        conditions.append(Consignment.supplier_id == supplier_id)

    if consignment_type:
        conditions.append(Consignment.consignment_type == consignment_type)

    if requisition_type:
        conditions.append(
            Consignment.id.in_(
                select(ConsignmentItem.consignment_id).where(
                    ConsignmentItem.requisition_type == requisition_type
                )
            )
        )

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