"""
Retire the `can_delete_*` permissions from a database that already has them.

WHY THEY ARE GONE

    Deleting a record, and undoing that delete, are now ADMIN-ONLY
    (`require_admin`, the same gate reopen uses). Before this, both needed
    `can_delete_{imports,logistics,trucking}` plus entry-ownership, so a
    data-entry user could remove their own records.

    That left three permissions that grant nothing. A permission that grants
    nothing is worse than no permission at all: the account form showed a
    "Delete" checkbox, and an admin ticking it would reasonably believe they
    had given somebody a right they had not.

    So the constants are gone from `app/accounts/permissions.ALL_PERMISSIONS`
    and from the front end's picker. Startup seeding will no longer create
    them — but seeding only ADDS, so rows already in the database survive on
    their own. This removes those, and the user links that point at them.

WHAT IT DOES NOT TOUCH

    Nothing else. It deletes exactly the three permission rows and the
    `user_permissions` links referencing them; every other permission and
    assignment is left alone.

USAGE
    python -m app.loading.scripts.retire_delete_permissions
    python -m app.loading.scripts.retire_delete_permissions --check
"""

import sys

import app.accounts.models          # noqa: F401
import app.masters.models           # noqa: F401
import app.imports.models           # noqa: F401
import app.logistics.models         # noqa: F401
import app.trucking.models          # noqa: F401
import app.loading.schemas.stores_schemas  # noqa: F401

from sqlalchemy import text

from app.database import SessionLocal

RETIRED = (
    "can_delete_imports_consignments",
    "can_delete_logistics_consignments",
    "can_delete_trucking_consignments",
)


def main():
    check_only = "--check" in sys.argv
    db = SessionLocal()

    try:
        rows = db.execute(text("""
            SELECT p.id, p.name, count(up.user_id) AS holders
            FROM permissions p
            LEFT JOIN user_permissions up ON up.permission_id = p.id
            WHERE p.name = ANY(:names)
            GROUP BY p.id, p.name
            ORDER BY p.name
        """), {"names": list(RETIRED)}).all()

        if not rows:
            print("Nothing to do — the retired permissions are not in this database.")
            return

        print("retired permissions still present:")
        for _pid, name, holders in rows:
            print(f"   {name:<40} held by {holders} user(s)")

        if check_only:
            print("\n--check given, nothing was changed.")
            return

        links = db.execute(text("""
            DELETE FROM user_permissions
            WHERE permission_id IN (SELECT id FROM permissions WHERE name = ANY(:names))
        """), {"names": list(RETIRED)}).rowcount

        removed = db.execute(text(
            "DELETE FROM permissions WHERE name = ANY(:names)"
        ), {"names": list(RETIRED)}).rowcount

        db.commit()

        print(f"\nremoved {links} user link(s) and {removed} permission row(s)")

        left = db.execute(text(
            "SELECT count(*) FROM permissions WHERE name = ANY(:names)"
        ), {"names": list(RETIRED)}).scalar()
        print(f"remaining retired rows: {left}")
        print(f"permissions now in the catalogue: "
              f"{db.execute(text('SELECT count(*) FROM permissions')).scalar()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
