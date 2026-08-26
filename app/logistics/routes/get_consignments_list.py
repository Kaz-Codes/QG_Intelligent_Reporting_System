from app.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_LOGISTICS
from app.logistics.helpers import fetch_consignments_page
from app.logistics.serializers import serialize_consignment
from typing import Optional
from datetime import date
from fastapi import Query
import logging

logger = logging.getLogger(__name__)

@router.get("/")
def get_consignments_list(
    request : Request,
    page : int = 1,
    page_size : int = 20,
    include_deleted : Optional[bool] = False,
    status : Optional[list[str]] = Query(None),
    order_type : Optional[list[str]] = Query(None),
    customer : Optional[list[str]] = Query(None),
    # Repeated param -> IN, the same convention as status/order_type/customer.
    # Job number lives on the ITEM, so this filters orders by their lines —
    # see helpers._has_matching_item.
    job_number : Optional[list[str]] = Query(None),
    # Single free-text value, matched partially and case-insensitively against
    # the items' detail. Not multi-select: this is a search, not a pick-list.
    item_name : Optional[str] = None,
    gate_out_from : Optional[date] = None,
    gate_out_to : Optional[date] = None,
    q : Optional[str] = None,
    # 'standard' (the Orders tab, the default), 'rework' (Service Jobs), or
    # 'all' for both. Not multi-select: a record is one kind or the other.
    job_kind : Optional[str] = "standard"
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_VIEW_LOGISTICS, db)

        # Keep the page and size sane
        if page < 1:
            page = 1

        if page_size < 1 or page_size > 100:
            page_size = 20

        consignments, total = fetch_consignments_page(
            db, include_deleted, status, order_type, customer,
            gate_out_from, gate_out_to, q, page, page_size,
            None if job_kind == "all" else job_kind,
            job_number=job_number, item_name=item_name,
        )

        # Serializeing this page of orders. change_history is left out here —
        # the list never renders it (see /change-history) — and
        # fetch_consignments_page doesn't eager-load it either, so this stays
        # one query for the whole page rather than one extra per row.
        serialized_consignments = [
            serialize_consignment(consignment, include_change_history=False)
            for consignment in consignments
        ]

        return {
            "status_code":200,
            "detail":"Orders fetched",
            "data":serialized_consignments,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if total else 0
            }
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.get_consignments_list")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
