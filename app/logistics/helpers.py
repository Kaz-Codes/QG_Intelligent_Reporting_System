from fastapi import HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.inspection import inspect
from datetime import datetime, timezone, date
from decimal import Decimal

from app.logistics.models import (
    LogisticsConsignment, LogisticsItem, LogisticsPackage, LogisticsContainer,
    LogisticsChangeHistory, LogisticsStatusHistory,
)
from app.logistics.serializers import serialize_many
from app.enums import LogisticsStatus


#----------------------------------
# TURNING A STRING BACK INTO A TYPE
#
# Change history is stored as JSON, so dates, datetimes and Decimals come
# back out as strings. Before writing an old value back onto a typed column
# on a revert, it is turned back into the type the column expects. JSON
# columns (the allocation / rfd / remark feeds) fall through untouched.
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
# ADMINS MAY TOUCH ANY ORDER; EVERYONE
# ELSE ONLY THE ONES THEY CREATED.
#----------------------------------

def verify_entry_ownership(consignment, user, db):
    if user.is_admin:
        return

    if consignment.created_by_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="This entry does not belong to you"
        )


#-------------------------------------------------
# CONVERTING SCHEMA OBJECTS INTO DATABASE ROWS
#
# The order header excludes its line collections; each line collection is
# turned into its own list of ORM objects. The nested feeds (rfd_history,
# allocations) ride along inside the line's model_dump as plain JSON.
#-------------------------------------------------

def create_consignment_object(consignment_data, user):
    # exclude_none so an empty order falls back to the column defaults
    # (e.g. current_status, remarks_log) instead of writing NULL over them
    consignment_data_dict = consignment_data.model_dump(
        exclude_none=True,
        exclude={"consignment_id", "items", "packages", "containers"}
    )

    consignment_data_dict["created_by_id"] = user.id

    consignment = LogisticsConsignment(**consignment_data_dict)
    return consignment


def create_child_objects(child_schemas, model):
    # child_schemas is a list of pydantic line schemas; each becomes one row.
    objects = []
    for child in (child_schemas or []):
        objects.append(model(**child.model_dump()))
    return objects


#-------------------------------------
# FETCH ONE ORDER FROM DB BASED ON ID
#-------------------------------------

def fetch_consignment(db, consignment_id):
    query = select(LogisticsConsignment).where(
        LogisticsConsignment.id == consignment_id
    ).options(
        selectinload(LogisticsConsignment.items),
        selectinload(LogisticsConsignment.packages),
        selectinload(LogisticsConsignment.containers),
        selectinload(LogisticsConsignment.status_updates),
        selectinload(LogisticsConsignment.change_history),
        joinedload(LogisticsConsignment.created_by),
        joinedload(LogisticsConsignment.deleted_by)
    )

    return db.execute(query).scalar_one_or_none()


#-------------------------------------
# FETCH ONE PAGE OF ORDERS, FILTERED
#
# The list screen filters and pages, so the filters are applied in SQL and
# only one page is loaded. The total count is worked out with the same
# filters so the caller can say how many pages there are.
#-------------------------------------

def fetch_consignments_page(db, include_deleted, status, order_type,
                            customer, gate_out_from, gate_out_to, q,
                            page, page_size):
    # status, order_type and customer are lists (the list screen filters are
    # multi-select), so each is an IN filter, not an equals.
    conditions = []

    if not include_deleted:
        conditions.append(LogisticsConsignment.is_deleted == False)

    if status:
        conditions.append(LogisticsConsignment.current_status.in_(status))

    if order_type:
        conditions.append(LogisticsConsignment.order_type.in_(order_type))

    # Customer is free text on the order (there is no customer master), so it
    # is filtered by the name value directly.
    if customer:
        conditions.append(LogisticsConsignment.customer_name.in_(customer))

    if gate_out_from:
        conditions.append(LogisticsConsignment.gate_out_date >= gate_out_from)

    if gate_out_to:
        conditions.append(LogisticsConsignment.gate_out_date <= gate_out_to)

    if q:
        pattern = "%" + q.strip() + "%"
        conditions.append(
            or_(
                LogisticsConsignment.customer_name.ilike(pattern),
                LogisticsConsignment.pod.ilike(pattern),
                LogisticsConsignment.origin_country.ilike(pattern),
                LogisticsConsignment.mo_no.ilike(pattern)
            )
        )

    # how many match, for the page count
    total = db.execute(
        select(func.count(LogisticsConsignment.id)).where(*conditions)
    ).scalar()

    # the page itself, newest first
    query = select(LogisticsConsignment).where(*conditions).options(
        selectinload(LogisticsConsignment.items),
        selectinload(LogisticsConsignment.packages),
        selectinload(LogisticsConsignment.containers),
        selectinload(LogisticsConsignment.status_updates),
        selectinload(LogisticsConsignment.change_history),
        joinedload(LogisticsConsignment.created_by),
        joinedload(LogisticsConsignment.deleted_by)
    ).order_by(
        LogisticsConsignment.id.desc()
    ).limit(page_size).offset((page - 1) * page_size)

    rows = db.execute(query).scalars().all()

    return rows, total


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
# GET ALL THE HEADER FIELDS THAT ARE TO
# BE UPDATED IN THE ALREADY CREATED ORDER
#---------------------------------------

def updated_fields(consignment, update_consignment_data, db):
    updation_dict = {}  #--> which field to update and its old and new value

    # exclude_none because a field left out means the user did not touch it
    fields_to_update = update_consignment_data.model_dump(
        exclude_none=True,
        exclude={"consignment_id", "items", "packages", "containers"}
    )

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


#----------------------------------
# FINDING NEW LINES TO ADD
#
# A line with no id has not been saved yet, so it is a new row.
#----------------------------------

def new_children_to_add(child_schemas):
    return [child for child in (child_schemas or []) if child.id is None]


#--------------------------------------
# DELETING LINES NOT COMING IN THE
# REQUEST BODY (ASSUMING THE USER
# HAS REMOVED THEM)
#--------------------------------------

def delete_missing(consignment, present_ids, id_column, db, model):
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


#----------------------------------
# FIELD LEVEL DIFF FOR EXISTING LINES
#----------------------------------

def updated_children(existing_children, child_schemas):
    updated_list = []

    serialized = serialize_many(existing_children)
    serialized_dict = {row["id"]: row for row in serialized}

    for child in (child_schemas or []):
        child_dict = child.model_dump()

        if child_dict["id"] is None:
            continue

        old_child = serialized_dict.get(child_dict["id"])
        if old_child is None:
            continue

        updation_dict = {}
        for field in list(child_dict.keys()):
            if child_dict[field] != old_child.get(field):
                updation_dict[field] = {
                    "old_value": old_child.get(field),
                    "new_value": child_dict[field]
                }

        if updation_dict:
            updation_dict["id"] = child_dict["id"]
            updated_list.append(updation_dict)

    return updated_list


#------------------------------------
# APPLY ALL THE UPDATES
#------------------------------------

def apply_updates(updation_dict, target):

    for field, change_data in updation_dict.items():
        # A line update dict also carries a plain "id" so the row can be
        # matched. Skip anything that is not an {old_value, new_value} change,
        # so the id is left alone rather than written onto the row (which would
        # also strip it from the copy stored in the change history and break a
        # revert of that line).
        if not isinstance(change_data, dict) or "new_value" not in change_data:
            continue

        setattr(target, field, change_data["new_value"])


#------------------------------------
# ADD UPDATES IN CHANGE HISTORY
# TO KEEP TRACK
#------------------------------------

def add_in_consignment_change_history(
        updation_dict,
        new_items, new_packages, new_containers,
        deleted_items, deleted_packages, deleted_containers,
        item_updates, package_updates, container_updates,
        consignment, user, db
):

    updates_history = {
        "fields": updation_dict,
        "items": item_updates,
        "packages": package_updates,
        "containers": container_updates,
        "new_items": new_items,
        "new_packages": new_packages,
        "new_containers": new_containers,
        "deleted_items": serialize_many(deleted_items),
        "deleted_packages": serialize_many(deleted_packages),
        "deleted_containers": serialize_many(deleted_containers),
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
            remarks=None,
            effective_date=effective_date,
            user_id=user.id
        )

        db.add(status_change)


#---------------------------------
# HELPERS REQUIRED FOR REVERTING
# UPDATES
#
# A revert puts the header fields back, deletes the lines the update added,
# restores the lines it removed and rolls back the field changes on the lines
# it edited.
#---------------------------------

def revert(consignment_history, consignment, db):
    history = consignment_history.history

    # Reverting header fields
    revert_local_fields(consignment, history.get("fields", {}))

    child_models = [
        ("items", "new_items", "deleted_items", LogisticsItem),
        ("packages", "new_packages", "deleted_packages", LogisticsPackage),
        ("containers", "new_containers", "deleted_containers", LogisticsContainer),
    ]

    for updates_key, new_key, deleted_key, model in child_models:
        # Deleting lines the update added back out
        add_or_delete(history.get(new_key, []), model, consignment.id, model.id, db, delete=True)
        # Adding lines the update removed back in
        add_or_delete(history.get(deleted_key, []), model, consignment.id, model.id, db, delete=False)
        # Rolling back edits to lines that already existed
        revert_old_values(history.get(updates_key, []), model, consignment.id, model.id, db)


def revert_local_fields(consignment, fields):
    consignment_columns = inspect(consignment).mapper.column_attrs
    for column in consignment_columns:
        change = fields.get(column.key)
        if isinstance(change, dict) and "old_value" in change:
            old_value = coerce_value(LogisticsConsignment, column.key, change["old_value"])
            setattr(consignment, column.key, old_value)


def add_or_delete(data_list, model, consignment_id, id_column, db, delete=False):
    for data in data_list:
        data_id = data.get("id")
        if data_id:
            row = db.execute(
                select(model).where(
                    model.consignment_id == consignment_id
                ).where(
                    id_column == data_id
                )
            ).scalar_one_or_none()
            if row:
                if delete:
                    row.is_deleted = True
                    row.deleted_at = datetime.now(timezone.utc)
                else:
                    row.is_deleted = False
                    row.deleted_at = None


def revert_old_values(updated_data, model, consignment_id, id_column, db):
    for data in updated_data:
        data_id = data.get("id")
        if data_id:
            row = db.execute(
                select(model).where(
                    model.consignment_id == consignment_id
                ).where(
                    id_column == data_id
                )
            ).scalar_one_or_none()
            if row:
                row_columns = inspect(row).mapper.column_attrs
                for column in row_columns:
                    change = data.get(column.key)
                    if isinstance(change, dict) and "old_value" in change:   # <-- skips the bare "id"
                        old_value = coerce_value(model, column.key, change["old_value"])
                        setattr(row, column.key, old_value)


#---------------------------------------
# THE CLOSED LOCK
#
# An order closes when its status reaches "Delivered" — the terminal stage for
# both export and local orders. While closed it cannot be edited by anyone
# until an admin reopens it.
#---------------------------------------

def is_closed(consignment):
    return consignment.current_status == LogisticsStatus.DELIVERED.value


#---------------------------------------
# SUBMIT VALIDATION
#
# The rule set enforced only when a draft is submitted — never at the database
# level, since drafts and submitted rows share one table and a draft may be
# empty. Mirrors the front end's logistics consignmentSchema.superRefine.
# Returns a list of messages; empty means complete enough to submit. Opt-in:
# the front end only sees these if it calls the submit endpoint.
#---------------------------------------

def submission_errors(consignment):
    errors = []

    if not consignment.customer_name:
        errors.append("Customer name is required")

    if consignment.order_type == "Export":
        if not consignment.origin_country:
            errors.append("Country of origin is required for exports")
    elif consignment.order_type == "Local":
        if not consignment.origin_city:
            errors.append("City is required for local orders")
        if not consignment.origin_province:
            errors.append("Province is required for local orders")

    active_items = [item for item in consignment.items if not item.is_deleted]

    if not active_items:
        errors.append("Add at least one item")

    for index, item in enumerate(active_items, start=1):
        if not item.item_detail:
            errors.append(f"Item {index}: item detail is required")
        if item.quantity is None or item.quantity <= 0:
            errors.append(f"Item {index}: quantity must be greater than 0")

    return errors
