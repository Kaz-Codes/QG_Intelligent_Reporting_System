from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.inspection import inspect
from datetime import datetime, timezone, date
from decimal import Decimal

from app.logistics.models import (
    LogisticsConsignment, LogisticsChangeHistory, LogisticsStatusHistory,
)
from app.accounts.models import Role


#----------------------------------
# TURNING A STRING BACK INTO A TYPE
#
# Change history is stored as JSON, so dates, datetimes and Decimals come
# back out as strings. Before writing an old value back onto a typed column
# on a revert, it is turned back into the type the column expects.
#----------------------------------

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


#----------------------------------
# AN ENTRY OPERATOR MAY ONLY TOUCH
# ORDERS THEY CREATED. ADMIN AND
# MANAGER PASS STRAIGHT THROUGH.
#----------------------------------

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
# INTO A DATABASE ROW USING SQL ALCHEMY ORM
#-------------------------------------------------

def create_consignment_object(consignment_data, user):
    # exclude_none so an empty order falls back to the column defaults
    # (e.g. current_status) instead of writing NULL over them
    consignment_data_dict = consignment_data.model_dump(exclude_none=True, exclude={"consignment_id"})

    consignment_data_dict["created_by_id"] = user.id

    consignment = LogisticsConsignment(**consignment_data_dict)
    return consignment


#-------------------------------------
# FETCH ONE ORDER FROM DB BASED ON ID
#-------------------------------------

def fetch_consignment(db, consignment_id):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.id == consignment_id
    ).options(
        selectinload(LogisticsConsignment.status_updates),
        selectinload(LogisticsConsignment.change_history),
        joinedload(LogisticsConsignment.created_by),
        joinedload(LogisticsConsignment.deleted_by)
    )

    return db.execute(query).scalar_one_or_none()


#-------------------------------------
# FETCH ALL ORDERS FROM DB
#-------------------------------------

def fetch_all_consignments(db, include_deleted):
    query = select(LogisticsConsignment)

    if not include_deleted:
        query = query.where(
            LogisticsConsignment.is_deleted == False
        )

    query = query.options(
        selectinload(LogisticsConsignment.status_updates),
        selectinload(LogisticsConsignment.change_history),
        joinedload(LogisticsConsignment.created_by),
        joinedload(LogisticsConsignment.deleted_by)
    )

    return db.execute(query).scalars().all()


#----------------------------------------
# FETCH ALL CHANGE HISTORY OF AN ORDER
#----------------------------------------

def fetch_all_consignment_history(db, include_reverted, consignment_id):
    query = select(LogisticsChangeHistory)

    if not include_reverted:
        query = query.where(
            LogisticsChangeHistory.is_reverted == False
        )

    query = query.where(
        LogisticsChangeHistory.consignment_id == consignment_id
    ).options(
        joinedload(LogisticsChangeHistory.consignment),
        joinedload(LogisticsChangeHistory.changed_by),
        joinedload(LogisticsChangeHistory.reverted_by)
    ).order_by(LogisticsChangeHistory.created_at.desc())

    return db.execute(query).scalars().all()


#----------------------------------------
# FETCH THE LATEST CHANGE HISTORY ROW
#----------------------------------------

def fetch_latest_consignment_history(db, consignment_id):
    query = select(LogisticsChangeHistory).where(
        LogisticsChangeHistory.consignment_id == consignment_id
    ).options(
        joinedload(LogisticsChangeHistory.consignment),
        joinedload(LogisticsChangeHistory.changed_by),
        joinedload(LogisticsChangeHistory.reverted_by)
    ).order_by(LogisticsChangeHistory.created_at.desc())

    return db.execute(query).scalars().first()


#----------------------------------------
# FETCH ONE CHANGE HISTORY ROW BY ID
#----------------------------------------

def fetch_consignment_history(db, consignment_id, history_id):
    query = select(LogisticsChangeHistory).where(
        LogisticsChangeHistory.consignment_id == consignment_id
    ).where(
        LogisticsChangeHistory.id == history_id
    ).options(
        joinedload(LogisticsChangeHistory.consignment),
        joinedload(LogisticsChangeHistory.changed_by),
        joinedload(LogisticsChangeHistory.reverted_by)
    )

    return db.execute(query).scalar_one_or_none()


#---------------------------------------
# GET ALL THE FIELDS THAT ARE TO BE
# UPDATED IN THE ALREADY CREATED ORDER
#---------------------------------------

def updated_fields(consignment, update_consignment_data, db):
    updation_dict = {}  #--> which field to update and its old and new value

    # exclude_none because a field left out means the user did not touch it
    fields_to_update = update_consignment_data.model_dump(exclude_none=True, exclude={"consignment_id"})

    columns = {c.key for c in LogisticsConsignment.__mapper__.column_attrs}

    for field, new_value in fields_to_update.items():
        if field not in columns:
            continue

        old_value = getattr(consignment, field)

        if new_value == old_value:
            continue

        updation_dict[field] = {
            "old_value": old_value,
            "new_value": new_value
        }

    return updation_dict


#------------------------------------
# APPLY ALL THE UPDATES
#------------------------------------

def apply_updates(updation_dict, consignment):

    for field, change_data in updation_dict.items():
        new_value = change_data["new_value"]
        setattr(consignment, field, new_value)


#------------------------------------
# ADD UPDATES IN CHANGE HISTORY
# TO KEEP TRACK
#------------------------------------

def add_in_consignment_change_history(updation_dict, consignment, user, db):

    updates_history = {
        "fields": updation_dict
    }

    change_history = LogisticsChangeHistory(
        consignment_id=consignment.id,
        change_type="update",
        history=updates_history,
        changed_by_id=user.id
    )

    db.add(change_history)
    return change_history


#----------------------------------
# IF STATUS CHANGES, ADD NEW AND
# OLD STATUS IN STATUS HISTORY TO
# KEEP TRACK OF ALL STATUSES
#----------------------------------

def add_in_status_change_history(updation_dict, consignment, user, db):
    if updation_dict.get("current_status"):

        # The front end does not always send a date with a status change,
        # so it falls back to today rather than being refused.
        effective_date = updation_dict.get("effective_date", {}).get("new_value") or date.today()

        status_change = LogisticsStatusHistory(
            consignment_id=consignment.id,
            previous_status=updation_dict.get("current_status", {}).get("old_value"),
            new_status=updation_dict.get("current_status", {}).get("new_value"),
            remarks=updation_dict.get("remarks", {}).get("new_value"),
            effective_date=effective_date,
            user_id=user.id
        )

        db.add(status_change)


#---------------------------------
# HELPERS REQUIRED FOR REVERTING
# UPDATES
#
# A logistics order has no item or payment children, so a revert only puts
# the header fields back to what they were before the change.
#---------------------------------

def revert(consignment_history, consignment, db):
    history = consignment_history.history
    fields = history["fields"]

    revert_local_fields(consignment, fields)


def revert_local_fields(consignment, fields):
    consignment_columns = inspect(consignment).mapper.column_attrs
    for column in consignment_columns:
        change = fields.get(column.key)
        if isinstance(change, dict) and "old_value" in change:
            old_value = coerce_value(LogisticsConsignment, column.key, change["old_value"])
            setattr(consignment, column.key, old_value)
