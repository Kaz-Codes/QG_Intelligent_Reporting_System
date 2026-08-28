import logging

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.notifications.catalogue import get_event
from app.notifications.models import NotificationEvent

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# RAISING AN EVENT
#
# EMITTING A NOTIFICATION MUST NEVER BREAK A BUSINESS TRANSACTION. A
# consignment saves or fails on its own merits; whether anybody got told about
# it is a side effect and is not allowed a vote. Three things enforce that,
# and all three matter:
#
#   1. IT OPENS ITS OWN SESSION. The caller's session is never touched. If
#      this shared the caller's transaction, a failed insert here would poison
#      that transaction and roll the consignment back — and a caller that
#      rolled back for its own reasons would silently take the notification
#      with it. Separate sessions is what makes the two independent.
#
#   2. IT NEVER RAISES. Everything is wrapped; failures are logged and
#      swallowed, and the caller gets None. A caller is not expected to check
#      the return value, and must never be expected to handle an exception.
#
#   3. IT DOES NOT FAN OUT. This writes the EVENT — the fact — and stops.
#      Working out who receives it and writing their delivery rows is bulk
#      work that must not happen inside a web request while holding a pooled
#      connection. That is a separate step; routing.py resolves recipients,
#      and the dispatcher that calls it runs outside the request path.
#
# DEDUPE IS OPTIMISTIC, NOT CHECKED. Insert, and treat the unique violation as
# a no-op success. Checking first and inserting second races: two concurrent
# emits both see nothing, both insert, and one crashes — or worse, both
# succeed on a database without the constraint.
#-----------------------------------------------------


class _Blanks(dict):
    """Renders an absent template variable as its own placeholder.

    A message missing one value should still be readable and should still say
    what is missing — losing the whole notification because a payload key was
    forgotten trades a small defect for a total one.
    """

    def __missing__(self, key):
        return "{" + key + "}"


def render(template, payload):
    try:
        return template.format_map(_Blanks(payload or {}))
    except Exception:
        # A malformed template is a bug to fix, not a reason to lose the
        # event; keep the raw template so it is obvious in the panel.
        logger.exception("Notification template failed to render: %r", template)
        return template


def emit(event_type, payload=None, *, entity_type=None, entity_id=None,
         branch=None, dedupe_key=None):
    """Record that a business event happened. Returns its id, or None.

    None means one of three things, none of which the caller should act on:
    the event type is not in the catalogue, an identical event was already
    recorded (dedupe), or something failed and was logged. No exception ever
    leaves this function.
    """
    try:
        entry = get_event(event_type)

        if entry is None:
            # Refused rather than guessed at — see catalogue.py.
            logger.error(
                "Notification not emitted: %r is not in the event catalogue",
                event_type,
            )
            return None

        payload = payload or {}

        event = NotificationEvent(
            event_type=event_type,
            # Copied from the catalogue, not referenced — the event keeps the
            # classification it was raised under.
            severity=entry["severity"],
            tier=entry["tier"],
            module=entry["module"],
            title=render(entry["title_template"], payload),
            body=render(entry["body_template"], payload),
            entity_type=entity_type,
            entity_id=entity_id,
            branch=branch,
            payload=payload,
            dedupe_key=dedupe_key,
        )

        db = SessionLocal()

        try:
            db.add(event)
            db.commit()
            return event.id

        except IntegrityError:
            # The dedupe key is already present: this same real-world event
            # has been recorded. Nothing to do, and nothing went wrong.
            db.rollback()
            logger.debug(
                "Notification %r deduped on key %r", event_type, dedupe_key
            )
            return None

        finally:
            db.close()

    except Exception:
        # The whole point: a side effect does not get to break the caller.
        logger.exception(
            "Notification %r could not be emitted — swallowed so the caller "
            "is unaffected", event_type,
        )
        return None
