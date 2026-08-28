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
        "grouped_title_template": "{count} consignments at demurrage risk",
        "grouped_body_template": (
            "{count} consignments are within their last free days at port. Raised as one summary because too many crossed at once — open the Imports list to see them."
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
        "grouped_title_template": "{count} consignments aging in clearance",
        "grouped_body_template": (
            "{count} consignments have been in customs clearance longer than the alert threshold. Raised as one summary because too many crossed at once — open the Imports list, filtered to the Clearance stage."
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
        "grouped_title_template": "{count} payments overdue",
        "grouped_body_template": (
            "{count} payments are past their retirement date and still unpaid. Raised as one summary because too many crossed at once."
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
        "grouped_title_template": "{count} RFD dates missed",
        "grouped_body_template": (
            "{count} order lines have passed their planned RFD without being dispatched. Raised as one summary because too many crossed at once."
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
        "grouped_title_template": "{count} containers at detention risk",
        "grouped_body_template": (
            "{count} containers are approaching their detention window. Raised as one summary because too many crossed at once."
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
        "grouped_title_template": "{count} trucking requests unclaimed",
        "grouped_body_template": (
            "{count} handed-over requests have gone unclaimed past the alert threshold. Raised as one summary because too many crossed at once."
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
            "{item_name} ({specification}) at {branch} — {available_qty} "
            "available, reorder at {reorder_level}. Rank {rank} at this "
            "branch."
        ),
        "grouped_title_template": "{count} critical items below reorder level",
        "grouped_body_template": (
            "{count} rank A/B items are at or below their reorder level. Raised as one summary because too many crossed at once — open the Inventory dashboard for the itemised list, where each carries its specification."
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
        "grouped_title_template": "{count} critical items out of stock",
        "grouped_body_template": (
            "{count} rank A/B items that are actually moving have run to zero available. Raised as one summary because too many crossed at once — open the Inventory dashboard for the itemised list, where each carries its specification."
        ),
    },

    #--------------------------------
    # LIFECYCLE — THE HIGH-VOLUME EVENTS, AND WHY GROUPING EXISTS
    #
    # Everything above this line is an EXCEPTION: something went wrong, or is
    # about to. These twelve are the opposite — the ordinary life of a record:
    # it started, it changed state, it finished, it vanished. They fire on
    # normal work going normally.
    #
    # THAT MAKES THEM AN ORDER OF MAGNITUDE MORE FREQUENT. At roughly 5,000
    # consignments a year plus their status changes, this is ~50-150 events a
    # day against the exception catalogue's 30-80 — and unlike the exception
    # events, the number grows with how busy the business is rather than with
    # how much is going wrong.
    #
    # THEY ARE THE REASON DELIVERY GROUPING EXISTS. A user who would receive
    # more than GROUPING_THRESHOLD info-tier notifications from one module in
    # an hour gets them collapsed into a single expandable entry instead —
    # see routing.py::assign_group_key. That mechanism is general, keyed on
    # (user, module, severity); it is not special-cased for these events, it
    # just happens to be these that make it necessary.
    #
    # TIERS ARE THE OTHER HALF OF THE VOLUME ANSWER. `created` and
    # `status_changed` are OPERATIONAL, which in this system means they reach
    # operational users and stop there (routing.py: a user receives an event
    # when user_tier <= event_tier). A director is not pinged because a clerk
    # started a consignment. `deleted` is important/managerial because a
    # record disappearing without explanation is exactly what a supervisor
    # should hear about.
    #
    # NOT EVERY CHANGE IS A LIFECYCLE EVENT. Field edits, draft saves and
    # every other generic create/update/delete stay in app/logs/ where they
    # belong. Only four moments qualify: started, changed state, finished,
    # vanished.
    #
    # Payload keys are deliberately IDENTICAL across the three modules
    # (`reference`, `party`, `old_status`, `new_status`, `status`, `value`,
    # `deleted_by`) so app/notifications/lifecycle.py can build all twelve
    # from one place. Only the wording differs.
    #--------------------------------

    #--- imports lifecycle ---

    "imports.created": {
        "severity": S.INFO.value,
        "tier": T.OPERATIONAL.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "New consignment {reference}",
        "body_template": "{reference} from {party} has been created.",
    },

    "imports.status_changed": {
        "severity": S.INFO.value,
        "tier": T.OPERATIONAL.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "{reference} — {new_status}",
        "body_template": "{reference} moved from {old_status} to {new_status}.",
    },

    "imports.completed": {
        "severity": S.INFO.value,
        "tier": T.MANAGERIAL.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "{reference} completed",
        "body_template": "{reference} from {party} has reached {status}.",
    },

    "imports.deleted": {
        "severity": S.IMPORTANT.value,
        "tier": T.MANAGERIAL.value,
        "module": M.IMPORTS.value,
        "permission": CAN_VIEW_IMPORTS,
        "admin_only": False,
        "title_template": "Consignment {reference} deleted",
        "body_template": (
            "{reference} from {party}, valued {value}, was deleted by "
            "{deleted_by}. It is hidden from the list but not destroyed — an "
            "admin can restore it."
        ),
    },

    #--- logistics lifecycle ---

    "logistics.created": {
        "severity": S.INFO.value,
        "tier": T.OPERATIONAL.value,
        "module": M.LOGISTICS.value,
        "permission": CAN_VIEW_LOGISTICS,
        "admin_only": False,
        "title_template": "New order {reference}",
        "body_template": "{reference} for {party} has been created.",
    },

    "logistics.status_changed": {
        "severity": S.INFO.value,
        "tier": T.OPERATIONAL.value,
        "module": M.LOGISTICS.value,
        "permission": CAN_VIEW_LOGISTICS,
        "admin_only": False,
        "title_template": "{reference} — {new_status}",
        "body_template": "{reference} moved from {old_status} to {new_status}.",
    },

    "logistics.completed": {
        "severity": S.INFO.value,
        "tier": T.MANAGERIAL.value,
        "module": M.LOGISTICS.value,
        "permission": CAN_VIEW_LOGISTICS,
        "admin_only": False,
        "title_template": "{reference} delivered",
        "body_template": "{reference} for {party} has reached {status}.",
    },

    "logistics.deleted": {
        "severity": S.IMPORTANT.value,
        "tier": T.MANAGERIAL.value,
        "module": M.LOGISTICS.value,
        "permission": CAN_VIEW_LOGISTICS,
        "admin_only": False,
        "title_template": "Order {reference} deleted",
        "body_template": (
            "{reference} for {party}, valued {value}, was deleted by "
            "{deleted_by}. It is hidden from the list but not destroyed — an "
            "admin can restore it."
        ),
    },

    #--- trucking lifecycle ---
    #
    # TRUCKING HAS NO STORED JOB-LEVEL STATUS. Tracking is per vehicle, and
    # the job-level reading is a rollup over them — see
    # trucking/helpers.py::job_tracking_status, which mirrors the front end's
    # own trackingRollup (the least-advanced vehicle). So `status_changed`
    # here means that rollup moved, and `completed` means every active
    # vehicle reached Delivered. Both are stated in the wording rather than
    # pretending the job carries a status of its own.

    "trucking.created": {
        "severity": S.INFO.value,
        "tier": T.OPERATIONAL.value,
        "module": M.TRUCKING.value,
        "permission": CAN_VIEW_TRUCKING,
        "admin_only": False,
        "title_template": "New trucking job {reference}",
        "body_template": "{reference} with {party} has been created.",
    },

    "trucking.status_changed": {
        "severity": S.INFO.value,
        "tier": T.OPERATIONAL.value,
        "module": M.TRUCKING.value,
        "permission": CAN_VIEW_TRUCKING,
        "admin_only": False,
        "title_template": "{reference} — {new_status}",
        "body_template": (
            "{reference}: its vehicles have moved from {old_status} to "
            "{new_status}."
        ),
    },

    "trucking.completed": {
        "severity": S.INFO.value,
        "tier": T.MANAGERIAL.value,
        "module": M.TRUCKING.value,
        "permission": CAN_VIEW_TRUCKING,
        "admin_only": False,
        "title_template": "{reference} delivered",
        "body_template": "{reference} with {party}: every vehicle has {status}.",
    },

    "trucking.deleted": {
        "severity": S.IMPORTANT.value,
        "tier": T.MANAGERIAL.value,
        "module": M.TRUCKING.value,
        "permission": CAN_VIEW_TRUCKING,
        "admin_only": False,
        "title_template": "Trucking job {reference} deleted",
        "body_template": (
            "{reference} with {party}, valued {value}, was deleted by "
            "{deleted_by}. It is hidden from the list but not destroyed — an "
            "admin can restore it."
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
