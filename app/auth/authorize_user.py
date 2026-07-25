from sqlalchemy import select
from app.accounts.models import Role, User
from fastapi import HTTPException

#-------------------------------------------
# CHECK THE LOGGED IN USER HAS THE RIGHT ROLE
#
# The token only carries the user id, so the
# user and their role are loaded fresh from the
# database every time. Reading the role from
# the database rather than from the token means
# an old token stops working the moment
# somebody's role is changed.
#
# The user is handed back, so a route that
# needs the caller does not have to look them
# up a second time.
#-------------------------------------------

def authorize(user_data, allowed_roles, db):
    # authenticate() returns the token payload, which is a
    # dict, so the id is read as a dict key. getattr is kept
    # as a fallback in case it is ever handed an object.
    if isinstance(user_data, dict):
        user_id = user_data.get("id")
    else:
        user_id = getattr(user_data, "id", None)

    user = db.execute(
        select(User).where(User.id == user_id)
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

    role = db.execute(
        select(Role).where(Role.id == user.role_id)
    ).scalar_one_or_none()

    allowed = [r.strip().lower() for r in allowed_roles]

    if role is None or role.name.strip().lower() not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Not authorized"
        )

    return user
