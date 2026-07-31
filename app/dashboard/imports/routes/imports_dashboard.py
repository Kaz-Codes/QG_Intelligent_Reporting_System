from app.dashboard.imports.routes.router import router
from fastapi import Request, HTTPException
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.dashboard.imports.helpers import fetch_consignments, fetch_filtered_consigments
from app.dashboard.imports.serializers import serialize_imports_dashboard
from typing import Optional
from datetime import date

@router.get("/imports")
def imports_dashboard(
    request : Request,
    work : Optional[str] = None,
    supplier : Optional[str] = None,
    country : Optional[str] = None,
    item_category : Optional[str] = None,
    status : Optional[str] = None,
    mode_of_shipment : Optional[str] = None,
    from_date : Optional[date] = None,
    to_date : Optional[date] = None
    ):

    db = SessionLocal()

    try:

        # Authenticate user (whether user is logged in or not)
        user_payload = authenticate(request)

        # Authorize user (Check whether user is allowed for this
        # action). Dashboards are read only, so every role sees them.
        user = authorize(user_payload, ["admin", "manager", "viewer", "entry operator"], db)

        consignments = fetch_consignments(db)
        filtered_consignments = fetch_filtered_consigments(db, work, status, item_category, supplier, country, from_date, to_date, mode_of_shipment)

        works = set()
        suppliers = set()
        countries = set()
        item_categories = set()
        statuses = set()

        for consignment in consignments:
            if consignment.branch and consignment.branch.name:
                works.add(consignment.branch.name)
            if consignment.supplier:
                suppliers.add(consignment.supplier.name)
            if consignment.origin:
                countries.add(consignment.origin)
            for item in consignment.items:
                if item.item and item.item.category:
                    item_categories.add(item.item.category)

            if consignment.current_status:
                statuses.add(consignment.current_status)


        data = {
            "consignments": serialize_imports_dashboard(filtered_consignments),
            "works" : sorted(works),
            "suppliers" : sorted(suppliers),
            "countries" : sorted(countries),
            "item_categories" : sorted(item_categories),
            "status" : sorted(statuses)
        }

        return {
            "status_code":200,
            "detail":"Imports dashboard fetched",
            "data": data
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
