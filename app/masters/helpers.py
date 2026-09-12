from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.imports.models import (
    Consignment, ConsignmentBatchGroup, ConsignmentItem, ConsignmentOrderItem,
)
from app.logistics.models import LogisticsConsignment
from app.masters.models import HsCode, Item
from app.trucking.models import TruckingConsignment

#-----------------------------------------------------
# SMALL JOBS EVERY MASTERS ROUTE NEEDS
#
# Fetching a row, checking a name is not already taken, and
# working out how many consignments each record is used by.
#-----------------------------------------------------


#--------------------------------
# VALIDATE A BODY AGAINST A MASTER'S SCHEMA
#
# One route serves all six lists, so the body arrives as a
# plain dict and is checked against the right schema by
# hand. A bad body has to come back as a 422, the same as it
# would if FastAPI had validated it, not fall through to a
# 500.
#--------------------------------

def parse_payload(schema, payload):
    try:
        return schema(**payload)

    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "field": ".".join(str(part) for part in error["loc"]),
                    "message": error["msg"]
                }
                for error in e.errors()
            ]
        )


#--------------------------------
# SEARCH ITEMS BY NAME OR CODE FOR DATA ENTRY
#
# Feeds the item typeahead on the consignment wizard.
# As the operator types, the matching active items come
# back with everything the form auto-fills: the code, the
# default specification and unit, and the H.S. codes
# (an item can have several, so it is a list).
#
# Matches the CODE as well as the name. It was name-only,
# which left the wizard's item-code field with nothing to
# search against — and the code is the half an operator
# usually has in front of them, off a requisition or an
# invoice. Both are matched with one OR rather than a
# second endpoint, so a typeahead can be pointed at either
# field and behave the same.
#
# Unverified items are included, because an item created
# inline a moment ago must be findable straight away. Only
# a handful come back, since it is a live typeahead.
#--------------------------------

def search_items(db, q, limit):
    query = select(Item).where(Item.is_active == True)

    if q:
        pattern = "%" + q.strip() + "%"
        query = query.where(
            or_(
                Item.name.ilike(pattern),
                Item.item_code.ilike(pattern),
            )
        )

    query = query.options(
        selectinload(Item.hs_codes)
    ).order_by(Item.name).limit(limit)

    return db.execute(query).scalars().all()


#--------------------------------
# FETCH A ROW OR SAY IT IS NOT THERE
#
# Masters are never hard deleted, only deactivated, so a
# fetch returns inactive rows too. The list screen hides
# them, but an edit or a reactivate has to be able to reach
# them.
#--------------------------------

def get_row(model, row_id, db):
    row = db.execute(
        select(model).where(model.id == row_id)
    ).scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Record not found"
        )

    return row


#--------------------------------
# NAMES ARE UNIQUE, SO CHECK BEFORE SAVING
#
# The database would refuse a duplicate anyway, but catching
# it here gives a plain message instead of a 500. On an edit
# the row being edited is allowed to keep its own name.
#--------------------------------

def check_unique(model, field, value, db, ignore_id=None):
    if value is None:
        return

    column = getattr(model, field)

    query = select(model).where(column == value)

    if ignore_id is not None:
        query = query.where(model.id != ignore_id)

    clash = db.execute(query).scalar_one_or_none()

    if clash is not None:
        raise HTTPException(
            status_code=400,
            detail="A record with this " + field + " already exists"
        )


#--------------------------------
# HOW MANY CONSIGNMENTS USE EACH RECORD
#
# The masters screen shows a "used in" count so nobody
# deactivates something the business is still leaning on.
# One grouped query per list rather than one per row.
#
# Only live consignments are counted. A deleted one is not a
# reason to keep a supplier active.
#
# Ports and items are the odd ones out. A port can be a
# consignment's loading port or its delivery port, and an
# item is reached through the item lines, so both are
# tallied in python from the rows that reference them.
#--------------------------------

def used_counts(master, ids, db):
    counts = {row_id: 0 for row_id in ids}

    if not ids:
        return counts

    # SUPPLIER AND BRANCH COUNT ORDERS, NOT SHIPMENTS.
    #
    # Both columns now live on the batch GROUP (the LC), so the count is over
    # `consignment_batch_groups` and one row there is one order however many
    # batches it arrived in. Counting `consignments` instead would inflate a
    # supplier's usage every time one of its orders was split across two
    # shipments — the same supplier, the same agreement, counted twice.
    #
    # Branch reads `works_branch_id`, the group's header-level branch, which is
    # the successor to both `Consignment.works` and `Consignment.branch_id`.
    # NOT `consignment_order_items.branch_id`: items carry their own branch for
    # display, and nothing in the app aggregates on it — every branch total is
    # one-branch-per-order, deliberately (design section 3.3).
    if master == "supplier":
        return _grouped_count(ConsignmentBatchGroup.supplier_id, ids, db, counts)

    if master == "branch":
        return _grouped_count(ConsignmentBatchGroup.works_branch_id, ids, db, counts)

    if master == "customer":
        # The only master counted against LOGISTICS orders rather than import
        # consignments — customers are who the business ships TO.
        rows = db.execute(
            select(
                LogisticsConsignment.customer_id,
                func.count(LogisticsConsignment.id),
            )
            .where(LogisticsConsignment.is_deleted == False)
            .where(LogisticsConsignment.customer_id.in_(ids))
            .group_by(LogisticsConsignment.customer_id)
        ).all()

        for row_id, count in rows:
            counts[row_id] = count

        return counts

    if master == "works":
        # Works is no longer exposed as a master (it is the same thing as
        # Branch), but the branch is left here so an older caller cannot crash.
        return counts

    # THE CLEARING AGENT COUNTS SHIPMENTS, and it is the odd one out on purpose.
    #
    # `clearing_agent_id` stays on the batch: a different agent per shipment is
    # normal, so it is a per-arrival fact rather than a term of the order. An
    # agent who cleared two batches of one LC did two clearances, and this count
    # exists so nobody deactivates a master the business is still leaning on —
    # understating usage there fails in the dangerous direction.
    if master == "agent":
        return _grouped_count(Consignment.clearing_agent_id, ids, db, counts)

    if master == "transporter":
        # Counted against TRUCKING jobs, not import consignments — a
        # transporter is who moves a trucking job, so _grouped_count (which
        # is wired to Consignment) does not fit here.
        rows = db.execute(
            select(
                TruckingConsignment.transporter_id,
                func.count(TruckingConsignment.id),
            )
            .where(TruckingConsignment.is_deleted == False)
            .where(TruckingConsignment.transporter_id.in_(ids))
            .group_by(TruckingConsignment.transporter_id)
        ).all()

        for row_id, count in rows:
            counts[row_id] = count

        return counts

    if master == "port":
        rows = db.execute(
            select(Consignment.loading_port_id, Consignment.delivery_port_id)
            .where(Consignment.is_deleted == False)
            .where(
                or_(
                    Consignment.loading_port_id.in_(ids),
                    Consignment.delivery_port_id.in_(ids),
                )
            )
        ).all()

        for loading_id, delivery_id in rows:
            for port_id in {loading_id, delivery_id}:
                if port_id in counts:
                    counts[port_id] += 1

        return counts

    if master == "item":
        # `item_id` is on the ORDER LINE now, so the join runs line -> order
        # line rather than reading it off the line directly. Still counted per
        # CONSIGNMENT (distinct consignment_id), unchanged: this is "how many
        # shipments carried this item", and the unit did not move with the
        # column.
        rows = db.execute(
            select(ConsignmentOrderItem.item_id, ConsignmentItem.consignment_id)
            .select_from(ConsignmentItem)
            .join(ConsignmentOrderItem,
                  ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
            .join(Consignment, Consignment.id == ConsignmentItem.consignment_id)
            .where(Consignment.is_deleted == False)  # noqa: E712
            .where(ConsignmentOrderItem.item_id.in_(ids))
            .distinct()
        ).all()

        for item_id, _consignment_id in rows:
            if item_id in counts:
                counts[item_id] += 1

        return counts

    return counts


def _grouped_count(column, ids, db, counts):
    """"Used in N" for one master column, counting whatever that column hangs off.

    THE UNIT FOLLOWS THE COLUMN, which is why the model is read off the column
    rather than hardcoded to `Consignment` as it used to be. A column on
    `consignment_batch_groups` counts ORDERS; one on `consignments` counts
    SHIPMENTS. See the call sites above — supplier and branch are the first,
    the clearing agent is the second, and the difference is real rather than
    stylistic.
    """
    model = column.parent.class_
    rows = db.execute(
        select(column, func.count(model.id))
        .where(model.is_deleted == False)  # noqa: E712
        .where(column.in_(ids))
        .group_by(column)
    ).all()

    for row_id, count in rows:
        counts[row_id] = count

    return counts


#--------------------------------
# REPLACE AN ITEM'S H.S. CODES
#
# The codes come in as the full list the item should now
# have. Ones already stored stay, new ones are added and
# ones no longer in the list are switched off.
#
# Nothing is deleted. A code dropped from the list is only
# deactivated, so a past consignment line that cleared under
# it still means something, and a code brought back later is
# just switched on again rather than inserted a second time,
# which would trip the one-code-per-item rule.
#--------------------------------

def set_hs_codes(item, codes, db):
    wanted = []

    for code in codes:
        cleaned = code.strip()

        if cleaned and cleaned not in wanted:
            wanted.append(cleaned)

    existing = {row.code: row for row in item.hs_codes}

    for code, row in existing.items():
        if code not in wanted and row.is_active:
            row.is_active = False

    for code in wanted:
        if code in existing:
            existing[code].is_active = True
        else:
            db.add(HsCode(item_id=item.id, code=code))
