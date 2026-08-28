from app.accounts.permissions import (
    CAN_VIEW_IMPORTS, CAN_VIEW_INVENTORY_DASHBOARD, CAN_VIEW_LOGISTICS,
    CAN_VIEW_TRUCKING,
)
from app.enums import (
    NotificationModule as M,
    NotificationSeverity as S,
    NotificationTier as T,
)

#-----------------------------------------------------
# THE EVENT CATALOGUE
#
# Every notification this system can raise, in one dict. An event type that is
# not here cannot be emitted — emit() refuses an unknown key rather than
# inventing a classification for it, so the set of things that can interrupt
# somebody stays reviewable in one place.
#
# Each entry carries:
#   severity        how loud   (NotificationSeverity)
#   tier            who it is pitched at (NotificationTier) — routing.py owns
#                   how this compares against the recipient's own tier
#   module          which screen it belongs to (NotificationModule)
#   permission      the constant from app.accounts.permissions that a
#                   recipient must hold, or None if the event is not gated on
#                   one. NEVER a raw string — a typo in a permission name
#                   fails open, silently widening the audience.
#   admin_only      only is_admin users receive it, whatever their tier
#   title_template  short, one line
#   body_template   the full message
#
# Templates are str.format placeholders filled from the emitted payload.
#
# ONLY BUSINESS EVENTS BELONG HERE. Generic create/update/delete is already
# recorded, for every table, by app/logs/ — that is the audit trail. These are
# the handful of things somebody is expected to ACT on. If a proposed event
# would fire on ordinary data entry, it belongs in the activity log, not here.
#
#
# ITEM NAMES ARE NOT UNIQUE — SPECIFICATION IS MANDATORY
# ------------------------------------------------------
# The item master holds the same NAME against several specifications; "servo
# drive" alone matches four different codes. A notification that names an item
# without its specification is therefore ambiguous, and acting on the wrong
# one means moving, ordering or writing off the wrong part.
#
# So: EVERY event whose message names an item MUST render its specification
# alongside the name, in BOTH title and body. This is a correctness rule, not
# presentation — do not add an inventory event that omits it.
#
# The same applies to BRANCH on anything stock-related. ABC rank is held per
# item PER BRANCH (see enums.ItemRank), so "critical item" means rank A or B
# AT THE BRANCH THE EVENT CONCERNS. Rank is never folded across branches.
#-----------------------------------------------------

EVENT_CATALOGUE = {

    #--------------------------------
    # IMPORTS
    #--------------------------------

    "imports.eta_slipped_major": {
        "severity": S.CRITICAL.value,
        "tier": T.EXECUTIVE.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        # Variables match the payload the emitter sends exactly — see
        # imports/routes/update_consignment.py. Renaming one without the
        # other renders the placeholder literally in the message.
        "title_template": "ETA slipped {slip_days}d — {consignment_no}",
        "body_template": (
            "{consignment_no} from {supplier} has moved its ETA from "
            "{old_eta} to {new_eta} — {slip_days} days later."
        ),
    },

    "imports.demurrage_risk": {
        "severity": S.CRITICAL.value,
        "tier": T.EXECUTIVE.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "Demurrage risk — {reference}",
        "body_template": (
            "{reference} has {free_days_left} free day(s) left at {port}. "
            "Landed {arrived_on}; demurrage begins {demurrage_starts} if it "
            "is not cleared."
        ),
    },

    "imports.clearance_aging": {
        "severity": S.IMPORTANT.value,
        "tier": T.MANAGERIAL.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "In clearance {days_in_clearance}d — {reference}",
        "body_template": (
            "{reference} has sat at \"{status}\" for {days_in_clearance} days "
            "at {port}, handled by {clearing_agent}."
        ),
    },

    "imports.payment_overdue": {
        "severity": S.IMPORTANT.value,
        "tier": T.EXECUTIVE.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "Payment {days_overdue}d overdue — {reference}",
        "body_template": (
            "{instrument} {instrument_number} against {reference} "
            "({supplier}) was due {due_date} and is {days_overdue} days "
            "overdue."
        ),
    },

    #--------------------------------
    # LOGISTICS
    #--------------------------------

    "logistics.rfd_missed": {
        "severity": S.IMPORTANT.value,
        "tier": T.EXECUTIVE.value,
        "module": M.LOGISTICS.value,
        "permission": CAN_VIEW_LOGISTICS,
        "admin_only": False,
        "title_template": "RFD missed by {days_late}d — {mo_no}",
        "body_template": (
            "{item_detail} on order {mo_no} for {customer} missed its planned "
            "RFD of {planned_rfd} — now {days_late} days late."
        ),
    },

    "logistics.detention_risk": {
        "severity": S.CRITICAL.value,
        "tier": T.EXECUTIVE.value,
        "module": M.LOGISTICS.value,
        "permission": CAN_VIEW_LOGISTICS,
        "admin_only": False,
        "title_template": "Detention risk — container {container_no}",
        "body_template": (
            "Container {container_no} on order {mo_no} for {customer} has "
            "been held {days_held} days. Detention charges begin "
            "{detention_starts}."
        ),
    },

    #--------------------------------
    # TRUCKING
    #--------------------------------

    "trucking.request_aged": {
        "severity": S.IMPORTANT.value,
        "tier": T.MANAGERIAL.value,
        "module": M.TRUCKING.value,
        "permission": CAN_VIEW_TRUCKING,
        "admin_only": False,
        "title_template": "Trucking request open {days_open}d — {source_ref}",
        "body_template": (
            "{label} was handed to Trucking {days_open} days ago and no job "
            "has taken it."
        ),
    },

    #--------------------------------
    # INVENTORY
    #
    # Both of these name an item, so both carry {specification} in the title
    # AND the body, and both state the {branch} — see the header note. Rank is
    # the rank AT THAT BRANCH.
    #--------------------------------

    "inventory.below_reorder": {
        "severity": S.IMPORTANT.value,
        "tier": T.MANAGERIAL.value,
        "module": M.INVENTORY.value,
        "permission": CAN_VIEW_INVENTORY_DASHBOARD,
        "admin_only": False,
        "title_template": "Below reorder — {item_name} ({specification}) at {branch}",
        "body_template": (
            "{item_name} ({specification}) at {branch} — {available} "
            "available, reorder at {reorder_level}. Rank {rank} at this "
            "branch."
        ),
    },

    "inventory.stockout": {
        "severity": S.CRITICAL.value,
        "tier": T.EXECUTIVE.value,
        "module": M.INVENTORY.value,
        "permission": CAN_VIEW_INVENTORY_DASHBOARD,
        "admin_only": False,
        "title_template": "Stockout — {item_name} ({specification}) at {branch}",
        "body_template": (
            "{item_name} ({specification}) is out of stock at {branch} — "
            "nothing available against a reorder level of {reorder_level}. "
            "Rank {rank} at this branch."
        ),
    },

    #--------------------------------
    # SYSTEM
    #--------------------------------

    "system.backup_failed": {
        "severity": S.CRITICAL.value,
        "tier": T.MANAGERIAL.value,
        "module": M.SYSTEM.value,
        # No permission gates this: it is not about anyone's module. It goes
        # to admins and nobody else.
        "permission": None,
        "admin_only": True,
        "title_template": "Backup failed",
        "body_template": (
            "The {backup_kind} backup failed at {failed_at}: {error}"
        ),
    },
}


def get_event(event_type):
    """The catalogue entry, or None if the type is not registered."""
    return EVENT_CATALOGUE.get(event_type)
