from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import get_consignment as fetch_consignment 
from app.imports.permissions import CAN_VIEW, allow
from app.imports.routes.router import router
from app.imports.serializers import serialize_consignment
from fastapi import Request, HTTPException

#-------------------------------------------
# ONE WHOLE CONSIGNMENT (EVERY ROLE)
#
# Feeds the detail page and every one of the
# seven wizard steps. All of it comes back in
# a single call, so opening the wizard does not
# fire seven requests to draw one record.
#
# The response carries the calculated figures
# as well as the stored ones: line and
# consignment totals, the PKR value at the
# rate booked on the consignment, transit
# time, clearance time, slippage, stage
# ageing, generated system remarks and the
# list of what is still missing.
#-------------------------------------------

@router.get("/{consignment_id}")
async def get_consignment(consignment_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        allow(request_user_data, CAN_VIEW, db)

        consignment = fetch_consignment(consignment_id, db)

        return {
            "status": 200,
            "message": "Consignment fetched",
            "data": serialize_consignment(consignment, date.today())
        }

    except HTTPException:
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
