"""GET /consignments/{consignment_id}/batches - the order's sibling batches.

WHY AN ENDPOINT AND NOT A BLOCK ON THE DETAIL PAYLOAD (design 3.7b). A
`siblings` key on `GET /{id}` would duplicate a list row's shape in a second
place and go stale against it: the moment the list serializer gains a field the
siblings block does not, the same batch renders two ways depending on which
call fetched it. One shape, one serializer.

WHY NOT A `batch_group_id` FILTER ON THE LIST, which section 3.7b proposed. The
filter reads well and is wrong for this caller: the list applies
`include_closed=False`-style defaults, paging and the user's own filters, so
"the siblings of this order" would come back a different set depending on what
the screen happened to have selected. The locked-above sections need ALL of
them, always, in sequence order. An order holds a handful of batches, so there
is nothing to page.

It returns the SAME serializer the list and detail use, so a sibling card and a
list row cannot disagree about a batch.
"""

import logging

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.database import SessionLocal
from app.imports.helpers import fetch_consignment
from app.imports.models import (
    Consignment, ConsignmentBatchGroup, ConsignmentItem,
)
from app.imports.routes.router import router
from app.imports.serializers import serialize_consignment

logger = logging.getLogger(__name__)


@router.get("/{consignment_id}/batches")
def get_batches(request: Request, consignment_id: int):
    db = SessionLocal()

    try:
        user_payload = authenticate(request)
        authorize(user_payload, CAN_VIEW_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)
        if consignment is None:
            raise HTTPException(status_code=404, detail="Consignment not found")

        # EVERY LIVE BATCH OF THE ORDER, INCLUDING THE ONE ASKED ABOUT.
        #
        # Including itself is deliberate. The caller is a screen rendering "this
        # order's batches", and a list that omits the one you are looking at
        # makes the client reassemble the whole from a part - which is where an
        # off-by-one in the sequence display comes from. It is also what lets a
        # single call answer "which batch am I?" without a second fetch.
        #
        # ORDERED BY SEQUENCE, not by id: they agree today because sequences are
        # claimed in creation order, and they would stop agreeing the moment a
        # batch is created out of band. Sequence is what the NUMBER is derived
        # from, so sequence is what the screen must be ordered by.
        batches = db.execute(
            select(Consignment)
            .where(Consignment.batch_group_id == consignment.batch_group_id)
            .where(Consignment.is_deleted.is_(False))
            .options(
                joinedload(Consignment.batch_group)
                .joinedload(ConsignmentBatchGroup.supplier),
                joinedload(Consignment.batch_group)
                .joinedload(ConsignmentBatchGroup.works_branch),
                joinedload(Consignment.loading_port),
                joinedload(Consignment.delivery_port),
                joinedload(Consignment.clearing_agent),
                # The same eager loads the list uses - `serialize_consignment`
                # walks every line through `item.order_item`, so without this it
                # is one query per line per batch.
                selectinload(Consignment.items)
                .selectinload(ConsignmentItem.order_item),
                selectinload(Consignment.payments),
                selectinload(Consignment.status_updates),
                selectinload(Consignment.eta_revisions),
                joinedload(Consignment.created_by),
                joinedload(Consignment.deleted_by),
            )
            .order_by(Consignment.batch_sequence, Consignment.id)
        ).unique().scalars().all()

        return {
            "status_code": 200,
            "detail": "Batches fetched",
            "data": [
                # include_change_history=False for the same reason the list
                # passes it: the caller is drawing summary cards, and the
                # history is the single largest thing on the payload.
                serialize_consignment(b, db, include_change_history=False)
                for b in batches
            ],
            "total": len(batches),
        }

    except HTTPException:
        raise

    except Exception:
        logger.exception("Failed to fetch batches for consignment %s", consignment_id)
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
