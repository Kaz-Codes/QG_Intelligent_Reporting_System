"""
One-off migration: add consignment_items.net_weight / gross_weight / length /
width / height.

These are the FOB hand-off figures the truck load-out and freight rate depend
on (see ConsignmentItem in app/imports/models.py) — all nullable, so existing
rows simply have no value until entered.

Needed because `create_all()` only ever creates MISSING tables; it never adds
columns to one that already exists (see CLAUDE.md).

Idempotent — safe to re-run.

Run with: python -m app.loading.scripts.add_consignment_item_dimensions
"""

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from sqlalchemy import text

COLUMNS = {
    "net_weight": "NUMERIC(14,3)",
    "gross_weight": "NUMERIC(14,3)",
    "length": "NUMERIC(10,2)",
    "width": "NUMERIC(10,2)",
    "height": "NUMERIC(10,2)",
}


def run():
    db = SessionLocal()
    try:
        for column, coltype in COLUMNS.items():
            exists = db.execute(text("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'consignment_items' AND column_name = :c
            """), {"c": column}).fetchone()

            if exists:
                print(f"consignment_items.{column} already exists — skipping")
                continue

            db.execute(text(
                f"ALTER TABLE consignment_items ADD COLUMN {column} {coltype}"
            ))
            db.commit()
            print(f"added consignment_items.{column} ({coltype} NULL)")
    finally:
        db.close()


if __name__ == "__main__":
    run()
