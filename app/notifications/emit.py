import logging
import string

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.notifications.catalogue import get_event
from app.notifications.models import NotificationEvent

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# RAISING AN EVENT
#
# EMITTING A NOTIFICATION MUST NEVER BREAK A BUSINESS TRANSACTION. A
# consignment saves or fails on its own merits; whether anyone was told about
# it is a side effect and does not get a vote. Three properties enforce that:
#
#   1. IT NEVER RAISES. The whole body is wrapped. Failures are logged and
#      swallowed and the caller gets None back. No caller is expected to catch
#      anything, and none is expected to check a return value either.
#
#   2. IT USES ITS OWN SESSION — see the long note on that below.
#
#   3. IT DOES NOT FAN OUT. This writes the EVENT, the fact that something
#      happened, and stops. Working out who receives it and writing their
#      delivery rows is O(recipients) work that must not happen in a web
#      request; the background worker does it. That keeps emit O(1), so a
#      consignment save pays for one INSERT no matter how many people are
#      eventually told.
#
# DEDUPE IS OPTIMISTIC. Insert and let the unique index decide, treating the
# violation as a no-op success. A check-then-insert races: two concurrent
# emits both find nothing, both insert, and one blows up.
#-----------------------------------------------------


class _Blanks(dict):
    """Renders an absent template variable as its own placeholder."""

    def __init__(self, values, missing):
        super().__init__(values or {})
        self._missing = missing

    def __missing__(self, key):
        self._missing.append(key)
        return "{" + key + "}"


def render(template, payload, event_type=""):
    """Fill a catalogue template from the payload.

    A MISSING VARIABLE DOES NOT LOSE THE EVENT. The placeholder is rendered
    literally and the gap is logged: a message reading "{branch}" is ugly, but
    it still tells somebody what happened and it names its own defect. Raising
    here would trade one missing word for the entire notification.
    """
    missing = []

    try:
        rendered = string.Formatter().vformat(template, (), _Blanks(payload, missing))
    except Exception:
        # A malformed template is a bug to fix, not a reason to drop the
        # event. Keep the raw template so it is obvious in the panel.
        logger.exception(
            "Notification template could not be rendered for %r: %r",
            event_type, template,
        )
        return template

    if missing:
        logger.warning(
            "Notification %r rendered with missing payload variables: %s",
            event_type, ", ".join(sorted(set(missing))),
        )

    return rendered


def emit(db, event_type, *, payload, entity_type=None, entity_id=None,
         branch=None, dedupe_key=None):
    """Record that a business event happened. Always returns None.

    `db` IS THE CALLER'S SESSION AND IS DELIBERATELY NOT WRITTEN THROUGH.
    It is accepted so call sites read like every other helper in the codebase
    (`something(db, ...)`) and so a future version can READ context through it
    without changing every caller. It must never become the session this
    function writes on — see below.
    """
    try:
        entry = get_event(event_type)

        if entry is None:
            # Refused, not guessed at: the catalogue is the whole list of
            # things allowed to interrupt somebody.
            logger.error(
                "Notification not emitted: %r is not in the event catalogue",
                event_type,
            )
            return None

        payload = payload or {}

        #-----------------------------------------------------
        # WHY A SEPARATE SESSION, NOT THE CALLER'S
        #
        # This looks like pointless duplication — the caller already handed us
        # a perfectly good session. Using it would be a bug in both
        # directions:
        #
        #   * A notification failure would mark the CALLER'S transaction as
        #     rolled back, so a consignment that saved perfectly well would be
        #     lost because nobody could be told about it.
        #   * A caller that rolls back for its own reasons — a validation
        #     failure three lines later — would silently take the notification
        #     with it, and the event would vanish with no trace that it was
        #     ever raised.
        #
        # A fresh session commits on its own and fails on its own, so neither
        # can reach the other. Proven by test: a caller that rolls back its
        # own work still leaves the notification standing.
        #-----------------------------------------------------
        own_session = SessionLocal()

        try:
            own_session.add(NotificationEvent(
                event_type=event_type,
                # Copied from the catalogue rather than looked up on read, so
                # the event keeps the classification it was raised under even
                # if the catalogue is later re-tuned.
                severity=entry["severity"],
                tier=entry["tier"],
                module=entry["module"],
                title=render(entry["title_template"], payload, event_type),
                body=render(entry["body_template"], payload, event_type),
                entity_type=entity_type,
                entity_id=entity_id,
                branch=branch,
                payload=payload,
                dedupe_key=dedupe_key,
            ))
            own_session.commit()

        except IntegrityError:
            # The dedupe key is already present, so this same real-world event
            # has been recorded. Nothing to do, and nothing went wrong.
            own_session.rollback()
            logger.debug(
                "Notification %r deduped on key %r", event_type, dedupe_key
            )

        finally:
            own_session.close()

    except Exception:
        # The entire point: a side effect does not get to break its caller.
        logger.exception(
            "Notification %r could not be emitted — swallowed so the caller "
            "is unaffected", event_type,
        )

    return None
