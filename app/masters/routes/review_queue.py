from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import used_counts
from app.auth.authorize_user import authorize
from app.masters.registry import MASTER_ORDER, MASTERS
from app.masters.routes.router import router
from app.masters.serializers import serialize
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

#-------------------------------------------
# THE REVIEW QUEUE (EVERY ROLE)
#
# Every record that was created inline during
# data entry and has not been confirmed yet,
# gathered from all six lists into one place.
# A Manager works through this, opening each to
# check the details before it counts as a
# proper master.
#
# Only active ones show, since a deactivated
# record is out of use anyway. The count per
# master feeds the "N need review" note on
# each tab.
#-------------------------------------------

@router.get("/review-queue")
async def review_queue(request: Request):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin", "manager", "entry operator", "viewer"], db)

        queue = {}
        total = 0

        for master in MASTER_ORDER:
            config = MASTERS[master]
            model = config["model"]

            query = (
                select(model)
                .where(model.is_verified == False)
                .where(model.is_active == True)
            )

            if config["has_hs"]:
                query = query.options(selectinload(model.hs_codes))

            if master == "agent":
                query = query.options(selectinload(model.primary_port))

            rows = db.execute(query.order_by(model.name)).scalars().all()

            counts = used_counts(master, [row.id for row in rows], db)

            queue[master] = [
                serialize(master, row, counts.get(row.id, 0))
                for row in rows
            ]

            total = total + len(rows)

        return {
            "status": 200,
            "message": "Review queue fetched",
            "data": queue,
            "total": total
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
