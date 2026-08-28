#-----------------------------------------------------
# A NOTIFICATION AS PLAIN JSON
#
# Used by the list route AND by the websocket push, so a notification looks
# identical whether it arrived live or was loaded with the page. The panel
# renders one component either way — if these two drifted apart, a live
# notification would look different from the same notification after a
# refresh.
#
# The message is read from the stored title/body and is NEVER re-rendered
# from the payload here. The event says what it said when it was raised, even
# after the consignment it describes has moved on. `payload` is passed through
# as well, for click-through and for explaining a wrong-looking message.
#-----------------------------------------------------


def _iso(value):
    # Stringified because the websocket's send_json cannot serialize a
    # datetime, and because the list route should not disagree with it.
    return value.isoformat() if value else None


def serialize_event(event):
    return {
        "id": event.id,
        "event_type": event.event_type,
        "severity": event.severity,
        "tier": event.tier,
        "module": event.module,
        "title": event.title,
        "body": event.body,
        # Polymorphic and deliberately not a foreign key — see models.py. The
        # panel resolves these into a link; nothing enforces that they point
        # at a row that still exists.
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "branch": event.branch,
        "payload": event.payload or {},
        "created_at": _iso(event.created_at),
    }


def serialize_delivery(delivery):
    """One row of the panel: the recipient's read state, plus its event."""
    return {
        "id": delivery.id,
        "channel": delivery.channel,
        "status": delivery.status,
        # NULL read_at means unread. The panel needs the timestamp, not just
        # the boolean — see the models.py note on why it is stored that way.
        "read_at": _iso(delivery.read_at),
        "is_read": delivery.read_at is not None,
        "created_at": _iso(delivery.created_at),
        "event": serialize_event(delivery.event),
    }
