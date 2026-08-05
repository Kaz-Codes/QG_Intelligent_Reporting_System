from sqlalchemy import select
from fastapi import HTTPException

from app.accounts.models import Permission
from app.accounts.permissions import ALL_PERMISSIONS_SET

#-------------------------------------
# CHECK EXISTENCE OF ANY RECORD
#
# Fetch a row by id, or say plainly that it is
# not there. A missing row is a 404, not a 500,
# so the "not found" case is raised on its own
# and let through rather than being swallowed
# and turned into a server error.
#-------------------------------------

def check_existence(entity_id, model, db):
    entity = db.execute(
        select(model).where(model.id == entity_id)
    ).scalar_one_or_none()

    if entity is None:
        raise HTTPException(
            status_code=404,
            detail="Entity not found"
        )

    return entity


#-------------------------------------
# A USER AS PLAIN JSON
#
# The password is included on purpose. These
# routes are admin only, and the admin is meant
# to be able to see every account's password.
#-------------------------------------

def serialize_user(user):
    return {
        "id": user.id,
        "username": user.username,
        "password": user.password,
        "is_admin": user.is_admin,
        "permissions": [p.name for p in user.permissions],
        "is_active": user.is_active
    }


#-------------------------------------
# ASSIGN AN ACCOUNT'S ADMIN FLAG + PERMISSIONS
#
# Shared by create and edit. An admin holds no permissions (is_admin passes
# everything on its own), so the list is cleared for admins. For a normal
# account the given names are validated against the catalogue — an unknown name
# is a 400, not a silently dropped permission — and the matching Permission rows
# replace whatever the user held before.
#-------------------------------------

def apply_account_access(db, user, is_admin, permission_names):
    user.is_admin = is_admin

    if is_admin:
        user.permissions = []
        return

    names = list(dict.fromkeys(permission_names or []))  # de-dupe, keep order

    unknown = [n for n in names if n not in ALL_PERMISSIONS_SET]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown permission(s): {', '.join(unknown)}"
        )

    user.permissions = db.execute(
        select(Permission).where(Permission.name.in_(names))
    ).scalars().all()
