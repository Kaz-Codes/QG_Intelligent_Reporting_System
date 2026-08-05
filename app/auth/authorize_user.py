from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.accounts.models import User
from fastapi import HTTPException

#-------------------------------------------
# PERMISSION-BASED AUTHORIZATION
#
# The token carries only the user id, so the user (and their permissions) are
# loaded fresh every request — a permission granted or revoked takes effect on
# the caller's very next request, with no stale token.
#
# An admin (is_admin) passes every check. A normal account passes only if it
# holds the required permission. `authorize` takes one permission name or a list
# of names, any one of which is enough (e.g. submit needs add OR edit).
#
# The user is handed back, so a route that needs the caller (for created_by,
# ownership, etc.) does not have to look them up again.
#-------------------------------------------


def _load_active_user(user_data, db):
    # authenticate() returns the token payload dict; getattr is a fallback in
    # case it is ever handed an object.
    if isinstance(user_data, dict):
        user_id = user_data.get("id")
    else:
        user_id = getattr(user_data, "id", None)

    user = db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.permissions))
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User no longer exists"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Account is inactive"
        )

    return user


def authorize(user_data, permissions, db):
    """Require the caller to be an admin OR to hold one of `permissions`.

    `permissions` is a single permission name or a list of names — holding ANY
    of them is enough. Returns the user on success, 403 otherwise.
    """
    user = _load_active_user(user_data, db)

    if user.is_admin:
        return user

    needed = [permissions] if isinstance(permissions, str) else list(permissions)
    held = {p.name for p in user.permissions}

    if not any(name in held for name in needed):
        raise HTTPException(
            status_code=403,
            detail="Not authorized"
        )

    return user


def require_admin(user_data, db):
    """Admin-only routes: account management, reopening a closed record, and the
    activity log feed. No permission grants these — only is_admin."""
    user = _load_active_user(user_data, db)

    if not user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Admin only"
        )

    return user
