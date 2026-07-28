from app.enums import LogAction
from app.logs.models import ActivityLog

#-----------------------------------------------------
# WRITING A LOG AND MAKING SENSE OF A REQUEST
#
# One place that saves a log row, and two small readers that
# work out from the request what was done and to what, so
# the middleware does not have to know the shape of every
# url in the system.
#-----------------------------------------------------


#--------------------------------
# SAVE ONE LOG ROW
#--------------------------------

def write_log(db, user_id, username, action, method=None, path=None,
              status_code=None, entity_type=None, entity_id=None, detail=None):

    log = ActivityLog(
        user_id=user_id,
        username=username,
        action=action,
        method=method,
        path=path,
        status_code=status_code,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=detail
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log


#--------------------------------
# A LOG ROW AS PLAIN JSON
#
# Used both by the live websocket feed and by the history
# list, so an entry looks the same whichever way it arrives.
#--------------------------------

def serialize_log(log):
    return {
        "id": log.id,
        "user_id": log.user_id,
        "username": log.username,
        "action": log.action,
        "method": log.method,
        "path": log.path,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "status_code": log.status_code,
        "detail": log.detail,
        # stringified so the websocket's send_json can handle it
        "created_at": log.created_at.isoformat() if log.created_at else None
    }


#--------------------------------
# WHAT WAS ACTED ON
#
# Pulled straight off the path. The first part is the kind
# of thing, e.g. consignments, and the first number after it
# is which one.
#--------------------------------

def parse_entity(path):
    parts = [part for part in path.split("/") if part]

    entity_type = parts[0] if parts else None
    entity_id = None

    for part in parts[1:]:
        if part.isdigit():
            entity_id = int(part)
            break

    return entity_type, entity_id


#--------------------------------
# WHAT KIND OF ACTION IT WAS
#
# The last part of the path names the specific action for
# the routes that have one, otherwise it falls back to the
# request method. Adding a new action word is one line here.
#--------------------------------

ACTION_BY_SUFFIX = {
    "revert": LogAction.REVERT.value,
    "restore": LogAction.RESTORE.value,
    "reactivate": LogAction.RESTORE.value,
    "verify": LogAction.VERIFY.value,
    "status": LogAction.STATUS_CHANGE.value,
    "deactivate": LogAction.DELETE.value,
}

ACTION_BY_METHOD = {
    "POST": LogAction.CREATE.value,
    "PUT": LogAction.UPDATE.value,
    "PATCH": LogAction.UPDATE.value,
    "DELETE": LogAction.DELETE.value,
}


def classify_action(method, path):
    parts = [part for part in path.split("/") if part]
    last = parts[-1] if parts else ""

    if last in ACTION_BY_SUFFIX:
        return ACTION_BY_SUFFIX[last]

    return ACTION_BY_METHOD.get(method, method)
