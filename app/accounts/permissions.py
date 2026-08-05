"""
The permission catalogue — the single source of truth for what a non-admin
account can be granted.

The system has no roles any more. A user is either an **admin** (the `is_admin`
flag, which passes every check) or a normal account holding an explicit set of
these permissions, assigned at account-creation time. `authorize()` checks the
caller against one (or any-of several) of these names.

Names are used verbatim as the `Permission.name` values seeded at startup and as
the strings the frontend sends when creating/editing an account, so they must
match on both sides. Reference the constants (not raw strings) in routes so a
typo is a loud NameError, not a silent 403.
"""

# --- imports consignments ---
CAN_VIEW_IMPORTS = "can_view_imports_consignments"
CAN_ADD_IMPORTS = "can_add_imports_consignments"
CAN_EDIT_IMPORTS = "can_edit_imports_consignments"
CAN_DELETE_IMPORTS = "can_delete_imports_consignments"

# --- logistics consignments ---
CAN_VIEW_LOGISTICS = "can_view_logistics_consignments"
CAN_ADD_LOGISTICS = "can_add_logistics_consignments"
CAN_EDIT_LOGISTICS = "can_edit_logistics_consignments"
CAN_DELETE_LOGISTICS = "can_delete_logistics_consignments"

# --- trucking consignments ---
CAN_VIEW_TRUCKING = "can_view_trucking_consignments"
CAN_ADD_TRUCKING = "can_add_trucking_consignments"
CAN_EDIT_TRUCKING = "can_edit_trucking_consignments"
CAN_DELETE_TRUCKING = "can_delete_trucking_consignments"

# --- dashboards (view-only) ---
CAN_VIEW_OVERVIEW_DASHBOARD = "can_view_overview_dashboard"
CAN_VIEW_IMPORTS_DASHBOARD = "can_view_imports_dashboard"
CAN_VIEW_LOGISTICS_DASHBOARD = "can_view_logistics_dashboard"
CAN_VIEW_PURCHASES_DASHBOARD = "can_view_purchases_dashboard"
CAN_VIEW_INVENTORY_DASHBOARD = "can_view_inventory_dashboard"

# --- masters ---
CAN_VIEW_MASTER = "can_view_master"
CAN_ADD_MASTER = "can_add_master"
CAN_EDIT_MASTER = "can_edit_master"

# --- misc features ---
CAN_USE_ASSISTANT = "can_use_assistant"
CAN_MAKE_REPORTS = "can_make_reports"


# The full list, in a stable order, seeded at startup. Adding a permission is a
# one-line change here plus wherever it is enforced.
ALL_PERMISSIONS = [
    CAN_VIEW_IMPORTS, CAN_ADD_IMPORTS, CAN_EDIT_IMPORTS, CAN_DELETE_IMPORTS,
    CAN_VIEW_LOGISTICS, CAN_ADD_LOGISTICS, CAN_EDIT_LOGISTICS, CAN_DELETE_LOGISTICS,
    CAN_VIEW_TRUCKING, CAN_ADD_TRUCKING, CAN_EDIT_TRUCKING, CAN_DELETE_TRUCKING,
    CAN_VIEW_OVERVIEW_DASHBOARD, CAN_VIEW_IMPORTS_DASHBOARD, CAN_VIEW_LOGISTICS_DASHBOARD,
    CAN_VIEW_PURCHASES_DASHBOARD, CAN_VIEW_INVENTORY_DASHBOARD,
    CAN_VIEW_MASTER, CAN_ADD_MASTER, CAN_EDIT_MASTER,
    CAN_USE_ASSISTANT, CAN_MAKE_REPORTS,
]

ALL_PERMISSIONS_SET = frozenset(ALL_PERMISSIONS)
