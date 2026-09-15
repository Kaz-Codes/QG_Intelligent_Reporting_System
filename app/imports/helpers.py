from app.imports.models import (
    Consignment, ConsignmentItem, Payment, ConsignmentChangeHistory,
    ConsignmentBatchGroup, ConsignmentOrderItem,
)
from sqlalchemy import select, func, or_, and_, not_, update, literal
from sqlalchemy.orm import joinedload, selectinload
from app.imports.serializers import serialize_many
from app.imports.models import ConsignmentChangeHistory, EtaRevisionHistory, StatusUpdateHistory

from app.enums import Status
from app.masters.models import Branch, Item, Supplier
from sqlalchemy import select
from datetime import datetime, timezone, date
from sqlalchemy.inspection import inspect
from decimal import Decimal
from app.imports.order_view import (
    consignment_number, line_item_code, line_item_name, line_specification,
    line_unit_price, order_exchange_rate, order_instrument_number,
)
# THE ALLOCATION INVARIANT lives in its own module for the same reason
# order_view does - it imports models and nothing else, so every caller can
# reach it. Re-exported here because the routes already import their write-path
# helpers from this module and splitting that across two imports for one
# concern would only make the call sites longer.
from app.imports.allocation import (  # noqa: F401
    AllocationError, OrderLineHasNoQuantity, OverAllocation, UnknownOrderLine,
    allocation_totals, allocation_view, lock_order_lines, reconcile_allocation,
)

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
def split_consignment_payload(payload):
    """Sort one flat consignment payload into the three rows it now describes.

    Returns (consignment_fields, group_fields, order_item_fields).

    THE UNROUTABLE CASE RAISES. A payload key that is not a `Consignment`
    column, not in either destination map and not a known retirement is a real
    defect - a field the client believes in that the server has never had - and
    the one thing it must not do is vanish. That is exactly how the group's copy
    went stale for a week: `updated_fields` filtered against the mapper and
    `continue`d on a miss, so twelve fields stopped being saved with no error
    anywhere.
    """
    consignment_columns = {c.key for c in Consignment.__mapper__.column_attrs}

    consignment_fields, group_fields, order_item_fields = {}, {}, {}
    unknown = []

    for key, value in payload.items():
        # EVERY destination is taken, not the first one that matches. `branch_id`
        # has two (the group's works_branch_id and every order line's branch_id),
        # and an elif chain would silently take one - which is a half-write, the
        # same shape as the half-undo this routing exists to prevent.
        routed = False

        if key in consignment_columns:
            consignment_fields[key] = value
            routed = True
        if key in PAYLOAD_TO_GROUP:
            group_fields[PAYLOAD_TO_GROUP[key]] = value
            routed = True
        if key in PAYLOAD_TO_ORDER_ITEM:
            order_item_fields[PAYLOAD_TO_ORDER_ITEM[key]] = value
            routed = True
        if key in RETIRED_PAYLOAD_FIELDS:
            routed = True

        if not routed:
            unknown.append(key)

    if unknown:
        raise ValueError(
            f"Consignment payload carries field(s) that belong to no table: "
            f"{', '.join(sorted(unknown))}. They were not saved. If a column "
            f"was retired, add it to RETIRED_PAYLOAD_FIELDS with the reason; if "
            f"it moved, add it to PAYLOAD_TO_GROUP or PAYLOAD_TO_ORDER_ITEM."
        )

    return consignment_fields, group_fields, order_item_fields


def create_consignment_object(consignment_data, user):
    """The batch row only. Its order and its order lines are built after it.

    `Consignment(**payload)` used to work because the payload and the table were
    the same shape. They are not any more: twelve of these keys now belong to
    the order and two to the order line, and passing them here is a TypeError.
    """
    payload = consignment_data.model_dump(
        exclude_none=True, exclude={"items", "payments"}
    )

    consignment_fields, _group, _order_item = split_consignment_payload(payload)
    consignment_fields["created_by_id"] = user.id

    return Consignment(**consignment_fields)


#--------------------------------------
# CREATING AN OBJECT FOR 
# CONSIGNMENT ITEM
#--------------------------------------

def split_item_payload(payload):
    """Sort one posted item into the shipment line and the order line.

    Returns (line_fields, order_item_fields).

    The same routing as `split_consignment_payload`, one level down, and it
    raises for the same reason: a key belonging to neither table is a field the
    client believes in and the server has never had, and dropping it silently is
    how the header copy went stale unnoticed.
    """
    line_columns = {c.key for c in ConsignmentItem.__mapper__.column_attrs}
    order_item_columns = {c.key for c in ConsignmentOrderItem.__mapper__.column_attrs}

    line_fields, order_item_fields, unknown = {}, {}, []

    for key, value in payload.items():
        if key in line_columns:
            line_fields[key] = value
        elif key in order_item_columns:
            order_item_fields[key] = value
        else:
            unknown.append(key)

    if unknown:
        raise ValueError(
            f"Consignment item payload carries field(s) that belong to no "
            f"table: {', '.join(sorted(unknown))}. They were not saved."
        )

    return line_fields, order_item_fields


def create_consignment_item_object(consignment_data):
    """One (shipment line, order-line fields) pair per posted item.

    RETURNS PAIRS, NOT OBJECTS. `ConsignmentItem(**item_dict)` used to be enough
    because the payload and the table matched; thirteen of those keys are the
    order line's now, so the routed half travels alongside the object until
    `sync_order_items` writes it.
    """
    pairs = []

    for item in consignment_data.items:
        line_fields, order_item_fields = split_item_payload(item.model_dump())
        pairs.append((ConsignmentItem(**line_fields), order_item_fields))

    return pairs


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
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.supplier),
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.works_branch),
        # THE ORDER'S LINES - what was bought, against which this batch's lines
        # are allocations. `serialize_consignment` publishes the allocation
        # panel from these on the DETAIL payload; without the chain it is a
        # query per order line every time a consignment is opened.
        # `selectinload`, not `joinedload`: this is a collection hanging off a
        # collection's parent, and joining it would multiply the rows.
        joinedload(Consignment.batch_group)
            .selectinload(ConsignmentBatchGroup.order_items),
        joinedload(Consignment.loading_port),
        joinedload(Consignment.delivery_port),
        joinedload(Consignment.clearing_agent),

        # THE ORDER LINE BEHIND EVERY SHIPMENT LINE. `serialize_items` reads
        # through `item.order_item` for the thirteen columns that moved there
        # in part 4, so without this chain every line lazy-loads its order line
        # one query at a time - an N+1 on every detail fetch, introduced by
        # repointing the reads without repointing the load beside them.
        selectinload(Consignment.items).selectinload(ConsignmentItem.order_item),
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
        # The header branch is the ORDER's works_branch now.
        conditions.append(Consignment.batch_group.has(
            ConsignmentBatchGroup.works_branch_id.in_(branch_id)
        ))

    if supplier_id:
        conditions.append(Consignment.batch_group.has(
            ConsignmentBatchGroup.supplier_id.in_(supplier_id)
        ))

    if requisition_type:
        # THE JOIN IS THE WHOLE FILTER. `requisition_type` moved to the order
        # line in part 4; the column name here was repointed onto
        # ConsignmentOrderItem and the join was not added, which does not error
        # - SQLAlchemy puts the second table in the FROM clause with no
        # condition and emits a CARTESIAN PRODUCT:
        #
        #     FROM consignment_items, consignment_order_items
        #    WHERE consignment_order_items.requisition_type IN (...)
        #
        # That subquery returns every consignment_id that has any line at all,
        # whenever ANY order item in the table carries the requested type.
        # Measured through the route, against a clone of production: BOTH of
        # the two types in use returned all 179 live consignments. The correct
        # answers are 1 for "Others" and 0 for "Store" - so the filter reported
        # the whole book under a type NOTHING live actually carries.
        conditions.append(
            Consignment.id.in_(
                select(ConsignmentItem.consignment_id)
                .join(ConsignmentOrderItem,
                      ConsignmentOrderItem.id == ConsignmentItem.order_item_id)
                .where(ConsignmentItem.is_deleted == False)  # noqa: E712
                .where(ConsignmentOrderItem.requisition_type.in_(requisition_type))
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
            Consignment.gd_number.ilike(pattern),
            # Everything the ORDER identifies itself by, in one subquery: the
            # payment reference, the origin, the supplier and the works/branch.
            #  (free text) is gone - works_branch is its successor, and
            # searching the dead column would match only rows the loader left
            # NULL, which is all of them.
            Consignment.batch_group.has(or_(
                ConsignmentBatchGroup.instrument_number.ilike(pattern),
                ConsignmentBatchGroup.origin.ilike(pattern),
                ConsignmentBatchGroup.supplier.has(Supplier.name.ilike(pattern)),
                ConsignmentBatchGroup.works_branch.has(Branch.name.ilike(pattern)),
            )),
            # THE ITEM FIELDS ARE REACHED THROUGH `.has()`, NOT NAMED BARE.
            #
            # These three columns live on the ORDER line since part 4. Naming
            # ConsignmentOrderItem directly inside `.any()` compiled to
            #
            #     EXISTS (SELECT 1 FROM consignment_items, consignment_order_items
            #              WHERE consignments.id = consignment_items.consignment_id
            #                AND consignment_items.is_deleted = false
            #                AND consignment_order_items.item_name ILIKE ...)
            #
            # - a cartesian product, true for every consignment that has a live
            # line as soon as ANY order item anywhere matched. Searching for an
            # item name returned the whole list (179 of 179 live rows), which
            # reads as "search is broken" in the good case and as a trustworthy
            # filtered set in the bad one.
            #
            # `order_item.has(...)` nests a second correlated EXISTS carrying
            # the join condition, so the match is against THIS line's order
            # line. `.join()` is not available inside `.any()`.
            Consignment.items.any(
                (ConsignmentItem.is_deleted == False) &  # noqa: E712
                ConsignmentItem.order_item.has(
                    or_(
                        ConsignmentOrderItem.item_name.ilike(pattern),
                        ConsignmentOrderItem.item_code.ilike(pattern),
                        ConsignmentOrderItem.reference_number.ilike(pattern),
                    )
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
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.supplier),
        joinedload(Consignment.batch_group).joinedload(ConsignmentBatchGroup.works_branch),
        joinedload(Consignment.loading_port),
        joinedload(Consignment.delivery_port),
        joinedload(Consignment.clearing_agent),

        # As in fetch_consignment: the list serializes every line through
        # `item.order_item`, so one query per LINE per PAGE without this.
        selectinload(Consignment.items).selectinload(ConsignmentItem.order_item),
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


#---------------------------------------------------------------------------
# WHICH ORDERS STILL HAVE QUANTITY NOBODY HAS PUT IN A BATCH
#
# The requirements want the list to highlight a consignment whose order has
# items pending allocation (requirements, Step 3 - "a blue highlighted line").
#
# A BOOLEAN COMPUTED IN SQL, NOT THE `allocation` BLOCK. `allocation_view`
# reads `group.order_items`, which the list query deliberately does not load;
# publishing it per row would be one collection load per row for a panel the
# list does not draw, which is exactly the N+1 the eager loads closed.
#
# IT IS A PROPERTY OF THE ORDER, NOT OF THE ROW. Every batch of an
# under-allocated order reports true, which is right: the pending quantity
# belongs to the ORDER, and hiding it on all but one batch would mean whether
# you saw it depended on which arrival you happened to be looking at.
#
# PAID ONLY WHEN ASKED FOR. `include_batch_context=False` skips the subquery
# entirely rather than computing it and discarding it - the list already runs a
# count plus a page plus five eager loads, and this is a correlated EXISTS over
# a second table that only one screen needs.
#---------------------------------------------------------------------------

HAS_PENDING_ALLOCATION = (
    select(literal(1))
    .select_from(ConsignmentOrderItem)
    .where(ConsignmentOrderItem.batch_group_id == Consignment.batch_group_id)
    .where(ConsignmentOrderItem.is_deleted.is_(False))
    # STRICTLY LESS THAN. Equal is fully allocated and must not highlight;
    # greater than cannot happen (ck_allocation_within_order), and if it ever
    # did, a row that is over-allocated is not "pending" and the allocation
    # check is the thing that should be complaining, not the list.
    .where(ConsignmentOrderItem.allocated_quantity
           < ConsignmentOrderItem.ordered_quantity)
    .correlate(Consignment)
    .exists()
)


def pending_allocation_ids(db, consignments):
    """Which of these consignments belong to an under-allocated order.

    Returned as a set of consignment ids rather than attached to the rows,
    because the rows are ORM objects the serializer walks by mapper - hanging a
    computed attribute on them is how a field ends up in one payload and not
    another depending on which query built it.

    ONE QUERY FOR THE WHOLE PAGE, not one per row. The alternative reads
    naturally (`any(o.outstanding for o in c.batch_group.order_items)`) and is
    twenty lazy loads on a twenty-row page.
    """
    if not consignments:
        return set()

    ids = [c.id for c in consignments]
    rows = db.execute(
        select(Consignment.id)
        .where(Consignment.id.in_(ids))
        .where(HAS_PENDING_ALLOCATION)
    ).scalars().all()

    return set(rows)


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
    """What this save changes, split by which row now owns each field.

    Returns (consignment_changes, group_changes, order_item_changes) — each a
    {field: {old_value, new_value}} dict against the object that field belongs
    to, so each is diffed against the value actually stored rather than against
    a stale copy on the consignment.

    IT USED TO RETURN ONE DICT AND SILENTLY DROP ANYTHING THE MAPPER DID NOT
    HAVE. That `continue` was correct while the payload and the table were the
    same shape, and became a data-loss bug the moment twelve fields moved to the
    order: the wizard kept posting them, the diff kept skipping them, and
    nothing errored. Unroutable keys now raise, in split_consignment_payload.

    THE CHANGE HISTORY KEEPS FLAT KEYS. A group field is recorded as
    `supplier_id`, not `group.supplier_id` — because section 4.7 item 3 says
    stored history is never rewritten, so old rows already use the flat form,
    and giving new rows a second shape would leave revert two formats to parse.
    Where a key lands is decided at REVERT time by the same maps used here.
    """
    payload = update_consignment_data.model_dump(
        exclude_none=True, exclude={"items", "payments", "consignment_id"}
    )

    consignment_fields, group_fields, order_item_fields = \
        split_consignment_payload(payload)

    group = consignment.batch_group

    def diff(target, fields, key_for=None):
        """{payload key: {old, new}} for whatever actually changed on `target`.

        `key_for` maps a DESTINATION column back to the PAYLOAD key the history
        must record it under, and it exists for one field: the payload says
        `branch_id` and the group's column is `works_branch_id`.

        RECORDING THE DESTINATION NAME IS A BUG, AND IT WAS ONE. The history
        held `works_branch_id`; revert routes on payload keys, so that key
        matched nothing, raised, and the entire undo failed - not just the
        branch. For the other ten group fields the key and the column are the
        same word, so it stayed invisible until a branch change was
        round-tripped through write-then-revert.

        The rule both sides share: THE HISTORY RECORDS WHAT THE USER CHANGED,
        in the words the client used. WHERE it lives is the maps' job, on the
        way in and on the way back out.
        """
        out = {}
        if target is None:
            return out
        for field, new_value in fields.items():
            old_value = getattr(target, field, None)
            if new_value == old_value:
                continue
            out[(key_for or {}).get(field, field)] = {
                "old_value": old_value, "new_value": new_value
            }
        return out

    # destination column -> payload key, for the history's benefit.
    group_key_for = {dest: key for key, dest in PAYLOAD_TO_GROUP.items()}

    # The order-line fields are header-level in the payload and per-item in the
    # model, so there is no single "old value" to diff against — one posted
    # value fans out to every line. They are returned undiffed and applied by
    # sync_order_item_from_line, which already does exactly that fan-out.
    return (diff(consignment, consignment_fields),
            diff(group, group_fields, key_for=group_key_for),
            order_item_fields)

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
    # SCOPED TO THIS CONSIGNMENT, which is what makes it safe on a split order:
    # a save of batch 2 can only ever soft-delete batch 2's own lines, so a line
    # absent from batch 2's payload cannot take a sibling's line with it. The
    # ORDER line above them survives either way - `reconcile_allocation` retires
    # one only when the last live line across the whole order goes.
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
    


def item_current_values(item):
    """One line's stored values, ACROSS BOTH of its rows.

    A shipment line and the order line above it are one thing to the person
    editing, and the payload is flat, so the diff needs a flat view of what is
    stored. `serialize_many` alone cannot give one: it walks the MAPPER, so it
    returns only the columns `ConsignmentItem` still has and silently omits the
    thirteen that moved. Diffing against that view raised KeyError on the first
    moved field - loud, and only because the payload happens to carry keys the
    view lacks. Had the mismatch gone the other way it would have compared
    nothing and reported no change.
    """
    values = dict(serialize_many([item])[0])

    order_item = item.order_item
    if order_item is not None:
        for column in inspect(order_item).mapper.column_attrs:
            # The line's own columns win: `id`, `is_deleted` and the timestamps
            # exist on both rows and the line's are the ones the payload means.
            values.setdefault(column.key, getattr(order_item, column.key))

    # `ordered_quantity` IS PUBLISHED AND IS DIFFED. It used to be stripped
    # here, along with `allocated_quantity`, on the reasoning that a client with
    # one quantity input should not be shown three. That was right while the
    # two were always equal; it is wrong now that they can differ, and leaving
    # it stripped would have been a quiet trap: `ordered_quantity` is a schema
    # field, so a client can send it, and a field the diff cannot see is a field
    # that is silently never saved - the exact shape of the bug that took
    # twelve group fields out of the write path for a week.
    #
    # `allocated_quantity` IS STILL STRIPPED, and for a different reason: it is
    # derived. Nobody types it, `reconcile_allocation` owns it, and putting it
    # in the diff would let a client post a value that the very next line of the
    # save overwrites. It reaches the client through the `allocation` panel on
    # the detail payload instead, where it is plainly a computed figure.
    for internal in ("allocated_quantity", "batch_group_id"):
        values.pop(internal, None)

    return values


#---------------------------------------------------------------------------
# FIELDS AN ABSENT KEY MUST NOT CLEAR
#
# `ConsignmentItemSchema` defaults every optional field to None, and
# `model_dump()` cannot tell "the client sent null" from "the client never
# mentioned it". The diff below reads both as a change TO null - which is
# deliberate and correct for the ordinary fields, because that is how the
# wizard clears one: `draftToPayload` omits an emptied input rather than
# sending "".
#
# IT IS WRONG FOR THESE TWO, AND IT WAS A 500 ON EVERY EDIT. Both are NOT NULL
# and both are resolved by the SERVER, not typed by anyone:
#
#   * `ordered_quantity` - `resolve_ordered_quantity` owns it, and its whole
#     contract is "None means leave it alone" (case 4). The diff got there
#     first and wrote the NULL before `sync_order_items` could run.
#   * `order_item_id` - `resolve_order_line` owns it, and a line that already
#     has one keeps it.
#
# MEASURED, at c8a450f, against a scratch clone: saving ANY existing
# consignment through the imports wizard - the wizard sends neither key -
# ended in
#
#     UPDATE consignment_order_items SET item_id=NULL, ordered_quantity=NULL
#     NotNullViolation: null value in column "ordered_quantity"
#
# a 500 with nothing saved. Found by driving the browser for step 8; the
# reproduction was replayed against an untouched HEAD worktree to confirm it
# is not step 8's.
#
# WHY NOT `model_dump(exclude_unset=True)` FOR THE WHOLE PAYLOAD. That would
# make every absent key mean "leave it", and clearing a field in the wizard
# works precisely because an emptied input arrives absent. The narrow set is
# the point: absence means "leave it" only where a server-owned column would
# otherwise be destroyed by it.
#---------------------------------------------------------------------------

SERVER_RESOLVED_ITEM_FIELDS = ("ordered_quantity", "order_item_id")


def updated_items(consignment, update_consignment_data, db):
    updated_items_list = []
    items_in_updated_data = update_consignment_data.items
    items_in_consignment = consignment.items

    serialized_dict = {
        item.id: item_current_values(item) for item in items_in_consignment
    }

    for item in items_in_updated_data:
        updation_dict = {}
        consignment_item = None
        item_dict = item.model_dump()
        consignment_item = serialized_dict.get(item_dict["id"])

        # What the client actually SENT, as opposed to what Pydantic defaulted.
        posted = item.model_fields_set

        if consignment_item is not None:

            for field in list(item_dict.keys()):
                # See SERVER_RESOLVED_ITEM_FIELDS above: an absent key here is
                # "leave it", not "set it to null".
                if field in SERVER_RESOLVED_ITEM_FIELDS and field not in posted:
                    continue
                # `.get`, not `[...]`: a payload key that matches no column on
                # either row is caught by split_item_payload when the change is
                # APPLIED, which raises and names it. Here it simply cannot be
                # a change, because there is nothing stored to differ from.
                if field not in consignment_item:
                    continue
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

def apply_group_updates(updation_dict, group, user):
    """Apply a group diff, whose keys are PAYLOAD keys, to the group's columns.

    The one asymmetry in the whole scheme: `branch_id` in, `works_branch_id`
    out. Everything else is the same word on both sides, which is exactly why
    this needs its own function rather than `apply_updates` - a setattr loop
    would write `branch_id` onto the group, where no such column exists, and
    SQLAlchemy would let it: it would set a plain Python attribute, change
    nothing in the database, and report success.

    `user` IS REQUIRED, NOT OPTIONAL, and that is the point of the parameter.
    A default of None would make an un-updated caller silently admin-less or
    silently unchecked depending on which way the default fell; a required
    argument makes every call site declare who is writing, and a caller that
    was missed is a TypeError at import-exercising time rather than a hole.

    THE SECOND LINE OF DEFENCE (design 3.9, and CLAUDE.md on the six write
    paths). `assert_group_writable` has already run at the route; this
    RE-DERIVES the same answer immediately before the setattr rather than
    trusting a flag the caller passed. Section 4.7 records six write paths
    found one at a time, four of them by driving rather than by reading - that
    is precisely the situation in which a second check earns its keep.

    IT RAISES; IT DOES NOT SKIP. Dropping a frozen field quietly and applying
    the rest would be the failure this whole rule exists to prevent, wearing
    the costume of a safety net: the save would return 200 and the operator
    would believe the rate had changed.
    """
    if group is None:
        return

    assert_group_writable(group, user, [
        key for key, change in updation_dict.items()
        if isinstance(change, dict) and "new_value" in change
    ])

    for key, change in updation_dict.items():
        if not (isinstance(change, dict) and "new_value" in change):
            continue
        target = PAYLOAD_TO_GROUP.get(key, key)
        setattr(group, target, change["new_value"])


def apply_item_updates(updation_dict, item):
    """Apply one line's diff to whichever of its two rows owns each field.

    `apply_updates` setattrs everything onto one object, which is right for a
    consignment and wrong for a line: thirteen of the keys in an item diff
    belong to the order line above it. Routed through `split_item_payload`, so
    the write path and this share ONE destination map - two maps that agree
    today are two maps that can disagree later, and they would disagree
    silently, because create and update are exercised by different tests.

    WHAT THIS DOES ON A SPLIT ORDER, checked when step 7 made one possible: the
    order-line half of the diff writes a row every batch of the order shares,
    so editing an item on batch 2 changes what batch 1 shows for it. That is
    correct and is the point of the table - the item's name, code, price and
    demand dates are facts about the ORDER and there is one of each. The change
    history records the edit against the batch it was made on, which is also
    right: somebody did it, from there, and that is who can undo it.

    The one key in that half that can break an invariant is
    `ordered_quantity` - lowering it can leave a sum that was legal too large.
    Both routes that reach here end at `reconcile_allocation`, which refuses.
    """
    changes = {
        field: change["new_value"]
        for field, change in updation_dict.items()
        if isinstance(change, dict) and "new_value" in change
    }

    line_fields, order_item_fields = split_item_payload(changes)

    for field, value in line_fields.items():
        setattr(item, field, value)

    if order_item_fields:
        order_item = item.order_item
        if order_item is not None:
            for field, value in order_item_fields.items():
                setattr(order_item, field, value)


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
        db,
        group_updates=None,
):
    """Record what this save changed, across all three rows.

    `group_updates` IS MERGED INTO "fields" UNDER FLAT KEYS, not nested under a
    "group" collection. Two reasons, and the first one is the load-bearing one:

    1. Every history row written before part 4 already records `supplier_id` and
       `exchange_rate` flat, because they were consignment columns then. Nesting
       new rows differently would leave revert two shapes to parse and a version
       test to get wrong. Section 4.7 item 3 says stored history is never
       rewritten; this is the same principle applied forwards.

    2. Where a key LANDS is decided at revert time, by the same destination maps
       the write path used. The history records WHAT CHANGED; the maps record
       WHERE IT LIVES. Putting the destination in the stored JSON would freeze
       today's answer into every row and break the next time something moves.

    Without this merge the group's changes were applied and never recorded - so
    they could not be reverted, and nothing said so. That is the same silent
    half-success this whole section exists to close, reached from a third
    direction.
    """

    # `item_current_values`, NOT `serialize_many` - the same mapper trap as
    # `serialize_items`, at a different boundary. A ConsignmentItem's mapper no
    # longer carries the thirteen identity/price fields, so serialize_many would
    # store a deleted line as a quantity and a landed cost with no item on it.
    #
    # Nothing READS those keys back on revert (`add_or_delete` touches `id` and
    # `is_deleted` and nothing else), so this is not data loss. It is the stored
    # RECORD going hollow: the change-history screen renders these rows through
    # `itemSummary`, which reads `item_name`, `item_code` and
    # `unit_of_measurement` - so every add/remove card would read "3" where it
    # used to read "Forged Steel Round Bar (IMP-A51A714E) - 3 Pcs".
    #
    # PAYMENTS STAY ON serialize_many, deliberately. Nothing moved out of
    # `payments`; there is no order row above it, so its mapper is still the
    # whole truth about a payment.
    serialized_deleted_items = [item_current_values(item) for item in deleted_items]

    serialized_deleted_payments = serialize_many(deleted_payments)

    updates_history = {
        "fields" : {**(updation_dict or {}), **(group_updates or {})}, 
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

def revert(consignment_history, consignment, db, user=None):
    history = consignment_history.history
    fields = history["fields"]
    items_updates = history["items"]
    payments_updates = history["payments"]
    new_items = history["new_items"]
    new_payments = history["new_payments"]
    deleted_items = history["deleted_items"]
    deleted_payments = history["deleted_payments"]

    # Reverting local fields. Returns {key: reason} for whatever it could not
    # restore - a retired column, or a group field a closed batch has frozen.
    # `user` decides Tier 2: an admin may restore a supplier, nobody may
    # restore a rate.
    skipped = dict(revert_local_fields(consignment, fields, user))

    # Deletig new items added in update
    add_or_delete(new_items, ConsignmentItem, consignment.id, ConsignmentItem.id, db, delete=True)

    # Deleting new payments added in update
    add_or_delete(new_payments, Payment, consignment.id, Payment.id, db, delete=True)

    # Adding deleted items back
    add_or_delete(deleted_items, ConsignmentItem, consignment.id, ConsignmentItem.id, db, delete=False)

    # Adding deleted payments back
    add_or_delete(deleted_payments, Payment, consignment.id, Payment.id, db, delete=False)

    # Reverting already existing items updates
    skipped.update(revert_old_values(items_updates, ConsignmentItem, consignment.id,
                                     ConsignmentItem.id, db))

    # Reverting already existing payments updates
    skipped.update(revert_old_values(payments_updates, Payment, consignment.id,
                                     Payment.id, db))

    # WHAT COULD NOT BE RESTORED GOES BACK TO THE CALLER, and from there into
    # the response. A revert that quietly does less than it says is the bug this
    # whole area exists to close; telling the user "these two fields no longer
    # exist, everything else is back" is the difference between a partial undo
    # and a partial undo NOBODY KNOWS ABOUT. A log line would not be that - it
    # is the same silence with a paper trail nobody reads.
    return skipped


#---------------------------------------
# UNDOING A CHANGE, ACROSS THE THREE ROWS IT MAY HAVE TOUCHED
#
# A history row records WHAT CHANGED, flat, under the key the field had at the
# time. It does not record WHERE the field lived, and it must not: the stored
# JSON is an audit record of what happened, not a derived artefact of the
# current model (section 4.7 item 3). So where a key lands is decided HERE, at
# read time, by the SAME destination maps the write path routes on.
#
# One set of maps, two consumers. Two maps that agree today are two maps that
# drift later, and they would drift silently, because create/update and revert
# are exercised by different tests.
#
# THREE OUTCOMES PER KEY, and the third is the one section 4.7 did not have:
#
#   routed    - the field moved; write it to its new home (possibly more than
#               one, see branch_id)
#   retired   - the column is gone and nothing replaced it. NOT an error, and
#               not silent either: the revert succeeds, restores everything
#               else, and REPORTS what it could not restore. A logged warning
#               would be the original bug wearing a hat.
#   unknown   - matches nothing anywhere. A real defect. Raises, named.
#---------------------------------------

# Keys that appear in old history rows for columns that have been retired with
# no successor. Each entry names what retired it and when, because a set with
# unexplained members becomes the place keys go when nobody wants to work out
# where they belong.
RETIRED_HISTORY_KEYS = {
    # Free text for the factory. Superseded by the group's `works_branch_id`
    # (part 4; section 3.3) - Works and Branch were always one thing to the
    # business. It is NULL on every row that ever had it, so the two history
    # rows carrying it restore nothing of value; the MECHANISM is what matters,
    # because po_date and every future retirement arrive down this same path.
    "works": "retired in part 4 - the order's works_branch_id replaced it",
}


def revert_local_fields(consignment, fields, user=None):
    """Restore a consignment's header fields, wherever they now live.

    Returns the list of keys it deliberately could NOT restore, so the caller
    can tell the user. An empty list means everything came back.

    A FROZEN GROUP FIELD IS SKIPPED, NOT FATAL - design 3.9, decided after the
    survey. Refusing the whole revert was the other candidate and is wrong for
    one reason: a history row mixing a frozen field with ordinary ones would
    become permanently un-revertable, and the operator would get nothing back
    at all rather than everything the rule actually permits. Tier 1 has no
    override, so "come back later as an admin" is not an answer there.

    IT REUSES THE RETIRED-KEY CHANNEL because that channel already means
    exactly this: "the revert succeeded, here is what could not be put back and
    why". The two reasons differ (a retired column no longer exists; a frozen
    one is deliberately protected) so they carry different explanations, but
    the mechanism - restore the rest, report the remainder, never fail silently
    - is the same one, and a second reporting path would be a second thing to
    keep in agreement.
    """
    consignment_columns = {c.key for c in inspect(consignment).mapper.column_attrs}
    group = getattr(consignment, "batch_group", None)

    skipped = {}
    unknown = []

    for key, change in fields.items():
        if not (isinstance(change, dict) and "old_value" in change):
            continue

        old_value = change["old_value"]

        # THE FREEZE IS CHECKED FIRST, AND SKIPS THE KEY WHOLE - every
        # destination it has, not only the group one.
        #
        # `branch_id` is the reason that matters. It is the one payload key with
        # TWO destinations (the group's works_branch_id AND every order line's
        # branch_id), so restoring the line half while the group half is frozen
        # would leave the header saying one branch and its lines another - the
        # exact divergence the fan-out exists to prevent, created by the safety
        # rule. Skipping a key wholly is the only self-consistent answer.
        if key in PAYLOAD_TO_GROUP and group is not None:
            if frozen_violations(group, user, [key]):
                skipped[key] = frozen_reason(group, user, key)
                continue

        routed = False

        if key in consignment_columns:
            setattr(consignment, key,
                    coerce_value(Consignment, key, old_value))
            routed = True

        # THE SAME MAPS THE WRITE PATH USES, so a field cannot be written to one
        # place and restored to another. `coerce_value` takes the DESTINATION
        # model, not Consignment: the column it looks the type up in has to be
        # the one being written, or a Numeric restored onto the group would be
        # coerced against a type the group does not have.
        if key in PAYLOAD_TO_GROUP and group is not None:
            target = PAYLOAD_TO_GROUP[key]
            setattr(group, target,
                    coerce_value(ConsignmentBatchGroup, target, old_value))
            routed = True

        if key in PAYLOAD_TO_ORDER_ITEM:
            target = PAYLOAD_TO_ORDER_ITEM[key]
            # Fans out to every live line, exactly as the write path does.
            # See the note on PAYLOAD_TO_ORDER_ITEM: this OVERWRITES per-item
            # values, which is correct only while nothing can set them
            # individually.
            for line in consignment.items:
                if line.is_deleted or line.order_item is None:
                    continue
                setattr(line.order_item, target,
                        coerce_value(ConsignmentOrderItem, target, old_value))
            routed = True

        if key in RETIRED_HISTORY_KEYS:
            skipped[key] = RETIRED_HISTORY_KEYS[key]
            routed = True

        if not routed:
            unknown.append(key)

    if unknown:
        raise ValueError(
            f"Change history for consignment {getattr(consignment, 'id', '?')} "
            f"holds field(s) that belong to no table: {', '.join(sorted(unknown))}. "
            f"Nothing was reverted. If a column was retired, add it to "
            f"RETIRED_HISTORY_KEYS with the reason."
        )

    return skipped


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
    """Restore child rows, routing each key to whichever table now owns it.

    Returns the keys it deliberately could not restore, like its header twin.

    THIS HAD THE IDENTICAL BUG AND NO LOUD FAILURE AT ALL. It walked the child's
    mapper and applied whatever matched, so once the thirteen item attributes
    moved to `consignment_order_items` every one of them would have been skipped
    in silence - an item revert reporting success having restored the quantity
    and the landed cost and nothing else. Phase 1 hardened only the header half.

    Routing uses `split_item_payload`, the SAME function the write path uses, so
    a field cannot be written to one table and restored to another.
    """
    skipped = {}

    for data in updated_data:
        data_id = data.get("id")
        if not data_id:
            continue

        row = db.execute(
            select(model)
            .where(model.consignment_id == consignment_id)
            .where(id_column == data_id)
        ).scalar_one_or_none()

        if row is None:
            continue

        changes = {
            key: change["old_value"]
            for key, change in data.items()
            if isinstance(change, dict) and "old_value" in change  # skips the bare "id"
        }

        # PAYMENTS AND OTHER CHILDREN ARE NOT SPLIT. Only ConsignmentItem has an
        # order line above it; a Payment's history keys all still belong to
        # Payment, so routing it through split_item_payload would be wrong.
        if model is not ConsignmentItem:
            for key, old_value in changes.items():
                if key in {c.key for c in inspect(row).mapper.column_attrs}:
                    setattr(row, key, coerce_value(model, key, old_value))
            continue

        retired = {k: v for k, v in changes.items() if k in RETIRED_HISTORY_KEYS}
        routable = {k: v for k, v in changes.items() if k not in retired}
        # The reason travels WITH the key. It used to be a bare list and the
        # route looked each one up in RETIRED_HISTORY_KEYS - which stops working
        # the moment a second kind of skip exists (a frozen field is not a
        # retired column and carries a different explanation), and stops
        # working by raising KeyError inside the success path.
        skipped.update({k: RETIRED_HISTORY_KEYS[k] for k in retired})

        # Raises, naming the keys, on anything belonging to neither table.
        line_fields, order_item_fields = split_item_payload(routable)

        for key, old_value in line_fields.items():
            setattr(row, key, coerce_value(ConsignmentItem, key, old_value))

        if order_item_fields:
            order_item = row.order_item
            if order_item is not None:
                for key, old_value in order_item_fields.items():
                    setattr(order_item, key,
                            coerce_value(ConsignmentOrderItem, key, old_value))

    return skipped


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


#---------------------------------------------------------------------------
# THE GROUP FREEZE - design section 3.9
#
# A batch closing does not only lock that batch. It settles the ORDER's terms,
# because money has already moved against them: batch 1 closes at rate 278.50,
# its `pkr_total` is stored and reported, and somebody then edits the GROUP's
# rate to 281.00 to book batch 3 correctly. Batch 1's stored total does not move
# - its update route 423s - so the group now says one thing and the stored
# figure says another, and neither is wrong for its own basis. That is
# CLAUDE.md's "one metric, one definition" failure reached from a new direction.
#
# IT IS LIVE TODAY, NOT PREPARATION FOR STEP 8b. `PUT /consignments/{id}` on any
# open batch of a split order already reaches every one of these columns; step 7
# opened it when it made splitting possible through the API. Nobody has hit it
# because nobody can split from the UI yet, which is luck rather than safety.
#
# TWO TIERS, AND THE FIELD SETS ARE IN *COLUMN* SPACE.
#
# Section 3.9's sketch lists `works_branch_id`, which is the COLUMN; the payload
# key for it is `branch_id` (PAYLOAD_TO_GROUP). Comparing an incoming payload
# key against a set of column names would therefore never match on branch, and
# the freeze would have a hole in exactly the field a works change goes through.
# So the sets below are columns, and every caller routes its keys through
# PAYLOAD_TO_GROUP first - the same map the write path and both revert paths
# already route on, so there is no second spelling of where a field goes.
#---------------------------------------------------------------------------

# TIER 1 - NOBODY, INCLUDING AN ADMIN.
#
# The valuation inputs. Changing one after a batch has closed restates that
# batch's stored pkr_total, which is precisely what CLAUDE.md rule 4 exists to
# prevent: "the money totals are STORED (recomputed on save) so a later rate
# change or edit can't restate a printed report". A rate that has been reported
# against is a historical fact, not a field; a genuinely rebooked rate applies
# to the NEXT LC, not retrospectively to this one.
HARD_FROZEN = frozenset({
    "exchange_rate", "rate_booked_on", "rate_source", "currency",
})

# TIER 2 - FROZEN FOR NORMAL USERS, an admin may still write them.
#
# Commercial facts rather than valuation inputs: who the counterparty is and on
# what terms. None feeds a stored money total, and correcting a wrong one on a
# three-batch LC is normal work rather than an exceptional recovery - the record
# should not stay permanently wrong because one shipment landed. They freeze
# against casual edits; an admin is the deliberation.
#
# NOT A GUARD AGAINST TYPOS, and must not be documented as one - rule 13 permits
# inline supplier creation, and a user can pick the wrong supplier from an
# entirely correct dropdown. The justification is the commercial/valuation split
# above, and the tiers make no sense read any other way.
#
# `payment_instrument` IS HERE. Section 3.9's prose called it "deliberately
# absent from both tiers" while its own code sketch included it - an internal
# contradiction, resolved in the direction the sketch and the note itself
# pointed ("It should be Tier 2"). It is the paired half of `instrument_number`,
# and "the instrument is frozen but the instrument number is not" is the kind of
# split that gets implemented by accident.
ADMIN_FROZEN = frozenset({
    "supplier_id", "origin", "consignment_type", "incoterm",
    "instrument_number", "payment_instrument", "works_branch_id",
})

# EVERY PAYLOAD-REACHABLE GROUP COLUMN IS IN ONE TIER OR THE OTHER. Measured
# against the mapper rather than assumed: PAYLOAD_TO_GROUP has exactly eleven
# destinations and HARD_FROZEN | ADMIN_FROZEN is the same eleven, no gap and no
# overlap. So for a NORMAL USER a frozen group is entirely read-only, and the
# two tiers diverge only for an admin. That is not what "two tiers" suggests and
# it is the single most important fact for the front end, which is why the
# serializer publishes the sets rather than a boolean.
#
# `insurance_amount` is on the group and is deliberately in NEITHER set. It is
# not reachable from the payload today (it is absent from GROUP_SHARED_FIELDS),
# so nothing can write it and nothing needs to exempt it - but step 9 wires it
# up, and section 3.9 says the payment process does not freeze. Anyone
# implementing this as "deny all group writes for non-admins", which the
# paragraph above makes tempting, would freeze it by accident. Named here and
# asserted in tests/test_group_freeze.py so that cannot happen quietly.
FREEZE_EXEMPT_GROUP_COLUMNS = frozenset({"insurance_amount"})


class GroupFrozenError(Exception):
    """A write to a group field that a closed batch has settled.

    Mirrors AllocationError: one exception, raised wherever the rule is checked,
    mapped to one status by every route that can raise it. 423 - the same status
    the row lock returns - so the front end's existing "this record is closed"
    handling applies and there is no second locked-state vocabulary to learn.
    """

    status_code = 423

    def __init__(self, fields, tier, group=None, batch=None):
        self.fields = sorted(fields)
        self.tier = tier                      # "hard" | "admin"
        self.group_id = getattr(group, "id", None)
        self.batch = batch

        named = ", ".join(FROZEN_FIELD_LABELS.get(f, f) for f in self.fields)

        where = ""
        if batch is not None:
            number = consignment_number(batch) or batch.id
            where = f" Batch {number} has arrived at works."

        if tier == "hard":
            why = ("Rates and currency that money has already moved against "
                   "cannot be changed by anyone, including an admin.")
        else:
            why = ("The order's commercial terms are settled once a batch has "
                   "arrived. An admin can still correct them.")

        super().__init__(f"Cannot change {named} on this order.{where} {why}")


# What a refusal CALLS each field. A message reading "Cannot change
# works_branch_id" names a column an operator has never seen; the screen says
# "Works / Branch". The refusal has to be actionable, not merely accurate.
FROZEN_FIELD_LABELS = {
    "exchange_rate": "the exchange rate",
    "rate_booked_on": "the rate date",
    "rate_source": "the rate source",
    "currency": "the currency",
    "supplier_id": "the supplier",
    "branch_id": "the works / branch",
    "origin": "the country of origin",
    "consignment_type": "the consignment type",
    "incoterm": "the incoterm",
    "instrument_number": "the instrument number",
    "payment_instrument": "the payment instrument",
}


def freezing_batch(group):
    """The earliest live batch of this order that has closed, or None.

    `batches`, NOT `consignments` - the relationship on ConsignmentBatchGroup is
    `batches` (models.py), and section 3.9's sketch said `consignments` for four
    revisions. An AttributeError inside a freeze check would surface as a 500 on
    an ordinary save.
    """
    if group is None:
        return None

    for batch in sorted(group.batches, key=lambda b: b.batch_sequence or 0):
        if not batch.is_deleted and is_closed(batch):
            return batch
    return None


def group_is_frozen(group):
    """Has any live batch of this order closed?

    DERIVED, NOT STORED. A `frozen_at` column would be a denormalisation that
    can drift from the batch statuses it summarises, and this design has already
    rejected that shape twice (the numbering suffix, the shared group fields). A
    group holds a handful of batches and they are loaded anyway.
    """
    return freezing_batch(group) is not None


def frozen_columns_for(group, user):
    """Which GROUP COLUMNS this user may not write right now.

    IT NEVER RETURNS AN EMPTY SET FOR AN ADMIN ON A FROZEN GROUP, and that is
    the only place in this application where `is_admin` does not pass. Every
    other check in authorize() lets an admin through unconditionally. The
    asymmetry is deliberate - Tier 1 is a historical fact rather than a
    permission - and it is commented here AND at the raise site, because the
    first person to read either in isolation will assume it is a bug and fix it.
    """
    if not group_is_frozen(group):
        return frozenset()

    if user is not None and getattr(user, "is_admin", False):
        return HARD_FROZEN

    return HARD_FROZEN | ADMIN_FROZEN


def frozen_violations(group, user, payload_keys):
    """The payload keys in `payload_keys` this user may not write.

    Takes PAYLOAD keys and routes them through PAYLOAD_TO_GROUP, so `branch_id`
    is tested against `works_branch_id` rather than missed. Returns payload
    keys, because that is what the caller was handed and what the front end
    disables.
    """
    frozen = frozen_columns_for(group, user)
    if not frozen:
        return []

    return sorted(
        key for key in payload_keys
        if PAYLOAD_TO_GROUP.get(key) in frozen
    )


def frozen_reason(group, user, key):
    """Why this one key could not be restored, in a sentence an operator reads.

    The revert report needs a reason PER KEY, because a single revert can be
    refused two ways at once - one field retired, another frozen - and
    "some fields could not be restored" is the report that tells nobody
    anything.
    """
    column = PAYLOAD_TO_GROUP.get(key)
    label = FROZEN_FIELD_LABELS.get(key, key)
    batch = freezing_batch(group)
    where = ""
    if batch is not None:
        where = f" (batch {consignment_number(batch) or batch.id} has arrived at works)"

    if column in HARD_FROZEN:
        return (f"{label} is settled{where} - money has moved against it and "
                f"nobody, including an admin, can restate it")
    return (f"{label} is settled{where} - an admin can still change it, "
            f"but this revert cannot")


def assert_group_writable(group, user, payload_keys):
    """Refuse a write to a frozen group field. Raises GroupFrozenError.

    THE FIRST OF TWO LINES OF DEFENCE. This is the pre-write check every path
    calls before touching anything; `apply_group_updates` re-derives the same
    answer immediately before each setattr. Two checks for one rule is normally
    the thing to avoid - here it is deliberate, because section 4.7 records six
    write paths found one at a time, four of them by driving rather than by
    reading, and a silent drop is the exact failure this rule exists to prevent.

    IT RUNS BEFORE ANY WRITE, including before the change-history row. In the
    update route the history is written before the group is applied, so a check
    between them would record a change that never happened.
    """
    offending = frozen_violations(group, user, payload_keys)
    if not offending:
        return

    # Tier 1 is reported in preference to Tier 2 when a payload carries both:
    # it is the refusal with no way round it, so it is the one the operator
    # needs to read first.
    hard = [k for k in offending if PAYLOAD_TO_GROUP.get(k) in HARD_FROZEN]
    raise GroupFrozenError(
        hard or offending,
        "hard" if hard else "admin",
        group,
        freezing_batch(group),
    )


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
        line_item_code(item).strip().lower()
        for item in consignment.items
        if not item.is_deleted and line_item_code(item) and line_item_code(item).strip()
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
        if item.is_deleted or not line_item_code(item) or not line_item_code(item).strip():
            continue

        master = by_code.get(line_item_code(item).strip().lower())

        if master is None:
            continue

        # WRITES TO THE ORDER LINE, because that is where the name and the
        # specification live now (section 3.7). Reading through an accessor and
        # writing through one would hide that this function MUTATES; the
        # assignment is left explicit so the write is visible.
        #
        # STILL RUNS PER BATCH, AND THAT IS SAFE RATHER THAN MERELY UNCHANGED.
        #
        # Section 3.7 observes this could take a group and run once per group.
        # It is left per-batch, and with a second batch now possible the
        # question is no longer academic - saving batch 2 writes an order line
        # batch 1 also reads. Three reasons that is correct:
        #
        #   * THE VALUE IS THE SAME EITHER WAY. Both batches' lines point at
        #     the same order line, which carries ONE item_code, which resolves
        #     to ONE master row. Whichever batch saves, it writes the value the
        #     other would have written. There is nothing to drift.
        #   * IT ONLY EVER WRITES THE MASTER'S OWN CURRENT VALUE, so it cannot
        #     carry a batch-specific edit across to a sibling.
        #   * IT DOES NOT TOUCH A LOCKED SIBLING'S ROW. The lock is on the
        #     `consignments` row and its lines; this writes the ORDER line,
        #     which is shared by construction and is not what `is_locked`
        #     protects.
        #
        # What it costs is a repeated query on a split order - once per batch
        # save instead of once per order. Two or three batches is not a
        # performance problem, and moving it would change WHEN the correction
        # runs relative to the rest of the save for no gain in correctness.
        order_item = item.order_item
        if order_item is None:
            continue

        order_item.item_name = master.name

        if master.default_specification:
            order_item.specification = master.default_specification


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
        if item.quantity is not None and line_unit_price(item) is not None:
            foreign_total += item.quantity * line_unit_price(item)

    consignment.foreign_total = foreign_total

    # THE ORDER'S booked rate. Every batch of one LC converts at the same rate,
    # which is why it lives on the group (section 3.8) - held per batch, two
    # shipments of one order could report different PKR for the same money.
    rate = order_exchange_rate(consignment)
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
# The payment reference is what the list, the reports and the notifications
# all show as the consignment's reference; the CONSIGNMENT NUMBER is the
# fallback for an order that has not been given an instrument number (it was
# `IMP-{id}` until step 8 - see order_view.reference_label_from). One definition,
# because a notification naming a consignment differently from the screen the
# reader then opens is a notification they cannot act on.
#---------------------------------------

#---------------------------------------------------------------------------
# NOTHING IS SAVED UNTIL THERE IS SOMETHING TO SAVE - requirements line 161,
# finding 11, build-order step 2.
#
#   "If a user opens a new consignment and leaves it empty, no draft should be
#    created."
#
# Until now `POST /consignments/` created a row whatever it was given, so
# opening the wizard and closing it left a numbered draft behind. Those rows
# are indistinguishable from real work in progress: they sit in the list, they
# count towards the drafts filter, and nobody can tell which are abandoned.
#
# WHAT COUNTS AS SOMETHING, and why these three. They are the three ways an
# operator actually starts a consignment: they know who it is from, or they
# have the LC/TT number in front of them, or they are keying the items. Any one
# is a real beginning.
#
# WHAT DELIBERATELY DOES NOT COUNT: a status, a date, a mode of shipment. The
# wizard pre-fills or defaults those, so accepting "any field at all" would let
# an untouched form through and this guard would do nothing - which is worse
# than not having it, because it would look like it worked.
#
# WHERE IT SITS, AND WHY ONLY HERE. On CREATE only. The wizard POSTs once and
# PUTs from then on (ImportsStatusWizard, "POST the first time, PUT after"), so
# guarding the PUT as well would block an operator clearing a field on a record
# that already exists - an edit, not an empty draft. A record can still be
# emptied after creation, deliberately: that is a decision someone made about a
# real row, and the delete route is how it goes away.
#---------------------------------------------------------------------------

EMPTY_DRAFT_MESSAGE = (
    "Nothing to save yet. Enter at least a supplier, a payment instrument "
    "number, or one item with a name or code."
)


def _has_text(value):
    return value is not None and str(value).strip() != ""


def has_something_to_save(payload):
    """True if this create payload is a real beginning rather than a blank form.

    Takes the FLAT payload as posted, before it is split across the three
    tables, because the check is about what the operator typed and not about
    where each value ends up.
    """
    if _has_text(payload.get("supplier_id")) or _has_text(payload.get("instrument_number")):
        return True

    for item in (payload.get("items") or []):
        # A line counts only if it IDENTIFIES something. The wizard adds an
        # empty row as soon as the items step is opened, so "items is
        # non-empty" would wave the blank form straight through.
        if (_has_text(item.get("item_name"))
                or _has_text(item.get("item_code"))
                or _has_text(item.get("placeholder_name"))
                or _has_text(item.get("item_id"))):
            return True

    return False


# `consignment_reference()` IS GONE - build-order step 1, design section 3.4.
#
# It returned `instrument_number or IMP-{id}`, which conflated two different
# facts: the ORDER's payment reference (shared by every batch of one LC) and
# the SHIPMENT's own number. Two batches therefore rendered as two rows under
# one identical label. Replaced by `order_view.reference_label()` for what a
# row prints, `payment_reference()` for the order's reference alone, and
# `consignment_number()` for the shipment's number - all one definition each,
# over plain values, so the seven SQL-row call sites can reach them too.



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
# CORRECT FOR ITS OWN JOB, AND WRONG AS A REMOVAL LIST. READ THIS BEFORE
# REUSING IT.
#
# These are the values that live on the ORDER under their OWN NAME, which is
# what makes them copyable in a loop. FOURTEEN attributes came off
# `Consignment` in part 4, and this list is ten of them. The other four each
# need something this loop cannot do:
#
#   branch_id  -> the group's `works_branch_id`   (a RENAME, not a copy)
#   requisition_date, required_date -> the ORDER LINE, not the group
#   works      -> RETIRED; no successor anywhere
#
# So code that treats this as "the fields that left Consignment" will leave four
# behind. `PAYLOAD_TO_GROUP` below is the list with the rename folded in, and it
# is what the write path routes on.
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


#---------------------------------------
# WHERE A PAYLOAD FIELD GOES, NOW THAT IT IS NOT ALL ONE ROW
#
# The wizard still posts one flat consignment object, and it should: a batch and
# its order are one thing to the person typing. Splitting that payload across
# three tables is the server's job, and these maps are the whole of the rule.
#
# EXPLICIT DESTINATION MAPS, NOT A FALLBACK CHAIN. The tempting shape is "try
# the consignment, then the group, then the order item". It is wrong, and
# specifically dangerous: `branch_id` exists on BOTH the group (as
# `works_branch_id`) and the order line (as `branch_id`), so a chain would find
# the order line's, write a header value to a per-item column, and SUCCEED.
# A wrong destination that raises is a bug; a wrong destination that works is a
# data corruption nobody sees.
#---------------------------------------

# payload key -> the group's column name. The rename is here, not special-cased.
PAYLOAD_TO_GROUP = {field: field for field in GROUP_SHARED_FIELDS}
PAYLOAD_TO_GROUP["branch_id"] = "works_branch_id"

# payload key -> the ORDER LINE's column. Header-level in the payload, per-item
# in the model, so one posted value fans out to every line of the consignment.
# Section 3.3: the read side went per line, the write side keeps the header key.
#
# `branch_id` IS IN BOTH MAPS, DELIBERATELY - one payload key, two destinations.
#
# It is not a new shape: `requisition_date` and `required_date` already fan from
# one header key to every order line. Branch just fans to the group AS WELL,
# because `works_branch_id` is the header-level branch and
# `consignment_order_items.branch_id` is the per-item one, and until step 8
# offers a per-item control they are the same value.
#
# WHY BOTH RATHER THAN THE GROUP ALONE. Revision A back-filled
# `consignment_order_items.branch_id` on 448 of 451 rows, and the expanded
# per-item view displays it (requirement 8). Writing only the group would leave
# it NULL on everything created from now on - one column with two populations,
# old rows showing a branch and new rows blank on the same screen. This project
# has been bitten by that shape more than once.
#
# WHAT THIS COSTS LATER, recorded here because it is invisible today: reverting
# a branch change fans out too, so it OVERWRITES every line's branch with the
# header value. Harmless while nothing can set them individually. The moment
# step 8 offers a per-item branch, "restore the header branch" and "restore each
# line's own branch" become different operations and this map needs splitting.
# See section 3.3.
#
# WHAT A SECOND BATCH DOES TO THIS FAN-OUT - checked when step 7 made a second
# batch possible, and the answer is that it is SAFE, for a reason worth writing
# down rather than rediscovering.
#
# These three are facts about what was ORDERED, so one order line holds one
# value and every batch carrying that line reads the same one. Saving batch 2
# therefore writes a value batch 1 can see. That is not drift - it is the two
# batches agreeing about the order, which is the whole reason the column lives
# on the order line. And the fan-out reaches only the order lines THIS batch
# carries, so a save of batch 2 leaves an order line only batch 1 carries
# untouched.
#
# The revert paths inherit the same property for the same reason: reverting a
# demand date on batch 2 restores the order's date, which is the one fact there
# was to restore.
#
# The hazard is unchanged and is the one already named above - ONE header value
# fanned across lines that may legitimately differ - and it becomes real when
# step 8 offers a per-item control, not when an order splits.
PAYLOAD_TO_ORDER_ITEM = {
    "requisition_date": "requisition_date",
    "required_date": "required_date",
    "branch_id": "branch_id",
}

# Accepted from the payload and deliberately DROPPED, because the column they
# named is gone and nothing replaced it.
#
# Every entry needs a reason. A set with unexplained members becomes the place
# keys go when nobody wants to work out where they belong.
RETIRED_PAYLOAD_FIELDS = {
    # Free text for the factory, superseded by the group's `works_branch_id`:
    # Works and Branch were always the same thing to the business (section 3.3).
    # STEP 8 STOPPED THE WIZARD SENDING IT - Works is now Step 1's
    # "Works / Branch" dropdown, which writes `branch_id`, and the duplicate
    # free-text input on Finance is gone. The entry stays because a client that
    # has not reloaded still posts the key, and because an old change-history
    # row can still carry it on a revert; dropping it would turn either into
    # the "belongs to no table" ValueError above.
    "works",
}


def new_batch_group(consignment, user, db, group_fields=None):
    """Create the order this consignment is the first batch of, and link them.

    Flushes twice, in the only order the constraints allow - see the block
    comment above. Returns the group.

    `group_fields` COMES FROM THE PAYLOAD, not from the consignment. It used to
    read the values back off the consignment it had just built, which worked
    only while the consignment still had them. It does not, so the caller passes
    what `split_consignment_payload` routed here.
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
        created_by_id=user.id if user is not None else None,
        **(group_fields or {}),
    )

    db.add(group)
    db.flush()

    return group


#===========================================================================
# ADDING A BATCH TO AN ORDER THAT ALREADY EXISTS
#
# `new_batch_group` above founds an order. This is the other half: a second,
# third, nth arrival against an order already in the system.
#
# NUMBERING - THE THREE DECISIONS, IN THE CODE BECAUSE THE CODE IS WHERE THEY
# WILL BE READ (design sections 3.5 and 0.4, decisions A1/A2/A3):
#
# A1. A SINGLE BATCH KEEPS THE PLAIN NUMBER. `177` while an order holds one
#     batch; `177-1` and `177-2` the moment it splits. This overrides the
#     earlier design's universal suffix: the requirements asked for it, and
#     with most orders arriving once a suffix on everything would mean nothing.
#
#     THE COST IS REAL AND IS NOT HIDDEN. Creating a second batch RENUMBERS THE
#     FIRST, from `177` to `177-1` - a visible change to a number somebody may
#     have written down. It happens once, at a deliberate action, and the route
#     states it in its response rather than leaving the client to notice by
#     diffing two fetches. No row is written to do it: the number is derived
#     from `founding_consignment_id` + `batches_ever` + `batch_sequence`
#     (order_view.consignment_number_from), so the only column that moves is
#     `batches_ever` on the group. That matters more than it looks - 142 of 179
#     live consignments are LOCKED, and a stored suffix would have needed an
#     UPDATE against a locked sibling to renumber it.
#
# A2. THE NEXT BATCH EXISTS WHEN SOMEBODY CREATES IT, not before. The
#     requirements' "unallocated items are automatically placed into 177-2"
#     describes the SCREEN - a pending-allocation area - not a row in
#     `consignments`. A batch with no route, no ETA and no status is not a
#     shipment; it is a list of things not yet shipped, and creating one early
#     would put a phantom consignment into every list, count and dashboard in
#     the app. Unallocated quantity lives on the order line as
#     `ordered_quantity - allocated_quantity`, which is what it is for.
#
# A3. NUMBERS ARE PERMANENT, GAPS AND ALL. `batch_sequence` is assigned once
#     and never reused, so deleting `177-2` leaves `177-1` and `177-3` with a
#     gap between them. The gap is the point: a number that has been on an
#     invoice must not later mean a different shipment. RENUMBERING RUNS
#     FORWARD ONLY - an order that splits to two and then loses one keeps
#     `177-1` and does NOT revert to `177`, because `batches_ever` never
#     decrements.
#===========================================================================

def claim_batch_sequence(db, group_id):
    """Take the next sequence number for this order, atomically.

    `batches_ever` is both the count and the source of the next number, which
    works precisely because it never decrements and a sequence is never reused:
    after the increment, the new `batches_ever` IS the sequence to assign.

    DONE IN SQL, NOT IN PYTHON. Reading the column, adding one and writing it
    back is a read-modify-write, and two operators splitting one order at the
    same moment would both read 1 and both write 2 - two batches claiming
    sequence 2, and `batches_ever` stuck at 2 having counted three batches.
    `SET batches_ever = batches_ever + 1 ... RETURNING` is atomic and takes the
    group's row lock as a side effect.

    `uq_consignments_group_sequence` stays as the backstop underneath this. It
    should never fire; if it ever does, that is a bug report about this
    function, not something for the caller to retry around.
    """
    new_sequence = db.execute(
        update(ConsignmentBatchGroup)
        .where(ConsignmentBatchGroup.id == group_id)
        .values(batches_ever=ConsignmentBatchGroup.batches_ever + 1)
        .returning(ConsignmentBatchGroup.batches_ever)
    ).scalar_one()

    # The in-session copy is now stale, and `consignment_number()` reads it to
    # decide whether to suffix. Expiring it makes the very next read fetch the
    # committed value instead of reporting the pre-split number.
    group = db.get(ConsignmentBatchGroup, group_id)
    if group is not None:
        db.expire(group, ["batches_ever"])

    return new_sequence


def add_batch(db, group, allocations, user):
    """Create one more batch of an existing order, carrying `allocations`.

    `allocations` is [{order_item_id, quantity}] - which items this arrival
    brings, and how much of each.

    WHAT IT DELIBERATELY DOES NOT COPY FROM THE FOUNDING BATCH: the route, the
    schedule, the ports, the mode, the clearance and the status. The
    requirements are explicit that a later batch's shipping section starts
    EMPTY and editable, with the earlier batches' shown locked above it, so
    those are entered afterwards through the ordinary edit. The commercial half
    - supplier, currency, incoterm, the booked rate - is not copied either
    because it never lived on the batch: it is on the order, and the new batch
    reads the same row the first one does.

    THE ALLOCATION CHECK IS NOT HERE. It is `reconcile_allocation`, which the
    caller runs after this - the same function an ordinary edit runs, so a
    batch created through this route and a line re-quantified through `PUT`
    cannot be governed by two different rules.
    """
    sequence = claim_batch_sequence(db, group.id)

    batch = Consignment(
        batch_group_id=group.id,
        batch_sequence=sequence,
        created_by_id=user.id,
        # The first status in the pipeline. A new arrival has not shipped yet,
        # and inheriting the founding batch's status would announce that goods
        # nobody has dispatched are already in transit.
        current_status=Status.TT_LC_IN_PROCESS.value,
        record_state="draft",
        is_locked=False,
        is_deleted=False,
    )

    db.add(batch)
    db.flush()

    for allocation in allocations:
        line = ConsignmentItem(
            consignment_id=batch.id,
            order_item_id=allocation["order_item_id"],
            quantity=allocation["quantity"],
        )
        db.add(line)

    db.flush()

    return batch


def sync_group_deleted_state(db, group_id):
    """An order is deleted exactly when it has no live batch left.

    THIS FLAG HAD NO WRITER AT ALL, and the gap was found by driving the batch
    route rather than by reading the code. `consignment_batch_groups.is_deleted`
    was set once, by revision A's back-fill, copying it off the consignment
    each group was built from. Nothing in the application has written it since:
    the delete route sets the flag on the CONSIGNMENT and stops there.

    That was invisible while every order held one batch and nothing consulted
    the group's flag. It stops being invisible here - undo-deleting one of the
    four soft-deleted consignments produced a LIVE batch under a DELETED order,
    and the batch route correctly refused to add anything to an order that says
    it does not exist.

    Both directions, because either alone is worse than neither:

      * deleting the last live batch retires the order;
      * restoring any batch brings it back.

    Derived from the batches rather than tracked alongside them, for the reason
    this design keeps reaching for: a flag maintained in two places is a flag
    that disagrees with itself, and the batches are the fact.
    """
    live_batches = db.execute(
        select(func.count(Consignment.id))
        .where(Consignment.batch_group_id == group_id)
        .where(Consignment.is_deleted == False)  # noqa: E712
    ).scalar()

    group = db.get(ConsignmentBatchGroup, group_id)
    if group is None:
        return

    should_be_deleted = not live_batches
    if should_be_deleted != group.is_deleted:
        group.is_deleted = should_be_deleted
        group.deleted_at = datetime.now(timezone.utc) if should_be_deleted else None
        if not should_be_deleted:
            group.deleted_by_id = None


def renumbering_note(group, batches):
    """What this order's batches are numbered, now that one has been added.

    Published by the batch-create route because A1's renumbering is a change to
    rows the request did not name: creating `177-2` silently turns `177` into
    `177-1` everywhere it is rendered. The client is told rather than left to
    work it out by fetching the list again and noticing.
    """
    from app.imports.order_view import consignment_number_from

    return {
        "order_number": str(group.founding_consignment_id),
        "batches_ever": group.batches_ever,
        # True exactly when this creation was the split - the point at which
        # every sibling gained a suffix it did not have a moment ago.
        "siblings_renumbered": group.batches_ever == 2,
        "batches": [
            {
                "consignment_id": b.id,
                "batch_sequence": b.batch_sequence,
                "consignment_number": consignment_number_from(
                    group.founding_consignment_id, group.batches_ever,
                    b.batch_sequence,
                ),
                # NULL on the batch that was just created - it had no number a
                # moment ago, and reporting one would invite a client to render
                # "177 is now 177-2" for a shipment that did not exist. On every
                # sibling it is the number that was on screen before this
                # request, which is the only one worth telling anybody about.
                "previous_consignment_number": (
                    None if b.batch_sequence == group.batches_ever
                    else consignment_number_from(
                        group.founding_consignment_id, group.batches_ever - 1,
                        b.batch_sequence,
                    )
                ),
            }
            for b in sorted(batches, key=lambda x: x.batch_sequence)
        ],
    }


#---------------------------------------
# `sync_batch_group` WAS HERE, AND IS DELETED.
#
# It mirrored the shared values from batch 1 onto its group, because both
# copies existed and only one of them was read. There is one copy now: the
# write path sets the group DIRECTLY from the payload
# (`split_consignment_payload` -> `apply_group_updates`), so there is nothing
# left to mirror FROM and nothing that could drift.
#
# Its own docstring said it was transitional and named this as the moment it
# goes. Recorded rather than quietly dropped because the BUG it fixed is worth
# remembering: an ordinary ORM update kept writing the copy nobody read, and
# nothing noticed until the readers moved. That is section 4.7's fourth bypass
# path, and deleting the patch does not delete the lesson.
#
# Its batch-1 rule does NOT become the editing rule. Any batch may be deleted,
# the founding one included, so a batch-1 rule would leave an order whose first
# shipment was deleted with terms nobody could correct. Step 7 edits the group
# AS THE GROUP (section 3.8).
#---------------------------------------


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
# The demand fields the wizard posts at HEADER level and that fan out to every
# order line - see PAYLOAD_TO_ORDER_ITEM, which is what actually routes them.
#
# `branch_id` IS LISTED HERE AND IS NOT ROUTED, AND THAT IS AN OPEN QUESTION,
# NOT AN OVERSIGHT. The header `branch_id` goes to the GROUP
# (PAYLOAD_TO_GROUP -> works_branch_id) and nowhere else, so a consignment
# created today leaves `consignment_order_items.branch_id` NULL - while the 448
# rows revision A back-filled all carry it, copied from the consignment header.
# New records and migrated records therefore differ.
#
# Writing it to both would make revert ambiguous (it restores one destination,
# see the revert routing), and writing it to neither loses a column the
# requirements ask for. Which it should be is a design decision that belongs
# with step 8, when the wizard first offers a per-ITEM branch and there is a
# real answer to "what did the user mean". Left explicit rather than silently
# resolved either way.
ORDER_ITEM_HEADER_FIELDS = {
    "branch_id": "branch_id",
    "requisition_date": "requisition_date",
    "required_date": "required_date",
}


#---------------------------------------------------------------------------
# WHAT WAS ORDERED, AND WHEN IT STOPS FOLLOWING WHAT SHIPPED
#
# While an order holds ONE batch the two are the same quantity. There is
# nothing to tell apart, no screen that asks for both, and every one of the 179
# existing records is in that state - so an ordinary edit to the line quantity
# moves `ordered_quantity` with it, exactly as it always has, and the wizard
# needs no change before step 8.
#
# The moment an order SPLITS they stop being one fact. Batch 2 carrying 150 of
# an order for 250 must not restate the order as 150 - and it would, on every
# save, because the wizard posts the whole draft back. From the split onwards
# the order quantity is set explicitly (the payload's own `ordered_quantity`)
# or left alone.
#
# `batches_ever` is the test rather than a live count of batches, because it
# never decrements: an order that split and then lost a batch has still been
# split, and its order quantity is a fact of its own from then on. It does not
# quietly start following the survivor again.
#---------------------------------------------------------------------------

def resolve_ordered_quantity(order_item, line, line_payload, group):
    """What `ordered_quantity` should become on this save. None means leave it.

    Four cases, in order:

      1. the payload states it                -> that value, always
      2. the order line is brand new          -> the line's quantity
      3. the order has only ever held 1 batch -> the line's quantity
      4. otherwise                            -> None: do not touch it
    """
    if line_payload is not None and line_payload.get("ordered_quantity") is not None:
        return line_payload["ordered_quantity"]

    # NOT NULL, and a line can legitimately carry no quantity at draft. A line
    # that orders nothing orders zero - the same COALESCE the migration and the
    # loader apply, for the same reason.
    line_quantity = line.quantity if line.quantity is not None else Decimal("0")

    if order_item.ordered_quantity is None:
        return line_quantity

    if (getattr(group, "batches_ever", 1) or 1) <= 1:
        return line_quantity

    return None


class NewItemOnLaterBatch(AllocationError):
    """An item posted on a later batch with nothing saying what it allocates against.

    422, like the other allocation refusals - the client sent something the
    server cannot act on, which is a request problem rather than a permission
    or a lock.

    THE MESSAGE NAMES THE ITEM, because the alternative is an operator staring
    at a six-line form being told "an item is invalid". Where the payload did
    not even carry a name, it says so rather than printing "None".
    """

    status_code = 422

    def __init__(self, item_name, batch_sequence):
        self.item_name = item_name
        self.batch_sequence = batch_sequence
        named = f'"{item_name}"' if item_name else "An unnamed item"
        where = f" (batch {batch_sequence})" if batch_sequence else ""
        super().__init__(
            f"{named} is not one of the items this order bought, and this is "
            f"not the order's first batch{where}. Allocate against an existing "
            f"order line by sending its `order_item_id`, or add the item to the "
            f"order explicitly - posting it here would raise what the order is "
            f"recorded as having bought."
        )


def resolve_order_line(db, item, consignment, line_payload):
    """The order line this shipment line is an allocation against.

    Three ways a line gets one:

      * `order_item_id` in the payload - a later batch allocating against an
        order line that already exists. VALIDATED AGAINST THE GROUP: without
        that check a client could point a line at another order's line and
        allocate across orders, which no screen offers and nothing else in the
        write path would catch.
      * already attached - an ordinary edit to a line that has one.
      * neither - a new item, which gets a new order line.
    """
    # ONE TEST, COVERING EVERY WRITER. `order_item_id` is a `ConsignmentItem`
    # column, so it can arrive three ways: in this payload, through
    # `ConsignmentItem(**line_fields)` on a line an update adds, or through
    # `apply_item_updates` on one it edits. Reading the COLUMN rather than the
    # relationship catches all three - on a pending row the relationship is
    # still None while the foreign key is already set, so a guard written
    # against `item.order_item` would silently mint a duplicate order line for
    # exactly the case it was there to check.
    named_id = (line_payload or {}).get("order_item_id") or item.order_item_id

    if named_id is not None:
        order_item = db.get(ConsignmentOrderItem, named_id)
        if order_item is None or order_item.batch_group_id != consignment.batch_group_id:
            raise UnknownOrderLine(named_id)
        return order_item

    if item.order_item is not None:
        return item.order_item

    # A NEW ITEM ON A SPLIT ORDER IS REFUSED - design 3.7b, finding 3.
    #
    # With no `order_item_id` and no existing link, the only honest reading of
    # this line is "a new item on the order". That is right on the founding
    # batch, where the order is being written for the first time, and wrong on
    # every later one - there it silently RAISES WHAT THE ORDER BOUGHT.
    #
    # Measured before this guard existed, on the split fixture: a wizard-shaped
    # PUT adding one line to batch 2 returned 200, created order line 456, and
    # took the order from 33.523 ordered to 38.523. No error, and the
    # over-allocation CHECK cannot see it because each line sits inside its own
    # order line - the sum is larger but so is the limit.
    #
    # THE FRONT END SENDING `order_item_id` IS THE REAL FIX; this is the one
    # that catches the next client. It is the same reasoning as the freeze's
    # setattr guard: a rule enforced only where today's caller happens to obey
    # it is not enforced.
    #
    # The founding batch stays permissive, so the ordinary create path and
    # every single-batch order behave exactly as before.
    if (getattr(consignment.batch_group, "batches_ever", 1) or 1) > 1:
        raise NewItemOnLaterBatch(
            line_payload.get("item_name") if line_payload else None,
            getattr(consignment, "batch_sequence", None),
        )

    return ConsignmentOrderItem(batch_group_id=consignment.batch_group_id)


def sync_order_item_from_line(order_item, item, line_payload=None,
                              header_fields=None, group=None):
    """Update the order line above a shipment line.

    IT NO LONGER COPIES FROM THE LINE, because the line no longer has the
    thirteen columns to copy. `line_payload` is what the client posted for this
    item; `header_fields` is the consignment-level demand data
    (requisition/required date, branch) routed out of the header payload. Both
    are written straight to the order line.

    That is the write-path inversion in one function: the values used to arrive
    on the ConsignmentItem and be mirrored UP, and they now arrive from the
    payload and are written DOWN. A line that is re-saved with no payload (a
    quantity-only edit) keeps whatever its order line already holds.

    TWO THINGS IT USED TO WRITE AND DELIBERATELY NO LONGER DOES, both because
    they are facts about the ORDER while this function only ever sees one batch:

      * `allocated_quantity` - the sum across every batch of the order. Written
        by `reconcile_allocation` and by nothing else. Set from one line, it
        became whichever batch happened to save last.
      * `is_deleted` - an order line outlives any one batch's line and is
        retired only when the last of them goes. Same function, same reason:
        mirroring it from the line meant deleting batch 2's line soft-deleted
        the order line batch 1 also points at.
    """
    for field in ORDER_ITEM_LINE_FIELDS:
        if line_payload is not None and field in line_payload:
            setattr(order_item, field, line_payload[field])

    for target in ORDER_ITEM_HEADER_FIELDS.values():
        if header_fields is not None and target in header_fields:
            setattr(order_item, target, header_fields[target])

    ordered = resolve_ordered_quantity(order_item, item, line_payload, group)
    if ordered is not None:
        order_item.ordered_quantity = ordered

    return order_item


def sync_order_items(consignment, db, payloads=None, header_fields=None):
    """Build or update the order line above every line of a consignment.

    `payloads` maps a ConsignmentItem INSTANCE to the order-line fields posted
    for it; `header_fields` is the consignment-level demand data that fans out
    to every line. Keyed by instance rather than by index or id because on an
    update the collection is a mix of rows that existed, rows just added and
    rows soft-deleted, and position means nothing across those three.

    A line absent from `payloads` keeps whatever its order line already holds -
    which is what a quantity-only edit, or a re-save that touched no item
    fields, should do.

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
    group = consignment.batch_group

    with db.no_autoflush:
        for item in consignment.items:
            line_payload = (payloads or {}).get(item)

            order_item = resolve_order_line(db, item, consignment, line_payload)
            if item.order_item is not order_item:
                item.order_item = order_item

            sync_order_item_from_line(
                order_item, item,
                line_payload=line_payload,
                header_fields=header_fields,
                group=group,
            )
