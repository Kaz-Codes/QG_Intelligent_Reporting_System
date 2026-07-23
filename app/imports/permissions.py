from fastapi import HTTPException
from sqlalchemy import select

from app.accounts.models import Role, User

#-----------------------------------------------------
# WHO CAN DO WHAT IN THE IMPORTS MODULE
#
# All of it sits in this one file. Changing a rule later is
# a one line change here instead of a hunt through twenty
# route files.
#
# admin           everything
# manager         create, edit, delete, restore and revert
# entry operator  create, view, and edit only the
#                 consignments they created themselves
# viewer          view only
#
# The role names below must match the names in the roles
# table exactly. If a role is spelled differently in the
# database, change it here and nowhere else.
#-----------------------------------------------------

ADMIN = "admin"
MANAGER = "manager"
ENTRY_OPERATOR = "entry operator"
VIEWER = "viewer"


#--------------------------------
# THE LISTS EACH ROUTE CHECKS AGAINST
#--------------------------------

CAN_VIEW = [ADMIN, MANAGER, ENTRY_OPERATOR, VIEWER]
CAN_CREATE = [ADMIN, MANAGER, ENTRY_OPERATOR]
CAN_EDIT = [ADMIN, MANAGER, ENTRY_OPERATOR]
CAN_DELETE = [ADMIN, MANAGER]
CAN_RESTORE = [ADMIN, MANAGER]
CAN_REVERT = [ADMIN, MANAGER]

# An entry operator is in CAN_EDIT but only for their own
# rows. Every edit route calls check_owner after allow, and
# that is where the restriction actually happens.
OWN_ROWS_ONLY = [ENTRY_OPERATOR]


#--------------------------------
# READ THE LOGGED IN USER OUT OF THE TOKEN
#
# authenticate() hands back whatever was put inside the
# token, so the id is read defensively and the user is then
# loaded from the database. The role always comes from the
# database and never from the token, otherwise an old token
# would keep working after somebody's role was changed.
#--------------------------------

def get_current_user(request_user_data, db):
    if isinstance(request_user_data, dict):
        user_id = request_user_data.get("id")
    else:
        user_id = getattr(request_user_data, "id", None)

    if user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

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

    return user


#--------------------------------
# THE NAME OF A USER'S ROLE
#--------------------------------

def get_role_name(user, db):
    role = db.execute(
        select(Role).where(Role.id == user.role_id)
    ).scalar_one_or_none()

    if role is None:
        raise HTTPException(
            status_code=403,
            detail="Not authorized"
        )

    return role.name.strip().lower()


#--------------------------------
# THE GATE EVERY ROUTE OPENS WITH
#
# Hands back the user and their role name so the route does
# not have to look either of them up a second time.
#--------------------------------

def allow(request_user_data, allowed_roles, db):
    user = get_current_user(request_user_data, db)
    role_name = get_role_name(user, db)

    if role_name not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Not authorized"
        )

    return user, role_name


#--------------------------------
# THE ENTRY OPERATOR RESTRICTION
#
# An entry operator may only change a consignment they
# created. Admin and manager pass straight through.
#--------------------------------

def check_owner(user, role_name, consignment):
    if role_name not in OWN_ROWS_ONLY:
        return

    if consignment.created_by_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only edit consignments you created"
        )
