from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.helpers import get_consignment
from app.imports.models import ConsignmentChangeHistory
from app.imports.permissions import CAN_VIEW, allow
from app.imports.routes.router import router
from app.imports.serializers import serialize_change
from fastapi import Request, HTTPException
from sqlalchemy import select

#-------------------------------------------
# WHAT HAS BEEN CHANGED ON A CONSIGNMENT
# (EVERY ROLE)
#
# Newest first. Each row holds what the fields
# it names held before somebody changed them,
# which is what the revert call needs, and
# says whether it has already been undone.
#
# A deleted consignment still answers here, so
# a manager can see why it went and put it
# back.
#-------------------------------------------

@router.get("/{consignment_id}/changes")
async def get_changes(consignment_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        allow(request_user_data, CAN_VIEW, db)

        consignment = get_consignment(consignment_id, db, include_deleted=True)

        changes = db.execute(
            select(ConsignmentChangeHistory)
            .where(ConsignmentChangeHistory.consignment_id == consignment.id)
            .order_by(ConsignmentChangeHistory.created_at.desc())
        ).scalars().all()

        return {
            "status": 200,
            "message": "Change history fetched",
            "data": [serialize_change(change) for change in changes]
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
