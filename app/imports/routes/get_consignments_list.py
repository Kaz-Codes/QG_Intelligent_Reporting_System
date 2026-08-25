from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.imports.helpers import fetch_consignments_page
from app.imports.serializers import serialize_consignment
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
    include_closed : Optional[bool] = False,
    status : Optional[list[str]] = Query(None),
    stage : Optional[str] = None,
    branch_id : Optional[list[int]] = Query(None),
    supplier_id : Optional[list[int]] = Query(None),
    requisition_type : Optional[list[str]] = Query(None),
    missing_only : Optional[bool] = False,
    etd_from : Optional[date] = None,
    etd_to : Optional[date] = None,
    q : Optional[str] = None,
    # The "Forwarded" view: only consignments handed to logistics or trucking.
    sent_only : Optional[bool] = False
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_VIEW_IMPORTS, db)

        # Keep the page and size sane
        if page < 1:
            page = 1

        if page_size < 1 or page_size > 100:
            page_size = 20

        consignments, total = fetch_consignments_page(
            db, include_deleted, include_closed, status, stage,
            branch_id, supplier_id, requisition_type,
            missing_only, etd_from, etd_to, q, page, page_size,
            sent_only=sent_only
        )

        # Serializeing this page of consignments. change_history is left out
        # here — the list never renders it (see /history) — and
        # fetch_consignments_page doesn't eager-load it either, so this stays
        # one query for the whole page rather than one extra per row.
        serialized_consignments = [
            serialize_consignment(consignment, db, include_change_history=False)
            for consignment in consignments
        ]

        return {
            "status_code":200,
            "detail":"Consignments fetched",
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
        logger.exception("Unhandled error in app.imports.routes.get_consignments_list")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
