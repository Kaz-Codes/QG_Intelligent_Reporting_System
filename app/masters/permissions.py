#-----------------------------------------------------
# WHO CAN DO WHAT IN THE MASTERS MODULE
#
# The role gate itself is the same one the imports module
# uses, so it is reused rather than written a second time.
# That keeps every role name spelled in exactly one place.
# Only the lists of which role may do which thing are
# masters specific, and they all live here.
#
# admin           everything
# manager         create, edit, deactivate, reactivate and
#                 verify records in the review queue
# entry operator  view, and create a Supplier, Item, Port
#                 or Clearing Agent inline during data entry
#                 (it lands unverified and waits for review)
# viewer          view only
#
# Branch and Works are never created inline. They are our
# own entities and have to be set up deliberately through
# Masters, not typed into existence mid consignment.
#-----------------------------------------------------

from app.imports.permissions import (
    ADMIN, ENTRY_OPERATOR, MANAGER, VIEWER, allow,
)

# Re-exported so the routes import everything to do with
# masters permissions from one module.
__all__ = [
    "ADMIN", "MANAGER", "ENTRY_OPERATOR", "VIEWER", "allow",
    "CAN_VIEW", "CAN_MANAGE", "CAN_INLINE_CREATE",
]


CAN_VIEW = [ADMIN, MANAGER, ENTRY_OPERATOR, VIEWER]
CAN_MANAGE = [ADMIN, MANAGER]
CAN_INLINE_CREATE = [ADMIN, MANAGER, ENTRY_OPERATOR]
