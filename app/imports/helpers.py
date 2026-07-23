from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from app.enums import ChangeType
from app.imports.models import (
    Consignment, ConsignmentChangeHistory, ConsignmentItem, Payment,
)

#-----------------------------------------------------
# SMALL JOBS EVERY IMPORTS ROUTE NEEDS
#
# Fetching a row and complaining if it is not there, and
# writing down what a field held before somebody changed it.
#
# The change history is what makes reverting possible. Only
# the fields that actually changed are stored, not the whole
# record, so one row makes it obvious what was touched.
#-----------------------------------------------------


#--------------------------------
# FETCHING ROWS
#
# A soft deleted consignment is hidden by default. Only the
# restore route asks for one on purpose.
#--------------------------------

def get_consignment(consignment_id, db, include_deleted=False):
    consignment = db.execute(
        select(Consignment).where(Consignment.id == consignment_id)
    ).scalar_one_or_none()

    if consignment is None:
        raise HTTPException(
            status_code=404,
            detail="Consignment not found"
        )

    if consignment.is_deleted and not include_deleted:
        raise HTTPException(
            status_code=404,
            detail="Consignment not found"
        )

    return consignment


def get_item(item_id, consignment_id, db):
    item = db.execute(
        select(ConsignmentItem).where(ConsignmentItem.id == item_id)
    ).scalar_one_or_none()

    if item is None or item.consignment_id != consignment_id:
        raise HTTPException(
            status_code=404,
            detail="Item not found on this consignment"
        )

    return item


def get_payment(payment_id, consignment_id, db):
    payment = db.execute(
        select(Payment).where(Payment.id == payment_id)
    ).scalar_one_or_none()

    if payment is None or payment.consignment_id != consignment_id:
        raise HTTPException(
            status_code=404,
            detail="Payment not found on this consignment"
        )

    return payment


def get_change(change_id, db):
    change = db.execute(
        select(ConsignmentChangeHistory).where(
            ConsignmentChangeHistory.id == change_id
        )
    ).scalar_one_or_none()

    if change is None:
        raise HTTPException(
            status_code=404,
            detail="Change not found"
        )

    return change


#--------------------------------
# MAKING A VALUE SAFE FOR THE JSON COLUMN
#
# previous_values and new_values are JSON columns, and JSON
# has no idea what a date or a Decimal is. Everything is
# stored as a string and read back the same way.
#--------------------------------

def to_json(value):
    if value is None:
        return None

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float, str)):
        return value

    return str(value)


#--------------------------------
# READING A VALUE BACK OUT OF THE JSON COLUMN
#
# Everything went into the history as a string, so putting
# it back means asking the table what type that column
# really is and turning the string into it again. Without
# this a reverted date would land in the column as text.
#--------------------------------

def from_json(model_class, field, value):
    if value is None:
        return None

    column_type = model_class.__table__.columns[field].type.__class__.__name__

    if column_type == "Date":
        return date.fromisoformat(value)

    if column_type == "DateTime":
        return datetime.fromisoformat(value)

    if column_type == "Numeric":
        return Decimal(str(value))

    if column_type == "Integer":
        return int(value)

    if column_type == "Boolean":
        return bool(value)

    return value


#--------------------------------
# APPLYING AN UPDATE AND NOTING WHAT CHANGED
#
# updates is a plain dict of column name to new value. Only
# the keys whose value is genuinely different end up in the
# history, so an untouched field never shows as an edit.
#--------------------------------

def apply_updates(record, updates):
    previous_values = {}
    new_values = {}

    for field, new_value in updates.items():
        old_value = getattr(record, field)

        if old_value == new_value:
            continue

        previous_values[field] = to_json(old_value)
        new_values[field] = to_json(new_value)

        setattr(record, field, new_value)

    return previous_values, new_values


#--------------------------------
# ONLY THE KEYS THE CALLER ACTUALLY SENT
#
# Every step schema is almost all Optional, so a missing key
# and a key deliberately set to null look the same once the
# schema is built. exclude_unset tells them apart, and only
# what was sent gets written.
#--------------------------------

def sent_fields(schema, ignore=None):
    ignore = ignore or []
    values = schema.model_dump(exclude_unset=True)

    return {
        field: value
        for field, value in values.items()
        if field not in ignore
    }


#--------------------------------
# WRITING A HISTORY ROW
#
# Nothing is written when nothing changed, otherwise the
# history fills up with rows that say a user opened a form
# and pressed save.
#--------------------------------

def record_change(consignment_id, previous_values, new_values, user_id, db,
                  change_type=ChangeType.UPDATE.value, is_revert=False):

    if not previous_values and not new_values:
        return None

    change = ConsignmentChangeHistory(
        consignment_id=consignment_id,
        change_type=change_type,
        previous_values=previous_values,
        new_values=new_values,
        changed_by_id=user_id,
        is_revert=is_revert
    )

    db.add(change)

    return change


#--------------------------------
# NAMING A CHILD ROW INSIDE THE HISTORY
#
# The history hangs off the consignment, so an item or a
# payment field is stored as "item.7.unit_price". That keeps
# one readable trail per consignment instead of three.
#--------------------------------

def prefix_fields(prefix, row_id, values):
    return {
        prefix + "." + str(row_id) + "." + field: value
        for field, value in values.items()
    }
