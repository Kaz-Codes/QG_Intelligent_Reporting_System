import logging

from sqlalchemy import insert, select
from sqlalchemy.orm import selectinload

from app.accounts.models import User
from app.enums import (
    NotificationChannel, NotificationDeliveryStatus, NotificationTier,
)
from app.notifications.catalogue import get_event
from app.notifications.models import NotificationDelivery

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
# TIER: HOW FAR DOWN AN EVENT REACHES
#
# The event's tier is a CEILING, and the rule is cumulative:
#
#     a user receives an event when user_tier <= event_tier,
#     ordered operational < managerial < executive.
#
# So an event tiered executive reaches executive, managerial AND operational
# users — everybody. One tiered operational reaches operational users only.
# Read from the other end: the more senior the pitch, the wider the reach;
# the more senior the USER, the less they see, because only the events pitched
# at their level or higher get through.
#
# That is also why operational is the right default for a new account: it
# receives everything until somebody deliberately narrows it. All ten v1
# events are pitched managerial or executive, so a default of executive would
# leave most accounts seeing almost nothing.
#
# Written as an ordered list and one comparison, not a chain of if-branches,
# so adding a tier is a one-line change here and nowhere else.
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
    """Whether one already-loaded user is an audience for one catalogue entry.

    The gates are ANDed, in the order the rule is written. Nothing here is an
    override of anything else — see the permission note.
    """
    # A disabled account should not accumulate unread work.
    if not user.is_active:
        return False

    # admin_only outranks tier: a failed backup is not about anybody's module
    # and goes to admins whatever tier they are set to.
    if entry.get("admin_only") and not user.is_admin:
        return False

    if not tier_receives(user.notification_tier, entry["tier"]):
        return False

    #-----------------------------------------------------
    # PERMISSION IS A HARD GATE. TIER NEVER OVERRIDES IT.
    #
    # These two are not alternatives and must never be ORed together. Tier
    # says how much someone WANTS to see; permission says what they are
    # ALLOWED to see, and it is the same permission the module's own routes
    # enforce. If a high tier could satisfy this check, the notification panel
    # would become a way to read imports data — supplier names, values, GD
    # numbers, all rendered into the body — without holding CAN_VIEW_IMPORTS.
    # That is a permission bypass with a friendly name.
    #
    # is_admin passes, because is_admin passes every authorization check in
    # the system; that is the one intended exception and it is the same one
    # authorize() makes.
    #-----------------------------------------------------
    permission = entry.get("permission")

    if permission and not user.is_admin:
        if permission not in {p.name for p in user.permissions}:
            return False

    # v1 has no per-user opt-outs. When they arrive they belong HERE, as one
    # more ANDed gate on an already-loaded user — not as a separate pass over
    # the recipient list, which would have to re-query.
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


#--------------------------------
# FAN-OUT
#
# Turns one event into one delivery row per recipient. Called by the
# background worker, NEVER from a web request — see worker.py on why.
#
# The insert is a single executemany, not a loop of db.add(): thirty
# recipients is thirty round trips otherwise, all of them holding a pooled
# connection that live requests are competing for.
#
# v1 delivers IN-APP ONLY. WhatsApp and email are separate channels with
# their own consent and provider concerns (see User.whatsapp_opted_in); when
# they land, this produces one row per channel per user and the per-channel
# senders read their own pending rows.
#--------------------------------

def fan_out(db, event, on_delivered=None):
    """Create the delivery rows for one event. Returns how many were written.

    `on_delivered(user_ids)` is called with the recipients AFTER the rows are
    committed, and is how the live websocket push is triggered without this
    function knowing anything about sockets.

    IT IS A CALLBACK RATHER THAN A PUSH FROM IN HERE for two reasons. This
    runs in a worker THREAD (sync SQLAlchemy — see worker.py), and the socket
    sends are async and belong on the event loop; awaiting them from here is
    not possible and scheduling onto the loop from a thread is a race waiting
    to be written. And it keeps fan-out testable and transport-agnostic: the
    delivery rows are the durable record, the push is a courtesy on top, and
    a failing socket must never affect whether the rows were written.

    Called AFTER the commit, never before, so a push can only ever announce a
    notification that is genuinely in the database — a socket message for a
    row that was then rolled back would show a notification the panel loses
    on its next refresh.
    """
    recipients = recipients_for(db, event.event_type)

    if not recipients:
        # Not an error. An event can legitimately reach nobody — no active
        # user holds the permission, or everyone is tiered above it. The
        # worker marks it done regardless, so it is not retried forever.
        logger.info(
            "Notification event %s (%s) matched no recipients",
            event.id, event.event_type,
        )
        return 0

    db.execute(
        insert(NotificationDelivery),
        [
            {
                "event_id": event.id,
                "user_id": user.id,
                "channel": NotificationChannel.IN_APP.value,
                "status": NotificationDeliveryStatus.PENDING.value,
            }
            for user in recipients
        ],
    )
    db.commit()

    if on_delivered is not None:
        try:
            on_delivered([user.id for user in recipients])
        except Exception:
            # The rows are committed and the notification exists. A failure
            # to announce it live is not a reason to report the fan-out as
            # failed — the panel picks it up on its next load either way.
            logger.exception(
                "Live push failed for notification event %s (%s); the "
                "delivery rows are written and unaffected",
                event.id, event.event_type,
            )

    return len(recipients)
