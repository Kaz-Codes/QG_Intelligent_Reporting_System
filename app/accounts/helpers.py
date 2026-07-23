from sqlalchemy import select
from fastapi import HTTPException

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
        "role": {
            "id": user.role.id,
            "name": user.role.name
        } if user.role else None,
        "is_active": user.is_active
    }
