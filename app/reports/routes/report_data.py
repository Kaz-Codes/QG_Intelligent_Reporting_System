from datetime import date
from typing import Optional

from fastapi import HTTPException, Query, Request

from app.reports.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.reports.helpers import (
    Filters, selected_types, type_included, conditions_for, count_for,
    fetch_slice, plan_slices,
)
from app.reports.serializers import serialize_rows
from app.accounts.permissions import CAN_MAKE_REPORTS


#-----------------------------------------------------
# GET /reports/data
#
# The cross-module report builder. `types` picks which data sources to span;
# the rest are the shared filters. The result is the selected types concatenated
# in a fixed order and paged as one list, so only the rows on the page are ever
# fetched or serialized (the whole point — an unfiltered report must not dump
# every table over the wire the way the old dashboards did).
#-----------------------------------------------------

@router.get("/data")
def reports_data(
    request: Request,
    types: Optional[list[str]] = Query(None),
    item: Optional[list[str]] = Query(None),
    shaft: Optional[list[str]] = Query(None),
    supplier: Optional[list[str]] = Query(None),
    branch: Optional[list[str]] = Query(None),
    category: Optional[list[str]] = Query(None),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
):
    db = SessionLocal()
    try:
        authorize(authenticate(request), CAN_MAKE_REPORTS, db)

        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 25

        filters = Filters(
            item=item, shaft=shaft, supplier=supplier, branch=branch,
            category=category, date_from=date_from, date_to=date_to, search=search,
        )
        types_wanted = selected_types(types)

        # Count each type once (cheap SQL COUNT); a type an active filter cannot
        # honour contributes nothing.
        counts_ordered = []
        conds_by_type = {}
        for report_type in types_wanted:
            if not type_included(report_type, filters):
                counts_ordered.append((report_type, 0))
                continue
            conds = conditions_for(report_type, filters)
            conds_by_type[report_type] = conds
            counts_ordered.append((report_type, count_for(db, report_type, conds)))

        total = sum(count for _, count in counts_ordered)
        offset = (page - 1) * page_size

        rows = []
        for report_type, sub_offset, take in plan_slices(counts_ordered, offset, page_size):
            objs = fetch_slice(db, report_type, conds_by_type[report_type], sub_offset, take)
            rows.extend(serialize_rows(db, report_type, objs))

        return {
            "status_code": 200,
            "detail": "Report data fetched",
            "data": rows,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if total else 0,
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
