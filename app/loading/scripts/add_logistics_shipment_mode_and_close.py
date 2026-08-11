"""
One-off migration for the logistics orders section:

  1. ADD logistics_consignments.shipment_mode (EFS / Regular). Left NULL for
     every existing row on purpose — the loaded workbooks have no such column,
     and defaulting historical orders to "Regular" would make an unrecorded
     value look recorded.

  2. BACKFILL record_state / is_locked so "Delivered" orders read as finished
     work. helpers.is_closed is now "Delivered AND submitted" (matching
     imports), and the loader writes those flags itself from now on — but rows
     already in the table came in as unlocked drafts, so 111 delivered orders
     would otherwise show Submitted="Draft" and Closed="—".

Needed because `create_all()` only ever creates MISSING tables — it never adds
a column to one that already exists (see CLAUDE.md). A full `load_all` would
also do it, but that is destructive: it drops and reloads every transaction
table, including anything entered through the app.

The flag map is imported from the logistics loader rather than restated here,
so migration and loader cannot drift apart.

Idempotent — safe to re-run.

Run with: python -m app.loading.scripts.add_logistics_shipment_mode_and_close
"""

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.loading.scripts.logistics.load_01_logistics import TERMINAL_FLAGS
from sqlalchemy import text


def run():
    db = SessionLocal()
    try:
        # ---- 1. shipment_mode ----
        exists = db.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'logistics_consignments' AND column_name = 'shipment_mode'
        """)).fetchone()

        if exists:
            print("logistics_consignments.shipment_mode already exists — skipping DDL")
        else:
            db.execute(text(
                "ALTER TABLE logistics_consignments ADD COLUMN shipment_mode VARCHAR(20)"
            ))
            db.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_logistics_consignments_shipment_mode "
                "ON logistics_consignments (shipment_mode)"
            ))
            db.commit()
            print("added logistics_consignments.shipment_mode (VARCHAR(20) NULL) + index")

        # ---- 2. terminal-status flags ----
        print("\nbefore:")
        _report(db)

        total = 0
        for status, (record_state, is_locked) in TERMINAL_FLAGS.items():
            res = db.execute(
                text("""
                    UPDATE logistics_consignments
                    SET record_state = :rs, is_locked = :lk
                    WHERE is_deleted = false
                      AND current_status = :st
                      AND (record_state <> :rs OR is_locked <> :lk)
                """),
                {"rs": record_state, "lk": is_locked, "st": status},
            )
            total += res.rowcount
            print(f"\n{status!r} -> record_state={record_state!r}, is_locked={is_locked}: "
                  f"{res.rowcount} row(s) updated")

        db.commit()
        print(f"\ntotal rows updated: {total}")

        print("\nafter:")
        _report(db)
    finally:
        db.close()


def _report(db):
    for rs, lk, n in db.execute(text("""
        SELECT record_state, is_locked, count(*) FROM logistics_consignments
        WHERE is_deleted = false GROUP BY 1, 2 ORDER BY 3 DESC
    """)).fetchall():
        print(f"   record_state={rs:<10} is_locked={str(lk):<5} {n}")


if __name__ == "__main__":
    run()
