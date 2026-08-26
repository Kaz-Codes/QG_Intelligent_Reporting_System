from fastapi import HTTPException, Request
from sqlalchemy import select

from app.logistics.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.accounts.permissions import CAN_VIEW_LOGISTICS
from app.logistics.models import LogisticsConsignment, LogisticsItem
from app.enums import LogisticsStatus, OrderType
import logging

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# THE LIST SCREEN'S FILTER DROPDOWNS
#
# Mirrors the imports version, with one difference that matters:
#
#   * status / order_type — the logistics loader NORMALISES the workbook's
#     vocabulary onto the canonical enums and defaults anything unmapped (see
#     the loading notes in CLAUDE.md), so unlike imports there are no stray
#     stored values to rescue. Every canonical value is still offered whether
#     or not a row currently sits at it — the filter list has to match the
#     dropdown used when SETTING a status, otherwise a stage you can select is
#     one you cannot filter by. Anything unexpected that did land is appended
#     and flagged, so those rows stay filterable.
#   * customer — free text on the order (no customer master), so the only
#     honest source is the DISTINCT of what is stored. Returned as plain
#     strings because the list filters by name, not by id.
#-----------------------------------------------------


def _stored(db, column):
    """DISTINCT non-null values of one column across non-deleted orders."""
    return {
        v for (v,) in db.execute(
            select(column)
            .where(LogisticsConsignment.is_deleted == False)  # noqa: E712
            .distinct()
        ).all() if v
    }


def _stored_item(db, column):
    """DISTINCT non-null values of one LogisticsItem column.

    Job number lives on the ITEM, not the order, so its options cannot come
    from _stored above. Scoped the same way the list is: items that are not
    themselves deleted, belonging to orders that are not deleted — otherwise
    the dropdown offers a job number that filters to nothing.

    A join is correct HERE (unlike in the list query) because this selects
    DISTINCT values of one column. There are no order rows to duplicate and
    no count to corrupt.
    """
    return {
        v for (v,) in db.execute(
            select(column)
            .join(
                LogisticsConsignment,
                LogisticsItem.consignment_id == LogisticsConsignment.id,
            )
            .where(LogisticsConsignment.is_deleted == False)  # noqa: E712
            .where(LogisticsItem.is_deleted == False)  # noqa: E712
            .distinct()
        ).all() if v
    }


def _with_canonical(stored, enum_cls):
    """Canonical values first (in declaration order), then anything else that
    is actually stored, each flagged so the front end can mark the strays."""
    canonical = [e.value for e in enum_cls]
    canonical_set = set(canonical)
    ordered = canonical + sorted(stored - canonical_set)
    return [{"value": v, "canonical": v in canonical_set} for v in ordered]


@router.get("/filter-options")
def filter_options(request: Request):
    db = SessionLocal()

    try:
        authorize(authenticate(request), CAN_VIEW_LOGISTICS, db)

        statuses = _with_canonical(
            _stored(db, LogisticsConsignment.current_status), LogisticsStatus
        )
        order_types = _with_canonical(
            _stored(db, LogisticsConsignment.order_type), OrderType
        )

        customers = sorted(_stored(db, LogisticsConsignment.customer_name))
        departments = sorted(_stored(db, LogisticsConsignment.department))
        job_numbers = sorted(_stored_item(db, LogisticsItem.job_no))

        return {
            "status_code": 200,
            "detail": "Filter options fetched",
            "data": {
                "statuses": statuses,
                "order_types": order_types,
                "customers": customers,
                "departments": departments,
                # From the ITEM table — see _stored_item.
                "job_numbers": job_numbers,
            },
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        logger.exception("Unhandled error in app.logistics.routes.filter_options")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        db.close()
