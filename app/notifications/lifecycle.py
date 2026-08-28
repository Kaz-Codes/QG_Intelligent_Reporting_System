import logging
from datetime import date

from app.notifications.emit import emit

logger = logging.getLogger(__name__)

#-----------------------------------------------------
# LIFECYCLE NOTIFICATIONS
#
# The four moments in a record's life that are worth telling somebody about:
# it STARTED, it CHANGED STATE, it FINISHED, it VANISHED. Everything else a
# route does — a field edit, a draft save, a re-save that changes nothing — is
# already in app/logs/ and does not belong here.
#
# ONE IMPLEMENTATION FOR THREE MODULES. The catalogue deliberately gives all
# twelve entries the same payload keys, so the only thing that varies between
# imports, logistics and trucking is the event-type prefix and the words in
# the template. Writing this out at twelve call sites is how the dedupe keys
# would end up subtly different from each other.
#
# EVERY FUNCTION HERE IS CALLED AFTER THE CALLER HAS COMMITTED, and every one
# is wrapped so it cannot raise into the caller. emit() already guarantees
# both (its own session, its own try/except); this second layer exists because
# these are called from routes that have already returned their work to the
# user, and a traceback from a notification must not turn a successful save
# into a 500.
#-----------------------------------------------------

# module name -> the entity_type the panel resolves into a link. Kept beside
# the event types rather than in the panel, because the two have to agree and
# this is the end that creates them.
MODULE_ENTITY_TYPE = {
    "imports": "consignment",
    "logistics": "logistics_order",
    "trucking": "trucking_job",
}


def format_money(value):
    """A PKR amount for a notification body, or a plain statement of absence.

    Rendered HERE rather than left to the template, because a Decimal formats
    as "1234567.8900" and a None formats as "None" — and "valued None" in a
    message about a record that has just been deleted reads as a bug in the
    message rather than as a gap in the data. Shared by all three modules so
    the same amount cannot appear three different ways.
    """
    if value is None:
        return "no recorded value"

    try:
        return f"PKR {value:,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _emit(db, module, action, record_id, payload, branch, dedupe_key):
    """Shared tail: build the event type, attach the entity, never raise."""
    try:
        emit(
            db,
            f"{module}.{action}",
            payload=payload,
            entity_type=MODULE_ENTITY_TYPE.get(module),
            entity_id=record_id,
            branch=branch,
            dedupe_key=dedupe_key,
        )
    except Exception:
        logger.exception(
            "Could not raise the %s.%s notification for record %s — swallowed; "
            "the change itself is already committed",
            module, action, record_id,
        )


def notify_created(db, module, record_id, *, reference, party, branch=None):
    """A record was persisted for the FIRST time.

    Called from the create route only, never from update — a wizard saves a
    draft repeatedly and only the first of those is the record starting.

    Dedupe is the bare id: a record is created once, so two of these can only
    mean the same POST arrived twice.
    """
    _emit(
        db, module, "created", record_id,
        payload={"reference": reference, "party": party},
        branch=branch,
        dedupe_key=f"{module}.created:{record_id}",
    )


def notify_status_changed(db, module, record_id, *, reference, old_status,
                          new_status, branch=None):
    """The record moved from one state to another.

    THE CALLER MUST HAVE ESTABLISHED THAT IT ACTUALLY CHANGED. This does not
    fire on a save that merely includes a status field holding the value it
    already had — that is a field edit, not a state change, and it is what
    would turn every draft save into a notification.

    Dedupe carries the transition AND the day, so a double-save of the same
    move is one notification while a genuine A -> B -> A on another day is
    not swallowed.
    """
    _emit(
        db, module, "status_changed", record_id,
        payload={
            "reference": reference,
            "old_status": old_status or "no status",
            "new_status": new_status,
        },
        branch=branch,
        dedupe_key=(
            f"{module}.status_changed:{record_id}:"
            f"{old_status}->{new_status}:{date.today().isoformat()}"
        ),
    )


def notify_completed(db, module, record_id, *, reference, party, status,
                     branch=None):
    """The record reached its module's terminal state.

    SUPPRESSES THE PAIRED status_changed — the caller emits this INSTEAD OF,
    not in addition to, the status-change event. Reaching the terminal state
    is a status change, so firing both would tell one person the same thing
    twice, one line apart, differing only in tone. The completion is the more
    informative of the two, so it is the one that survives.

    Dedupe is the bare id: completing is a once-per-record event. A record
    reopened by an admin and completed again does not notify twice, which is
    the intended reading — it finished, and that was already said.
    """
    _emit(
        db, module, "completed", record_id,
        payload={"reference": reference, "party": party, "status": status},
        branch=branch,
        dedupe_key=f"{module}.completed:{record_id}",
    )


def notify_deleted(db, module, record_id, *, reference, party, value,
                   deleted_by, branch=None):
    """The record was soft-deleted.

    THE PAYLOAD HAS TO STAND ON ITS OWN. Every other lifecycle event points at
    a record the reader can go and open; this one points at a row that has
    just been hidden from every list. So it carries what identifies the thing
    that vanished — reference, counterparty, value and who removed it —
    because a reader who cannot see the record cannot look any of it up.

    Dedupe carries the day rather than being the bare id: delete, undo-delete
    and delete again is a real sequence in this system (both routes exist),
    and the second removal is worth hearing about rather than being swallowed
    for ever by the first one's key.
    """
    _emit(
        db, module, "deleted", record_id,
        payload={
            "reference": reference,
            "party": party,
            "value": value,
            "deleted_by": deleted_by,
        },
        branch=branch,
        dedupe_key=f"{module}.deleted:{record_id}:{date.today().isoformat()}",
    )
