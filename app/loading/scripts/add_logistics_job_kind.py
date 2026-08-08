"""
One-off migration: add logistics_consignments.job_kind.

Customer-rework service jobs need the same shape as an export/local order
(items, packing, shipping, expenditures, status, Send to Trucking), so they
live in the SAME table with this column as the discriminator rather than
getting a table of their own. The Orders tab lists 'standard', the Service
Jobs tab lists 'rework'.

Every existing row is a standard order — the workbooks only ever describe
export/local work, and rework jobs can only be created through the app — so
the backfill is simply the default.

Needed because `create_all()` only ever creates MISSING tables; it never adds
a column to one that already exists (see CLAUDE.md).

Idempotent — safe to re-run.

Run with: python -m app.loading.scripts.add_logistics_job_kind
"""

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.enums import JobKind
from sqlalchemy import text

DEFAULT = JobKind.STANDARD.value


def run():
    db = SessionLocal()
    try:
        exists = db.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'logistics_consignments' AND column_name = 'job_kind'
        """)).fetchone()

        if exists:
            print("logistics_consignments.job_kind already exists — skipping DDL")
        else:
            db.execute(text(
                f"ALTER TABLE logistics_consignments "
                f"ADD COLUMN job_kind VARCHAR(20) NOT NULL DEFAULT '{DEFAULT}'"
            ))
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_logistics_consignments_job_kind "
                "ON logistics_consignments (job_kind)"
            ))
            db.commit()
            print(f"added logistics_consignments.job_kind "
                  f"(VARCHAR(20) NOT NULL DEFAULT '{DEFAULT}') + index")

        # Anything NULL (only possible if the column pre-existed without the
        # default) becomes a standard order.
        res = db.execute(text(
            "UPDATE logistics_consignments SET job_kind = :d WHERE job_kind IS NULL"
        ), {"d": DEFAULT})
        db.commit()
        if res.rowcount:
            print(f"backfilled {res.rowcount} NULL row(s) to {DEFAULT!r}")

        print("\ndistribution:")
        for kind, n in db.execute(text(
            "SELECT job_kind, count(*) FROM logistics_consignments "
            "WHERE is_deleted = false GROUP BY 1 ORDER BY 2 DESC"
        )).fetchall():
            print(f"   {kind:<10} {n}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
