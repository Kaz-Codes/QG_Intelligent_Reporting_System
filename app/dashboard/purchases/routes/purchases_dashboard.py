from app.dashboard.purchases.routes.router import router
from fastapi import Request, HTTPException, Query
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.purchases.helpers import fetch_consignments, fetch_filtered_consignments
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

        # Every row (for the filter option lists) and the filtered set.
        all_rows = fetch_consignments(db)
        rows = fetch_filtered_consignments(
            db, supplier, branch, item_category, mop,
            sourcing_o, po_from_date, po_to_date, search,
        )

        # Status is derived, so it is filtered here rather than in SQL.
        if status:
            wanted = set(status)
            rows = [r for r in rows if derive_status(r.purchase, r.required_d) in wanted]

        # Filter option lists, from the whole table.
        suppliers = set()
        branches = set()
        sourcing_officers = set()
        mops = set()
        item_categories = set()

        for row in all_rows:
            if row.supplier:
                suppliers.add(row.supplier)
            if row.branch:
                branches.add(row.branch)
            if row.sourcing_o:
                sourcing_officers.add(row.sourcing_o)
            if row.mop:
                mops.add(row.mop)
            if row.item and row.item.category:
                item_categories.add(row.item.category)

        data = {
            # The "view data" table is being removed from the dashboard, so
            # only the aggregates + filter option lists are returned (keeping
            # the payload in KBs, like the imports dashboard).
            **serialize_purchases_dashboard(rows),
            "statuses": PURCHASE_STATUSES,
            "suppliers": sorted(suppliers),
            "branches": sorted(branches),
            "sourcing_officers": sorted(sourcing_officers),
            "mops": sorted(mops),
            "item_categories": sorted(item_categories),
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
