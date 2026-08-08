"""
One-off migration: add consignments.sent_to_logistics_at / sent_to_trucking_at.

These record the cross-module hand-off — when a consignment was handed to
Logistics (shipping + clearing) and to Trucking (inland movement). NULL means
"not sent", which is correct for every existing row: nothing has ever been
sent, because until now the hand-off lived only in the browser (a module-level
object in the front end, lost on refresh).

They are the record of INTENT. The trucking inbox
(cross_module.derive_open_requests) now reads sent_to_trucking_at instead of
inferring from `incoterm == 'FOB'` — being bought FOB only makes a consignment
ELIGIBLE to be sent, it does not mean anyone has decided to send it.

Needed because `create_all()` only ever creates MISSING tables; it never adds
columns to one that already exists (see CLAUDE.md).

Idempotent — safe to re-run.

Run with: python -m app.loading.scripts.add_consignment_sent_columns
"""

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from sqlalchemy import text

COLUMNS = ["sent_to_logistics_at", "sent_to_trucking_at"]


def run():
    db = SessionLocal()
    try:
        for column in COLUMNS:
            exists = db.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'consignments' AND column_name = :c
            """), {"c": column}).fetchone()

            if exists:
                print(f"consignments.{column} already exists — skipping")
                continue

            db.execute(text(
                f"ALTER TABLE consignments ADD COLUMN {column} TIMESTAMPTZ"
            ))
            db.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_consignments_{column} "
                f"ON consignments ({column})"
            ))
            db.commit()
            print(f"added consignments.{column} (TIMESTAMPTZ NULL) + index")

        print("\ncurrent hand-off state:")
        row = db.execute(text("""
            SELECT count(*) FILTER (WHERE sent_to_logistics_at IS NOT NULL),
                   count(*) FILTER (WHERE sent_to_trucking_at IS NOT NULL),
                   count(*) FILTER (WHERE incoterm = 'FOB'),
                   count(*)
            FROM consignments WHERE is_deleted = false
        """)).fetchone()
        print(f"   sent to logistics : {row[0]}")
        print(f"   sent to trucking  : {row[1]}")
        print(f"   FOB (eligible)    : {row[2]}")
        print(f"   total             : {row[3]}")
        print("\nNote: the trucking inbox now reads sent_to_trucking_at, so it is")
        print("empty until someone actually sends a consignment — by design.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
