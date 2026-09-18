from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.masters.helpers import used_counts
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_MASTER
from app.masters.registry import get_master_config
from app.masters.routes.router import router
from app.masters.serializers import serialize
from app.dashboard.references import sql_search_clause
from fastapi import Request, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import logging

logger = logging.getLogger(__name__)

#-------------------------------------------
# ONE MASTER LIST (EVERY ROLE)
#
# Feeds one tab of the masters screen: the
# table, the search box, the show inactive
# toggle and its pagination.
#
# Inactive rows are hidden unless they are
# asked for, because a deactivated record
# still exists, it is only kept out of new
# data entry. The search runs in SQL, across
# each master's own `search_fields` (registry.py)
# — not a Python scan over the whole table, which
# stopped being viable once the ports master grew
# to ~133,000 rows from its own dedicated workbook.
#
# The "used in" count comes back on each row
# so nobody deactivates a supplier the
# business is still importing from. It is only
# ever computed over the PAGE just fetched, not
# the whole table — see used_counts, which already
# takes an `ids` list rather than assuming "every row".
#-------------------------------------------

@router.get("/{master}")
async def list_masters(master : str,
                       request: Request,
                       q : str = None,
                       include_inactive : bool = False,
                       unverified_only : bool = False,
                       page : int = 1,
                       page_size : int = 20):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        authorize(request_user_data, CAN_VIEW_MASTER, db)

        config = get_master_config(master)
        model = config["model"]
        columns = [getattr(model, field) for field in config["search_fields"]]

        conditions = []

        if not include_inactive:
            conditions.append(model.is_active == True)

        if unverified_only:
            conditions.append(model.is_verified == False)

        clause = sql_search_clause(q, *columns)
        if clause is not None:
            conditions.append(clause)

        # An out-of-range value falls back rather than 400ing — the screen
        # should still render, same convention as every other paginated list
        # in this app (see app/imports/routes/get_consignments_list.py).
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 20

        total = db.execute(
            select(func.count()).select_from(model).where(*conditions)
        ).scalar()

        query = select(model).where(*conditions)

        # The two masters with a relationship the screen
        # shows are loaded up front so the list does not
        # fire a query per row.
        if config["has_hs"]:
            query = query.options(selectinload(model.hs_codes))

        if master == "agent":
            query = query.options(selectinload(model.primary_port))

        rows = db.execute(
            query.order_by(model.name).limit(page_size).offset((page - 1) * page_size)
        ).scalars().all()

        counts = used_counts(master, [row.id for row in rows], db)

        records = [serialize(master, row, counts.get(row.id, 0)) for row in rows]

        total_pages = (total + page_size - 1) // page_size if total else 0

        return {
            "status": 200,
            "message": "Records fetched",
            "data": records,
            "total": total,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
            },
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.masters.routes.list_masters")
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )

    finally:
        db.close()
