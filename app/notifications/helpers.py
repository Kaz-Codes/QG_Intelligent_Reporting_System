from app.auth.authenticate_user import authenticate
from app.auth.authorize_user import _load_active_user

#-----------------------------------------------------
# WHO IS ASKING
#
#
# THESE ROUTES AUTHENTICATE BUT DO NOT AUTHORIZE. THAT IS DELIBERATE.
# DO NOT "ADD THE MISSING PERMISSION CHECK" — IT WOULD BREAK THE FEATURE.
#
# Every other module's routes call authorize(user, CAN_VIEW_X, db), because
# they read operational tables directly and the permission is what decides
# whether this caller may see that data. The notification routes read one
# table — the caller's own delivery rows — and those rows were ALREADY
# filtered by permission when they were created.
#
# app/notifications/routing.py::user_receives applies the tier gate, the
# admin_only gate and the module permission gate at fan-out time. A user who
# does not hold CAN_VIEW_IMPORTS never gets a delivery row for an imports
# event, so there is nothing about imports in their feed to gate. The
# permission boundary is the EXISTENCE of the row, not a check on read.
#
# Adding a per-module check here would not tighten anything — it would break
# the panel instead. A single feed mixes imports, logistics, trucking and
# inventory events, so gating the whole route on any one permission would
# make an inventory-only user unable to load their own inventory
# notifications. Gating per row would just re-run, on every page load, the
# decision fan-out already made and stored.
#
# What DOES have to be enforced here is identity: every query is scoped to
# `user_id == the caller`, and the single-row read route re-checks ownership
# rather than trusting the id in the path. Those are the checks that matter.
#
#
# The caller is loaded fresh (rather than trusted from the token, which
# carries only an id) so a deactivated account cannot keep reading its feed
# on a token issued before it was disabled. That is the same _load_active_user
# every authorize() call uses — imported rather than re-implemented, so
# "active" cannot come to mean two different things.
#-----------------------------------------------------


def current_user(request, db):
    """The authenticated, still-active caller. 401/403 otherwise."""
    return _load_active_user(authenticate(request), db)
