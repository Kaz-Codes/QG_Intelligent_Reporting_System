from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import used_counts
from app.auth.authorize_user import authorize
from app.masters.registry import get_master_config
from app.masters.routes.router import router
from app.masters.serializers import serialize
from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

#-------------------------------------------
# ONE MASTER LIST (EVERY ROLE)
#
# Feeds one tab of the masters screen: the
# table, the search box and the show inactive
# toggle.
#
# Inactive rows are hidden unless they are
# asked for, because a deactivated record
# still exists, it is only kept out of new
# data entry. The search runs across every
# text field the row has.
#
# The "used in" count comes back on each row
# so nobody deactivates a supplier the
# business is still importing from.
#-------------------------------------------

@router.get("/{master}")
async def list_masters(master : str,
                       request: Request,
                       q : str = None,
                       include_inactive : bool = False,
                       unverified_only : bool = False):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, ["admin", "manager", "entry operator", "viewer"], db)

        config = get_master_config(master)
        model = config["model"]

        query = select(model)

        # The two masters with a relationship the screen
        # shows are loaded up front so the list does not
        # fire a query per row.
        if config["has_hs"]:
            query = query.options(selectinload(model.hs_codes))

        if master == "agent":
            query = query.options(selectinload(model.primary_port))

        rows = db.execute(query.order_by(model.name)).scalars().all()

        counts = used_counts(master, [row.id for row in rows], db)

        records = [serialize(master, row, counts.get(row.id, 0)) for row in rows]

        if not include_inactive:
            records = [r for r in records if r["is_active"]]

        if unverified_only:
            records = [r for r in records if not r["is_verified"]]

        if q:
            needle = q.strip().lower()
            records = [r for r in records if _matches(r, needle)]

        return {
            "status": 200,
            "message": "Records fetched",
            "data": records,
            "total": len(records)
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


#--------------------------------
# DOES ANY TEXT ON THIS ROW CONTAIN THE SEARCH
#--------------------------------

def _matches(record, needle):
    for key, value in record.items():
        if key in ["id", "is_active", "is_verified", "used"]:
            continue

        if isinstance(value, list):
            if any(needle in str(part).lower() for part in value):
                return True

        elif value is not None and needle in str(value).lower():
            return True

    return False
