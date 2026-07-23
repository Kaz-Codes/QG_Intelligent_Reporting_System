from datetime import date
from typing import Optional

from app.auth.authenticate_user import authenticate
from app.database import SessionLocal
from app.imports.calculations import CLOSED_STATUS, STAGE_GROUPS
from app.imports.models import Consignment, ConsignmentItem
from app.imports.permissions import CAN_VIEW, allow
from app.imports.routes.router import router
from app.imports.serializers import serialize_list_row
from app.masters.models import Supplier
from fastapi import Request, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

#-------------------------------------------
# THE CONSIGNMENT LIST (EVERY ROLE)
#
# Feeds the list screen: the six stage
# pipeline across the top, the filter bar, the
# sortable table and the pager.
#
# Soft deleted consignments never appear here.
# "Arrived at works" is treated as closed and
# is hidden unless it is asked for, either by
# the toggle, by the Closed pipeline segment
# or by the status filter.
#
# The plain filters run in SQL. The three that
# depend on a worked out figure, missing
# information, slippage and the PKR value, are
# applied afterwards in python, because there
# is no column to sort them on. This runs on a
# LAN for thirty people, so that is a fair
# trade for code somebody can read.
#-------------------------------------------

SORT_KEYS = ["id", "status", "etd", "eta", "slip", "value", "pkr"]


def sort_value(row, key):
    if key == "status":
        return row["current_status"] or ""

    if key in ["etd", "eta"]:
        return row[key] or "9999-12-31"

    if key == "slip":
        return row["slippage_days"] or 0

    if key == "value":
        return float(row["foreign_total"] or 0)

    if key == "pkr":
        return float(row["pkr_total"] or 0)

    return row["id"]


@router.get("/")
async def list_consignments(
    request: Request,
    q : Optional[str] = None,
    branch_id : Optional[int] = None,
    supplier_id : Optional[int] = None,
    status : Optional[str] = None,
    requisition_type : Optional[str] = None,
    stage_group : Optional[str] = None,
    incomplete : bool = False,
    include_closed : bool = False,
    sort : str = "id",
    direction : str = "desc",
    page : int = 1,
    per_page : int = 10
):
    db = SessionLocal()

    try:
        request_user_data = authenticate(request)
        allow(request_user_data, CAN_VIEW, db)

        if sort not in SORT_KEYS:
            sort = "id"

        if page < 1:
            page = 1

        if per_page < 1 or per_page > 200:
            per_page = 10

        # Everything the list shows is loaded up front.
        # Without this the page fires one query per row per
        # relationship, which is the only realistic
        # performance problem this system has.
        query = (
            select(Consignment)
            .options(
                selectinload(Consignment.branch),
                selectinload(Consignment.supplier),
                selectinload(Consignment.clearing_agent),
                selectinload(Consignment.items),
                selectinload(Consignment.payments),
                selectinload(Consignment.eta_revisions),
                selectinload(Consignment.status_updates),
            )
            .where(Consignment.is_deleted == False)
        )

        if branch_id is not None:
            query = query.where(Consignment.branch_id == branch_id)

        if supplier_id is not None:
            query = query.where(Consignment.supplier_id == supplier_id)

        if status:
            query = query.where(Consignment.current_status == status)

        if requisition_type:
            query = query.where(
                Consignment.id.in_(
                    select(ConsignmentItem.consignment_id).where(
                        ConsignmentItem.requisition_type == requisition_type
                    )
                )
            )

        # A completed consignment is hidden unless somebody
        # asked for it one of the three ways.
        asked_for_closed = (
            include_closed
            or stage_group == "Closed"
            or status == CLOSED_STATUS
        )

        if not asked_for_closed:
            query = query.where(Consignment.current_status != CLOSED_STATUS)

        if q:
            pattern = "%" + q.strip() + "%"

            query = query.where(
                or_(
                    Consignment.origin.ilike(pattern),
                    Consignment.gd_number.ilike(pattern),
                    Consignment.instrument_number.ilike(pattern),
                    Consignment.supplier_id.in_(
                        select(Supplier.id).where(Supplier.name.ilike(pattern))
                    ),
                    Consignment.id.in_(
                        select(ConsignmentItem.consignment_id).where(
                            or_(
                                ConsignmentItem.item_name.ilike(pattern),
                                ConsignmentItem.item_code.ilike(pattern),
                                ConsignmentItem.reference_number.ilike(pattern),
                                ConsignmentItem.job_number.ilike(pattern),
                                ConsignmentItem.mo_number.ilike(pattern),
                            )
                        )
                    ),
                )
            )

        consignments = db.execute(query).scalars().all()

        today = date.today()
        rows = [serialize_list_row(row, today) for row in consignments]

        # Counted before the stage filter is applied, so
        # clicking a segment does not empty the strip that
        # was just clicked.
        pipeline = []

        for name, statuses in STAGE_GROUPS:
            pipeline.append({
                "group": name,
                "count": len([row for row in rows if row["stage_group"] == name])
            })

        if stage_group:
            rows = [row for row in rows if row["stage_group"] == stage_group]

        if incomplete:
            rows = [row for row in rows if row["missing"]]

        rows.sort(
            key=lambda row: sort_value(row, sort),
            reverse=(direction != "asc")
        )

        total = len(rows)
        start = (page - 1) * per_page
        page_rows = rows[start:start + per_page]

        return {
            "status": 200,
            "message": "Consignments fetched",
            "data": page_rows,
            "pipeline": pipeline,
            "total": total,
            "page": page,
            "per_page": per_page
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
