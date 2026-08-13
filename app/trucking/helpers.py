from fastapi import HTTPException
from sqlalchemy import select, func, or_, and_, exists
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.inspection import inspect
from datetime import datetime, timezone, date
from decimal import Decimal

from app.trucking.models import (
    TruckingConsignment, TruckingVehicle, TruckingChangeHistory,
)
from app.trucking.serializers import serialize_many
from app.masters.models import Transporter
from app.enums import VehicleTrackingStatus


#----------------------------------
# TURNING A STRING BACK INTO A TYPE
#
# Change history is stored as JSON, so dates and Decimals come back out as
# strings. Before writing an old value back onto a typed column on a revert,
# it is turned back into the type the column expects.
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
# ADMINS MAY TOUCH ANY JOB; EVERYONE
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
# CONVERTING AN OBJECT FROM SCHEMA
# INTO A DATABASE ROW USING SQL ALCHEMY ORM
#-------------------------------------------------

def create_consignment_object(consignment_data, user):
    # exclude_none so an empty job falls back to the column defaults instead
    # of writing NULL over them
    consignment_data_dict = consignment_data.model_dump(exclude_none=True, exclude={"vehicles", "consignment_id"})

    consignment_data_dict["created_by_id"] = user.id

    consignment = TruckingConsignment(**consignment_data_dict)
    return consignment


#--------------------------------------
# CREATING AN OBJECT FOR EACH VEHICLE
#
# Vehicles come in as a list, so an object is created for each and a list of
# objects returned, the same as item lines in imports.
#--------------------------------------

def create_vehicle_object(consignment_data):
    vehicles = consignment_data.vehicles

    objects = []

    for vehicle in vehicles:
        # exclude_none so an omitted tracking status falls back to the
        # column default instead of writing NULL over it
        vehicle_dict = vehicle.model_dump(exclude_none=True)
        objects.append(
            TruckingVehicle(**vehicle_dict)
        )

    return objects


#-------------------------------------
# KEEP transporter_id IN STEP WITH transporter_name
#
# The wizard sends a transporter NAME (it always has — this predates the
# master). The master link is derived from it here, on create, update and
# revert, so the two can never disagree — there is no second place a
# transporter can be set. Mirrors logistics.helpers.resolve_customer_id.
#
# An unmatched name leaves transporter_id NULL rather than creating a master
# row: silently minting a transporter from a typo is how a master list
# becomes the very free-text mess it exists to prevent. The Masters screen
# (or inline create) is where a genuinely new transporter is added, and the
# next save picks it up.
#
# Matching is case-insensitive and trims, the same reasoning as customers.
#-------------------------------------

def resolve_transporter_id(consignment, db):
    name = (consignment.transporter_name or "").strip()

    if not name:
        consignment.transporter_id = None
        return

    match = db.execute(
        select(Transporter).where(func.lower(Transporter.name) == name.lower())
    ).scalars().first()

    consignment.transporter_id = match.id if match else None


#-------------------------------------
# FETCH ONE JOB FROM DB BASED ON ID
#-------------------------------------

def fetch_consignment(db, consignment_id):
    query = select(TruckingConsignment).where(
        TruckingConsignment.id == consignment_id
    ).options(
        selectinload(TruckingConsignment.vehicles),
        selectinload(TruckingConsignment.change_history),
        joinedload(TruckingConsignment.created_by),
        joinedload(TruckingConsignment.deleted_by)
    )

    return db.execute(query).scalar_one_or_none()


#-------------------------------------
# FETCH ONE PAGE OF JOBS, FILTERED
#
# The list screen filters and pages, so the filters are applied in SQL and
# only one page is loaded. The total count is worked out with the same
# filters so the caller can say how many pages there are.
#-------------------------------------

def fetch_consignments_page(db, include_deleted, movement_type, source,
                            open_only, pending_only, q, page, page_size):
    # movement_type and source are lists (the list screen filters are
    # multi-select), so each is an IN filter, not an equals.
    conditions = []

    if not include_deleted:
        conditions.append(TruckingConsignment.is_deleted == False)

    if movement_type:
        conditions.append(TruckingConsignment.movement_type.in_(movement_type))

    if source:
        conditions.append(TruckingConsignment.source.in_(source))

    # "Open only" — a job is closed once it has vehicles and every one of them
    # is delivered (there is no stored job status). So an open job is one that
    # has no vehicles yet, or still has at least one vehicle not delivered.
    if open_only:
        delivered = VehicleTrackingStatus.DELIVERED.value
        has_vehicle = exists().where(
            and_(
                TruckingVehicle.consignment_id == TruckingConsignment.id,
                TruckingVehicle.is_deleted == False,
            )
        )
        has_undelivered = exists().where(
            and_(
                TruckingVehicle.consignment_id == TruckingConsignment.id,
                TruckingVehicle.is_deleted == False,
                TruckingVehicle.tracking_status != delivered,
            )
        )
        conditions.append(or_(~has_vehicle, has_undelivered))

    # "Pending only" — the server-side notion of an incomplete job is a draft
    # (a submitted one has passed the full rule set).
    if pending_only:
        conditions.append(TruckingConsignment.record_state == "draft")

    if q:
        pattern = "%" + q.strip() + "%"
        conditions.append(
            or_(
                TruckingConsignment.transporter_name.ilike(pattern),
                TruckingConsignment.reference_no.ilike(pattern),
                TruckingConsignment.item_details.ilike(pattern)
            )
        )

    # how many match, for the page count
    total = db.execute(
        select(func.count(TruckingConsignment.id)).where(*conditions)
    ).scalar()

    # the page itself, newest first
    query = select(TruckingConsignment).where(*conditions).options(
        selectinload(TruckingConsignment.vehicles),
        selectinload(TruckingConsignment.change_history),
        joinedload(TruckingConsignment.created_by),
        joinedload(TruckingConsignment.deleted_by)
    ).order_by(
        TruckingConsignment.id.desc()
    ).limit(page_size).offset((page - 1) * page_size)

    rows = db.execute(query).scalars().all()

    return rows, total


#----------------------------------------
# FETCH ALL CHANGE HISTORY OF A JOB
#----------------------------------------

#----------------------------------------
# ONE PAGE OF CHANGE HISTORY, NEWEST FIRST
#
# Mirrors fetch_consignments_page's shape: filter conditions built once and
# reused for both the count and the page itself, so they can never disagree.
# id.desc() is a secondary key after created_at so paging stays deterministic
# even when two rows share a timestamp.
#----------------------------------------

def fetch_all_consignment_history(db, include_reverted, consignment_id, page=1, page_size=20):
    conditions = [TruckingChangeHistory.consignment_id == consignment_id]

    if not include_reverted:
        conditions.append(TruckingChangeHistory.is_reverted == False)

    total = db.execute(
        select(func.count(TruckingChangeHistory.id)).where(*conditions)
    ).scalar()

    query = select(TruckingChangeHistory).where(*conditions).options(
        joinedload(TruckingChangeHistory.consignment),
        joinedload(TruckingChangeHistory.changed_by),
        joinedload(TruckingChangeHistory.reverted_by)
    ).order_by(
        TruckingChangeHistory.created_at.desc(), TruckingChangeHistory.id.desc()
    ).limit(page_size).offset((page - 1) * page_size)

    rows = db.execute(query).scalars().all()

    return rows, total


#----------------------------------------
# FETCH THE LATEST CHANGE HISTORY ROW
#----------------------------------------

def fetch_latest_consignment_history(db, consignment_id):
    query = select(TruckingChangeHistory).where(
        TruckingChangeHistory.consignment_id == consignment_id
    ).options(
        joinedload(TruckingChangeHistory.consignment),
        joinedload(TruckingChangeHistory.changed_by),
        joinedload(TruckingChangeHistory.reverted_by)
    ).order_by(TruckingChangeHistory.created_at.desc())

    return db.execute(query).scalars().first()


#----------------------------------------
# FETCH ONE CHANGE HISTORY ROW BY ID
#----------------------------------------

def fetch_consignment_history(db, consignment_id, history_id):
    query = select(TruckingChangeHistory).where(
        TruckingChangeHistory.consignment_id == consignment_id
    ).where(
        TruckingChangeHistory.id == history_id
    ).options(
        joinedload(TruckingChangeHistory.consignment),
        joinedload(TruckingChangeHistory.changed_by),
        joinedload(TruckingChangeHistory.reverted_by)
    )

    return db.execute(query).scalar_one_or_none()


#---------------------------------------
# GET ALL THE FIELDS THAT ARE TO BE
# UPDATED IN THE ALREADY CREATED JOB
#---------------------------------------

def updated_fields(consignment, update_consignment_data, db):
    updation_dict = {}  #--> which field to update and its old and new value

    # exclude_none because a field left out means the user did not touch it
    fields_to_update = update_consignment_data.model_dump(exclude_none=True, exclude={"vehicles", "consignment_id"})

    columns = {c.key for c in TruckingConsignment.__mapper__.column_attrs}

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
# FINDING NEW VEHICLES TO ADD
#
# A vehicle with an id the job does not already have is a new one.
#----------------------------------

def new_vehicles_to_add(consignment, update_consignment_data):
    new_vehicles = []
    vehicles_in_updated_data = update_consignment_data.vehicles
    vehicles_in_consignment = consignment.vehicles

    consignment_vehicle_ids = [vehicle.id for vehicle in vehicles_in_consignment]

    for vehicle in vehicles_in_updated_data:
        if vehicle.id not in consignment_vehicle_ids:
            new_vehicles.append(vehicle)

    return new_vehicles


#--------------------------------------
# DELETING VEHICLES THAT ARE NOT COMING
# IN THE REQUEST BODY (ASSUMING THE
# USER HAS REMOVED THEM)
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
# FINDING THE VEHICLES THAT CHANGED
#----------------------------------

def updated_vehicles(consignment, update_consignment_data, db):
    updated_vehicles_list = []
    vehicles_in_updated_data = update_consignment_data.vehicles
    vehicles_in_consignment = consignment.vehicles

    serialized_consignment_vehicles = serialize_many(vehicles_in_consignment)

    serialized_dict = {vehicle["id"]: vehicle for vehicle in serialized_consignment_vehicles}

    for vehicle in vehicles_in_updated_data:
        updation_dict = {}
        vehicle_dict = vehicle.model_dump()
        consignment_vehicle = serialized_dict.get(vehicle_dict["id"])

        if consignment_vehicle is not None:

            for field in list(vehicle_dict.keys()):
                if vehicle_dict[field] != consignment_vehicle[field]:

                    updation_dict[field] = {
                        "old_value": consignment_vehicle[field],
                        "new_value": vehicle_dict[field]
                    }

        if updation_dict:
            updation_dict["id"] = vehicle_dict["id"]
            updated_vehicles_list.append(updation_dict)

    return updated_vehicles_list


#------------------------------------
# APPLY ALL THE UPDATES
#------------------------------------

def apply_updates(updation_dict, consignment):

    for field, change_data in updation_dict.items():
        # A vehicle update dict also carries a plain "id" so the row can be
        # matched. Skip anything that is not an {old_value, new_value} change,
        # so the id is left alone rather than popped, which would also strip it
        # out of the copy already stored in the change history.
        if not isinstance(change_data, dict) or "new_value" not in change_data:
            continue

        setattr(consignment, field, change_data["new_value"])


#------------------------------------
# ADD UPDATES IN CHANGE HISTORY
# TO KEEP TRACK
#------------------------------------

def add_in_consignment_change_history(
        updation_dict,
        new_vehicles_added,
        deleted_vehicles,
        vehicle_updates,
        consignment,
        user,
        db
):

    serialized_deleted_vehicles = serialize_many(deleted_vehicles)

    updates_history = {
        "fields": updation_dict,
        "vehicles": vehicle_updates,
        "new_vehicles": new_vehicles_added,
        "deleted_vehicles": serialized_deleted_vehicles
    }

    change_history = TruckingChangeHistory(
        consignment_id=consignment.id,
        change_type="update",
        history=updates_history,
        changed_by_id=user.id
    )

    db.add(change_history)
    return change_history


#---------------------------------
# HELPERS REQUIRED FOR REVERTING
# UPDATES
#---------------------------------

def revert(consignment_history, consignment, db):
    history = consignment_history.history
    fields = history["fields"]
    vehicle_updates = history["vehicles"]
    new_vehicles = history["new_vehicles"]
    deleted_vehicles = history["deleted_vehicles"]

    # Reverting the job's own fields
    revert_local_fields(consignment, fields)

    # Deleting vehicles that were added in the update
    add_or_delete(new_vehicles, TruckingVehicle, consignment.id, TruckingVehicle.id, db, delete=True)

    # Adding back vehicles that were deleted in the update
    add_or_delete(deleted_vehicles, TruckingVehicle, consignment.id, TruckingVehicle.id, db, delete=False)

    # Reverting already existing vehicle updates
    revert_old_values(vehicle_updates, TruckingVehicle, consignment.id, TruckingVehicle.id, db)


def revert_local_fields(consignment, fields):
    consignment_columns = inspect(consignment).mapper.column_attrs
    for column in consignment_columns:
        change = fields.get(column.key)
        if isinstance(change, dict) and "old_value" in change:
            old_value = coerce_value(TruckingConsignment, column.key, change["old_value"])
            setattr(consignment, column.key, old_value)


def add_or_delete(data, model, consignment_id, id_column, db, delete=False):
    for row_data in data:
        data_id = row_data.get("id")
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
                    if isinstance(change, dict) and "old_value" in change:
                        old_value = coerce_value(model, column.key, change["old_value"])
                        setattr(consignment_data, column.key, old_value)


#---------------------------------------
# THE CLOSED LOCK
#
# Trucking has no stored job-level status — the job status is a rollup over
# the vehicles. So a job is closed once it has vehicles, every one of them is
# "Delivered", AND it has been submitted. A draft whose trucks have all
# arrived is not closed yet: it has not passed the full rule set in
# submission_errors, so there is nothing to protect.
#
# Same two-part rule as imports ("Arrived at Works" AND submitted) and
# logistics ("Delivered" AND submitted). As there, only the /submit route acts
# on it — a plain draft save never closes a job, no matter what the vehicles
# say. While closed it cannot be edited by anyone until an admin reopens it.
#---------------------------------------

def is_closed(consignment):
    if consignment.record_state != "submitted":
        return False

    active_vehicles = [v for v in consignment.vehicles if not v.is_deleted]
    if not active_vehicles:
        return False
    return all(
        vehicle.tracking_status == VehicleTrackingStatus.DELIVERED.value
        for vehicle in active_vehicles
    )


#---------------------------------------
# SUBMIT VALIDATION
#
# The rule set enforced only when a draft is submitted — never at the database
# level. Mirrors the front end's truckingSubmitSchema. Returns a list of
# messages; empty means complete enough to submit. Opt-in: the front end only
# sees these if it calls the submit endpoint.
#---------------------------------------

def submission_errors(consignment):
    errors = []

    # Shipment reference / IDM is required for outbound and inbound movements
    # (not for intrafactory).
    if consignment.movement_type and consignment.movement_type != "Intrafactory":
        if not consignment.reference_no:
            errors.append("Shipment reference / IDM is required for outbound and inbound movements")

    active_vehicles = [v for v in consignment.vehicles if not v.is_deleted]

    if not active_vehicles:
        errors.append("At least one vehicle is required")

    # Container no. is required per vehicle for inbound (import FOB) jobs.
    if consignment.movement_type == "Inbound":
        for index, vehicle in enumerate(active_vehicles, start=1):
            if not vehicle.container_no:
                errors.append(f"Vehicle {index}: container no. is required for import FOB")

    return errors
