"""POST /consignments/{consignment_id}/batches - one more arrival of an order.

WHY A ROUTE OF ITS OWN, AND NOT A PARAMETER ON `POST /consignments/`.
Four reasons; the first decides it on its own.

  1. `POST /` WOULD REJECT THIS AS AN EMPTY DRAFT. `has_something_to_save`
     requires a supplier, a payment-instrument number, or an item with a name
     or code. A later batch has none of those: the supplier and the instrument
     number live on the ORDER, and its lines are allocations against order
     lines that already exist. Making that guard order-aware would weaken a
     guard that was just shipped, for every create, to let one case through.

  2. `POST /` CALLS `new_batch_group` UNCONDITIONALLY. Making that conditional
     on a nullable `batch_group_id` in the body puts two different creation
     semantics behind one verb, chosen by a field the client may omit.

  3. THE LOCK RULES DIFFER, and only this path has to reason about them.
     Adding a batch to an order whose other batches are CLOSED is always
     allowed, to anybody, with no reopen - see the note on the guard below.
     `PUT /{id}` 423s on a locked row and must go on doing so.

  4. THE RESPONSE IS ABOUT ROWS THE REQUEST DID NOT NAME. Creating `177-2`
     renumbers `177` to `177-1`, and saying so is this route's job.
"""

import logging

from fastapi import HTTPException, Request
from sqlalchemy import select

from app.accounts.permissions import CAN_ADD_IMPORTS
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.database import SessionLocal
from app.imports.helpers import (
    AllocationError, OrderLineHasNoQuantity, UnknownOrderLine,
    add_batch, fetch_consignment, recompute_derived, reconcile_allocation,
    renumbering_note,
)
from app.imports.models import ConsignmentOrderItem
from app.imports.routes.router import router
from app.imports.schemas import CreateBatchSchema
from app.imports.serializers import serialize_consignment

logger = logging.getLogger(__name__)


def order_lines_by_id(group_id, ids):
    """The order's own lines, by id.

    SCOPED TO THE ORDER, which is the check that matters: without it a client
    could name an order line belonging to a different order and allocate across
    orders, which no screen offers and nothing further down the write path
    would catch.
    """
    return (
        select(ConsignmentOrderItem)
        .where(ConsignmentOrderItem.batch_group_id == group_id)
        .where(ConsignmentOrderItem.id.in_(ids))
        .where(ConsignmentOrderItem.is_deleted == False)  # noqa: E712
    )


@router.post("/{consignment_id}/batches")
def create_batch(
        batch_data: CreateBatchSchema,
        request: Request,
        consignment_id: int,
    ):

    db = SessionLocal()

    try:
        user_payload = authenticate(request)

        # `can_add_imports`, the same permission that creates an order. A batch
        # is a consignment, and nothing about it being the second one of an
        # order makes it a different kind of act.
        user = authorize(user_payload, CAN_ADD_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)

        if consignment is None or consignment.is_deleted:
            raise HTTPException(status_code=404, detail="Consignment not found")

        group = consignment.batch_group

        if group is None or group.is_deleted:
            raise HTTPException(
                status_code=404,
                detail="This consignment has no order to add a batch to.",
            )

        # THERE IS DELIBERATELY NO is_locked GUARD HERE, and its absence is the
        # decision rather than an omission.
        #
        # A closed batch means one shipment has arrived at the works. It says
        # nothing about the rest of the order, and the whole point of batching
        # is that the remainder arrives later - often weeks later, by which
        # time the first batch is certainly closed. Requiring an admin to
        # reopen a delivered shipment before the next one can be recorded would
        # make the normal case the exceptional one.
        #
        # What a closed batch DOES restrict is editing the ORDER's own fields
        # while it is closed. That is the group freeze - a separate rule, and
        # it is BUILT (design 3.9, helpers.assert_group_writable).
        #
        # IT IS STILL NOT CALLED HERE, and that remains correct rather than an
        # omission: this route writes no group field. The body is `allocations`
        # and nothing else, and `claim_batch_sequence` touches only
        # `batches_ever`, which is bookkeeping the freeze deliberately exempts.
        # A new batch INHERITS the order's terms; the moment anyone tries to
        # change them - through `PUT /{id}` on this new batch like any other -
        # the freeze refuses. Driven in tests/check_group_freeze.py: batch 3 is
        # created on a frozen order, and its attempt to set the rate 423s.

        # THE ORDER LINES, VALIDATED BEFORE ANYTHING IS WRITTEN.
        requested_ids = [a.order_item_id for a in batch_data.allocations]

        order_lines = {
            row.id: row
            for row in db.execute(
                order_lines_by_id(group.id, requested_ids)
            ).scalars().all()
        }

        unknown = [i for i in requested_ids if i not in order_lines]
        if unknown:
            raise UnknownOrderLine(unknown[0])

        # RULE: a line that ordered nothing has nothing to allocate, and the
        # refusal names the fix. These are the migration's COALESCE rows -
        # sheet lines that carried no quantity - not orders of zero, and
        # `ordered_quantity` is now a field the ordinary edit can set.
        no_quantity = [
            (row.id, row.item_name)
            for row in (order_lines[i] for i in requested_ids)
            if not row.ordered_quantity
        ]
        if no_quantity:
            raise OrderLineHasNoQuantity(no_quantity)

        # TWO LINES AGAINST ONE ORDER LINE IN ONE REQUEST would each be written
        # and the sum would quietly be their total, which is not what the
        # client asked for and reads as an accepted duplicate. One line per
        # item per batch.
        if len(set(requested_ids)) != len(requested_ids):
            raise HTTPException(
                status_code=422,
                detail=("The same item appears twice in this batch. Combine "
                        "them into one line with the total quantity."),
            )

        batch = add_batch(
            db, group,
            [{"order_item_id": a.order_item_id, "quantity": a.quantity}
             for a in batch_data.allocations],
            user,
        )

        # THE INVARIANT, through the SAME function an ordinary edit runs. It
        # takes the row locks, re-reads the sum out of the database and raises
        # if this batch has taken the order past what it bought.
        reconcile_allocation(db, group.id)

        # This batch's own money totals, from its own lines and the ORDER's
        # booked rate - which is how each batch comes to carry the value of
        # what it actually carried.
        recompute_derived(batch)

        db.commit()
        db.refresh(batch)
        db.refresh(group)

        return {
            "status_code": 201,
            "detail": "Batch created",
            "data": {
                "batch": serialize_consignment(batch, db),
                # A1'S RENUMBERING, STATED. Creating the second batch turns
                # `177` into `177-1` everywhere it is rendered, with no write
                # to that row - the number is derived. The client is told here
                # rather than left to notice by fetching the list again.
                "numbering": renumbering_note(
                    group,
                    [b for b in group.batches if not b.is_deleted],
                ),
            },
        }

    except AllocationError as e:
        db.rollback()
        raise HTTPException(status_code=e.status_code, detail=str(e))

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        logger.exception("Unhandled error in app.imports.routes.create_batch")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
