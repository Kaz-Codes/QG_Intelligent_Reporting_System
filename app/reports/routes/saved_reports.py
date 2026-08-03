from fastapi import HTTPException, Request

from app.reports.routes.router import router
from app.database import SessionLocal
from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import authorize
from app.reports.schemas import SavedReportSchema
from app.reports.helpers import (
    list_saved, get_saved, create_saved, update_saved, delete_saved,
)
from app.reports.serializers import serialize_saved

# Reading templates is open to everyone who can reach Reports; saving/editing/
# deleting is an authoring action, so viewers (read-only) are excluded.
READ_ROLES = ["admin", "manager", "viewer", "entry operator"]
WRITE_ROLES = ["admin", "manager", "entry operator"]


def _can_modify(user, saved):
    # Managers/admins may touch any template; an entry operator only their own.
    role = user.role.name.strip().lower() if user.role else ""
    if role in ("admin", "manager"):
        return True
    return saved.created_by_id == user.id


#-----------------------------------------------------
# GET /reports/saved  — every saved template (shared list)
#-----------------------------------------------------

@router.get("/saved")
def list_saved_reports(request: Request):
    db = SessionLocal()
    try:
        authorize(authenticate(request), READ_ROLES, db)
        rows = [serialize_saved(s) for s in list_saved(db)]
        return {"status_code": 200, "detail": "Saved reports fetched", "data": rows}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()


#-----------------------------------------------------
# POST /reports/saved  — create a template
#-----------------------------------------------------

@router.post("/saved")
def create_saved_report(payload: SavedReportSchema, request: Request):
    db = SessionLocal()
    try:
        user = authorize(authenticate(request), WRITE_ROLES, db)
        saved = create_saved(db, payload, user)
        return {
            "status_code": 201,
            "detail": "Saved report created",
            "data": serialize_saved(saved),
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


#-----------------------------------------------------
# GET /reports/saved/{id}  — one template
#-----------------------------------------------------

@router.get("/saved/{report_id}")
def get_saved_report(report_id: int, request: Request):
    db = SessionLocal()
    try:
        authorize(authenticate(request), READ_ROLES, db)
        saved = get_saved(db, report_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Saved report not found")
        return {
            "status_code": 200,
            "detail": "Saved report fetched",
            "data": serialize_saved(saved),
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


#-----------------------------------------------------
# PUT /reports/saved/{id}  — update a template
#-----------------------------------------------------

@router.put("/saved/{report_id}")
def update_saved_report(report_id: int, payload: SavedReportSchema, request: Request):
    db = SessionLocal()
    try:
        user = authorize(authenticate(request), WRITE_ROLES, db)
        saved = get_saved(db, report_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Saved report not found")
        if not _can_modify(user, saved):
            raise HTTPException(status_code=403, detail="Not allowed to edit this report")
        saved = update_saved(db, saved, payload)
        return {
            "status_code": 200,
            "detail": "Saved report updated",
            "data": serialize_saved(saved),
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


#-----------------------------------------------------
# DELETE /reports/saved/{id}  — soft-delete a template
#-----------------------------------------------------

@router.delete("/saved/{report_id}")
def delete_saved_report(report_id: int, request: Request):
    db = SessionLocal()
    try:
        user = authorize(authenticate(request), WRITE_ROLES, db)
        saved = get_saved(db, report_id)
        if saved is None:
            raise HTTPException(status_code=404, detail="Saved report not found")
        if not _can_modify(user, saved):
            raise HTTPException(status_code=403, detail="Not allowed to delete this report")
        delete_saved(db, saved, user)
        return {"status_code": 200, "detail": "Saved report deleted"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        print(e)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        db.close()
