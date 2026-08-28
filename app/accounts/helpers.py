from datetime import datetime, timezone

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
        "is_active": user.is_active,
        "notification_tier": user.notification_tier,
        "phone_number": user.phone_number,
        "whatsapp_opted_in": user.whatsapp_opted_in,
        # Read-only to the client: it is set here, never accepted from a
        # payload — see apply_notification_settings. Returned so the admin
        # screen can show WHEN consent was given, which is the whole point of
        # storing it.
        "whatsapp_opted_in_at": (
            user.whatsapp_opted_in_at.isoformat()
            if user.whatsapp_opted_in_at else None
        ),
    }


#-------------------------------------
# NOTIFICATION TIER + WHATSAPP CONSENT
#
# Shared by create and edit, so the three rules below hold on every write path
# rather than being repeated (and eventually diverging) in two routes.
#
#
# 1. ONLY AN ADMIN MAY SET notification_tier.
#
# The tier decides which events reach an account, and executive is NARROWER,
# not wider (see routing.py — a user receives an event when user_tier <=
# event_tier). So the risk is not someone promoting themselves to see more;
# it is someone quietly turning their own alerts DOWN and then not being
# accountable for missing them.
#
# Today every /users route is require_admin, so a non-admin cannot reach this
# at all and the check can never fire. It is here anyway, on the FIELD rather
# than on the route, because "accounts are admin-only" is a property of the
# current routes and not of this rule: the moment a self-service profile
# screen is added — change your own password, set your own phone — it will
# reuse UserSchema, and the tier would ride in with it. Enforcing at the route
# alone makes that a silent privilege escalation; enforcing here makes it a
# 403.
#
#
# 2. CONSENT REQUIRES A NUMBER TO CONSENT WITH. Opting in with no phone number
# is not a half-valid state to store, it is a contradiction — there is nothing
# to message. The front end disables the checkbox, but that is UX; this is the
# boundary.
#
#
# 3. THE OPT-IN TIMESTAMP IS SERVER-SET, NEVER SENT. Meta requires evidence of
# opt-in, and a boolean without a date cannot evidence one. Accepting the
# timestamp from the client would let it be backdated, which is worse than not
# recording it: it would look like evidence while being unverifiable.
# Set when consent starts, cleared when it is withdrawn — the flag and the
# timestamp always move together.
#-------------------------------------

def apply_notification_settings(db, user, schema, acting_user):
    if schema.notification_tier != user.notification_tier:
        if not acting_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only an admin may change a notification tier"
            )

        user.notification_tier = schema.notification_tier

    user.phone_number = schema.phone_number

    opted_in = bool(schema.whatsapp_opted_in)

    if opted_in and not user.phone_number:
        raise HTTPException(
            status_code=400,
            detail="A phone number is required to opt in to WhatsApp alerts"
        )

    if opted_in:
        # Only stamped when consent STARTS. Re-saving an account that was
        # already opted in must not move the date — that would rewrite the
        # record of when they actually agreed, every time anything else on the
        # form changed.
        if not user.whatsapp_opted_in:
            user.whatsapp_opted_in_at = datetime.now(timezone.utc)
    else:
        user.whatsapp_opted_in_at = None

    user.whatsapp_opted_in = opted_in


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

    if not names:
        raise HTTPException(
            status_code=400,
            detail="At least one permission must be assigned to the user"
        )

    unknown = [n for n in names if n not in ALL_PERMISSIONS_SET]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown permission(s): {', '.join(unknown)}"
        )

    user.permissions = db.execute(
        select(Permission).where(Permission.name.in_(names))
    ).scalars().all()
