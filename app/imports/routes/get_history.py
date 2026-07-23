from datetime import date

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.calculations import stage_ageing, system_remarks
from app.imports.helpers import get_consignment
from app.imports.permissions import CAN_VIEW, allow
from app.imports.routes.router import router
from app.imports.serializers import serialize_eta_revision, serialize_status_update
from fastapi import Request, HTTPException

#-------------------------------------------
# THE MOVEMENT HISTORY OF ONE CONSIGNMENT
# (EVERY ROLE)
#
# Feeds the history feed on step 5 and on the
# detail page: status changes and ETA
# revisions merged into one list, newest
# first, with how long the consignment sat at
# each stage.
#
# The system remarks come back with it,
# generated from these two logs every time
# rather than stored. Keeping them as a text
# field would let a user edit them and would
# destroy the delay analytics.
#-------------------------------------------

@router.get("/{consignment_id}/history")
async def get_history(consignment_id : int, request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        allow(request_user_data, CAN_VIEW, db)

        consignment = get_consignment(consignment_id, db)
        today = date.today()

        feed = []

        for update in consignment.status_updates:
            feed.append({
                "kind": "status",
                "on": update.effective_date.isoformat(),
                "entry": serialize_status_update(update)
            })

        for revision in consignment.eta_revisions:
            feed.append({
                "kind": "eta",
                "on": revision.created_at.date().isoformat(),
                "entry": serialize_eta_revision(revision)
            })

        feed.sort(key=lambda row: row["on"], reverse=True)

        return {
            "status": 200,
            "message": "History fetched",
            "data": feed,
            "stage_ageing": stage_ageing(consignment.status_updates, today),
            "system_remarks": system_remarks(
                consignment, consignment.eta_revisions,
                consignment.status_updates, today
            )
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
