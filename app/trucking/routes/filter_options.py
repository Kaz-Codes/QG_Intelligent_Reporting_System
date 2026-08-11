from fastapi import HTTPException, Request
from sqlalchemy import select

from app.trucking.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_TRUCKING
from app.trucking.models import TruckingConsignment
from app.enums import MovementType

#-----------------------------------------------------
# THE LIST SCREEN'S FILTER DROPDOWNS
#
# Mirrors imports and logistics:
#
#   * movement_type — every canonical value is offered whether or not a job
#     currently sits at it, because the filter list has to match the dropdown
#     used when SETTING one; anything unexpected that did land is appended and
#     flagged so those rows stay filterable.
#   * source — where the job came from ("from-logistics", "from-import-fob",
#     or NULL for one entered by hand). Returned as the stored values, since
#     it is written by the cross-module hand-off rather than chosen from a
#     fixed list on this screen.
#   * transporter — free text on the job (no transporter master), so the only
#     honest source is the DISTINCT of what is stored.
#-----------------------------------------------------


def _stored(db, column):
    """DISTINCT non-null values of one column across non-deleted jobs."""
    return {
        v for (v,) in db.execute(
            select(column)
            .where(TruckingConsignment.is_deleted == False)  # noqa: E712
            .distinct()
        ).all() if v
    }


@router.get("/filter-options")
def filter_options(request: Request):
    db = SessionLocal()

    try:
        authorize(authenticate(request), CAN_VIEW_TRUCKING, db)

        canonical = [m.value for m in MovementType]
        canonical_set = set(canonical)
        stored_types = _stored(db, TruckingConsignment.movement_type)
        ordered = canonical + sorted(stored_types - canonical_set)

        movement_types = [
            {"value": v, "canonical": v in canonical_set} for v in ordered
        ]

        return {
            "status_code": 200,
            "detail": "Filter options fetched",
            "data": {
                "movement_types": movement_types,
                "sources": sorted(_stored(db, TruckingConsignment.source)),
                "transporters": sorted(_stored(db, TruckingConsignment.transporter_name)),
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
