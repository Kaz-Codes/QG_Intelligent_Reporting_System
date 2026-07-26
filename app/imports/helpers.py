from fastapi import HTTPException
from app.imports.models import Consignment, ConsignmentItem, Payment, ConsignmentChangeHistory
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from app.imports.serializers import serialize_consignment, serialize_many
from app.imports.models import ConsignmentChangeHistory, EtaRevisionHistory, StatusUpdateHistory

from app.accounts.models import Role
from sqlalchemy import select

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
        joinedload(Consignment.works),
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
# FETCH ALL CONSIGNMENTS FROM DB
#-------------------------------------

def fetch_all_consignments(db, include_deleted):
    query = select(Consignment)

    if not include_deleted:
        query = query.where(
            Consignment.is_deleted == False
        )
        
    query = query.options(
        joinedload(Consignment.branch),
        joinedload(Consignment.supplier),
        joinedload(Consignment.works),
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
    

    return db.execute(query).scalars().all()


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
        new_value = change_data["new_value"]
        setattr(consignment, field, new_value)


#------------------------------------
# ADD UPDATES IN CONSIGNMENT CHANGE
# HISTORY TO KEEP TRACK
#------------------------------------

def add_in_consignment_change_history(
        updation_dict, 
        new_items_added,
        new_payments_added,
        item_updates,
        payment_updates,
        consignment,
        user,
        db
):

    new_items_dicts = []
    new_payments_dicts = []

    for item in new_items_added:
        new_items_dicts.append(item.model_dump())

    for payment in new_payments_added:
        new_payments_dicts.append(payment.model_dump())

    updates_history = {
        "fields" : updation_dict, 
        "items" : item_updates, 
        "payments" : payment_updates,
        "new_items": new_items_dicts,
        "new_payments" : new_payments_dicts
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
        