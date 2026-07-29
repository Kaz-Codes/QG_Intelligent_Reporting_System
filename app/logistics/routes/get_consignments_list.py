from app.logistics.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.logistics.helpers import fetch_consignments_page
from app.logistics.serializers import serialize_consignment
from typing import Optional

@router.get("/")
def get_consignments_list(
    request : Request,
    page : int = 1,
    page_size : int = 20,
    include_deleted : Optional[bool] = False,
    status : Optional[str] = None,
    order_type : Optional[str] = None,
    shipping_line : Optional[str] = None,
    q : Optional[str] = None
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action)
        user = authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        # Keep the page and size sane
        if page < 1:
            page = 1

        if page_size < 1 or page_size > 100:
            page_size = 20

        consignments, total = fetch_consignments_page(
            db, include_deleted, status, order_type, shipping_line, q, page, page_size
        )

        # Serializeing this page of orders
        serialized_consignments = [
            serialize_consignment(consignment) for consignment in consignments
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
        print(e)
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
