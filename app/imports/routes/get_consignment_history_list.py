from app.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.imports.helpers import fetch_all_consignment_history, fetch_consignment
from app.imports.serializers import serialize_consignment_history
from typing import Optional

@router.get("/change-history/{consignment_id}")
def get_consignment_history_list(
    request : Request,
    consignment_id : int,
    include_reverted : Optional[bool] = False,
    page : int = 1,
    page_size : int = 20
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, CAN_VIEW_IMPORTS, db)

        consignment = fetch_consignment(db, consignment_id)

        if not consignment:
            raise HTTPException(
                status_code=404,
                detail="Consignment not found"
            )

        # Keep the page and size sane, same bounds as the consignments list.
        if page < 1:
            page = 1

        if page_size < 1 or page_size > 100:
            page_size = 20

        consignment_history, total = fetch_all_consignment_history(
            db, include_reverted, consignment.id, page, page_size
        )

        # Serializeing this page of consignment histories
        serialized_consignment_history = [
            serialize_consignment_history(history) for history in consignment_history
        ]

        return {
            "status_code":200,
            "detail":"Consignment history fetched",
            "data":serialized_consignment_history,
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
        print(e)
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
 