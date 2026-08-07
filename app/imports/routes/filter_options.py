from fastapi import HTTPException, Request
from sqlalchemy import select

from app.imports.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_IMPORTS
from app.imports.models import Consignment, ConsignmentItem
from app.masters.models import Branch, Supplier
from app.enums import Status

#-----------------------------------------------------
# THE LIST SCREEN'S FILTER DROPDOWNS
#
# Built from what is ACTUALLY in the table, not from the enums, because the
# loaded (Excel) rows and rows entered through the ERP do not agree:
#
#   * status — the loader keeps whatever the sheet said, so values like
#     "Order Cancelled" or "LC in Process" exist alongside the eleven canonical
#     ones. Offering only the enum would make those rows unfilterable, so the
#     stored values are returned, canonical ones first (in pipeline order) and
#     any extras after, each flagged so the front end can mark them.
#   * branch / supplier — returned as {id, name} because the list filters by
#     id, while the screen shows names. Only masters actually referenced by a
#     consignment are offered, so the dropdown has no dead entries.
#   * requisition_type — NULL on every loaded item line (the sheet has no such
#     column), so this list is empty until rows are entered through the ERP.
#     Returned anyway, so the front end can say "not recorded on imported rows"
#     rather than silently showing nothing.
#-----------------------------------------------------


@router.get("/filter-options")
def filter_options(request: Request):
    db = SessionLocal()

    try:
        authorize(authenticate(request), CAN_VIEW_IMPORTS, db)

        # Statuses present on non-deleted consignments.
        stored_statuses = {
            s for (s,) in db.execute(
                select(Consignment.current_status)
                .where(Consignment.is_deleted == False)  # noqa: E712
                .distinct()
            ).all() if s
        }

        canonical = [s.value for s in Status]
        canonical_set = set(canonical)

        # EVERY canonical status is offered, in pipeline order, whether or not
        # anything currently sits at it — the filter list has to match the
        # dropdown used when setting a status, or a stage you can select would
        # be one you cannot filter by (and it would appear only once some
        # consignment happened to reach it). Anything the imported sheets left
        # behind is appended after, so those rows stay filterable too.
        ordered = canonical + sorted(stored_statuses - canonical_set)

        statuses = [
            {"value": s, "canonical": s in canonical_set}
            for s in ordered
        ]

        branches = [
            {"id": bid, "name": name}
            for bid, name in db.execute(
                select(Branch.id, Branch.name)
                .where(Branch.consignments.any(Consignment.is_deleted == False))  # noqa: E712
                .order_by(Branch.name)
            ).all()
        ]

        suppliers = [
            {"id": sid, "name": name}
            for sid, name in db.execute(
                select(Supplier.id, Supplier.name)
                .where(Supplier.consignments.any(Consignment.is_deleted == False))  # noqa: E712
                .order_by(Supplier.name)
            ).all()
        ]

        requisition_types = sorted(
            r for (r,) in db.execute(
                select(ConsignmentItem.requisition_type)
                .where(ConsignmentItem.is_deleted == False)  # noqa: E712
                .distinct()
            ).all() if r
        )

        return {
            "status_code": 200,
            "detail": "Filter options fetched",
            "data": {
                "statuses": statuses,
                "branches": branches,
                "suppliers": suppliers,
                "requisition_types": requisition_types,
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
