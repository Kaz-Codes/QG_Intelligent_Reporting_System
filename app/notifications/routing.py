import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.accounts.models import User
from app.enums import NotificationTier
from app.notifications.catalogue import get_event

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# WHO RECEIVES AN EVENT
#
# Resolution only. This works out the audience and returns it; it writes
# nothing. Creating the delivery rows is the dispatcher's job, and happens
# outside the request path — see emit.py on why fan-out is not inline.
#
# Three gates, all of which must pass:
#
#   PERMISSION  the catalogue entry names a permission constant, and the user
#               must hold it. is_admin bypasses this, as it bypasses every
#               other authorization check in the system.
#   ADMIN ONLY  some events (a failed backup) are not about anybody's module
#               and go to admins alone, whatever their tier.
#   TIER        see below.
#
# Inactive users are never recipients: a disabled account should not
# accumulate unread work.
#-----------------------------------------------------


#--------------------------------
# TIER: A VOLUME CONTROL, NOT A ROLE
#
# ASSUMPTION, FLAGGED FOR CONFIRMATION. The catalogue pitches each event at a
# tier, and each user carries one too, but how the two compare is a business
# decision that has not been stated. This is the reading implemented here:
#
#   a user receives events pitched at their own tier AND ABOVE it.
#
# So operational (the default) receives everything; managerial drops the
# operational chatter; executive receives only what is pitched at executives.
# Volume falls as seniority rises.
#
# Why this reading and not the reverse: all ten v1 events are pitched at
# managerial or executive, and none at operational. If tier meant "only this
# exact tier receives it", every user on the default setting would receive
# nothing at all, which would make the default useless. Reading it as a floor
# makes the default mean "show me everything until somebody narrows me",
# which is the only sensible thing for a new account.
#
# If the intended rule is the opposite — seniority widens rather than narrows
# — this one function is the only thing that changes.
#--------------------------------

_TIER_ORDER = [
    NotificationTier.OPERATIONAL.value,
    NotificationTier.MANAGERIAL.value,
    NotificationTier.EXECUTIVE.value,
]


def tier_receives(user_tier, event_tier):
    """Does a user at `user_tier` receive an event pitched at `event_tier`?"""
    try:
        return _TIER_ORDER.index(event_tier) >= _TIER_ORDER.index(user_tier)
    except ValueError:
        # An unrecognised tier on either side: deliver rather than drop. A
        # notification nobody asked for is a nuisance; one that silently went
        # to nobody is a failure you never find out about.
        logger.warning(
            "Unrecognised notification tier (user=%r, event=%r) — delivering",
            user_tier, event_tier,
        )
        return True


def user_receives(user, entry):
    """Whether one already-loaded user is an audience for one catalogue entry."""
    if not user.is_active:
        return False

    if entry.get("admin_only") and not user.is_admin:
        return False

    if not tier_receives(user.notification_tier, entry["tier"]):
        return False

    permission = entry.get("permission")

    if permission and not user.is_admin:
        if permission not in {p.name for p in user.permissions}:
            return False

    return True


def recipients_for(db, event_type):
    """Users who should receive `event_type`. Resolves only; writes nothing."""
    entry = get_event(event_type)

    if entry is None:
        logger.error(
            "Cannot route %r — not in the event catalogue", event_type
        )
        return []

    users = db.execute(
        select(User)
        .where(User.is_active == True)  # noqa: E712
        # The permission check reads user.permissions per row; without this
        # that is one query per user.
        .options(selectinload(User.permissions))
    ).scalars().all()

    return [user for user in users if user_receives(user, entry)]
