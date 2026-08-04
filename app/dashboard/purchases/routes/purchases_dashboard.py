from app.dashboard.purchases.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.purchases.helpers import fetch_filtered_consignments, option_lists
from app.dashboard.purchases.serializers import serialize_purchases_dashboard
from app.dashboard.purchases.calculations import derive_status, PURCHASE_STATUSES
from typing import Optional
from datetime import date


@router.get("/purchases")
def purchases_dashboard(
    request : Request,
    status : Optional[list[str]] = Query(None),
    supplier : Optional[list[str]] = Query(None),
    branch : Optional[list[str]] = Query(None),
    item_category : Optional[list[str]] = Query(None),
    mop : Optional[list[str]] = Query(None),
    sourcing_o : Optional[list[str]] = Query(None),
    po_from_date : Optional[date] = None,
    po_to_date : Optional[date] = None,
    search : Optional[str] = None,
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Dashboards are read only, so every role sees them.
        authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        # Only the filtered set is materialized; the dropdown values come from
        # cheap DISTINCT queries, not from loading the whole table.
        rows = fetch_filtered_consignments(
            db, supplier, branch, item_category, mop,
            sourcing_o, po_from_date, po_to_date, search,
        )

        # Status is derived, so it is filtered here rather than in SQL.
        if status:
            wanted = set(status)
            rows = [r for r in rows if derive_status(r.purchase, r.required_d) in wanted]

        data = {
            # The "view data" table is being removed from the dashboard, so
            # only the aggregates + filter option lists are returned (keeping
            # the payload in KBs, like the imports dashboard).
            **serialize_purchases_dashboard(rows),
            "statuses": PURCHASE_STATUSES,
            **option_lists(db),
        }

        return {
            "status_code": 200,
            "detail": "Purchases dashboard fetched",
            "data": data,
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
