"""
Repair the draft/closed flags on already-loaded consignments.

The imports loader now sets record_state/is_locked itself (see
load_05_consignments.terminal_flags): a sheet row that already carries a
terminal status describes finished work, so it loads as submitted, and
"Arrived at works" additionally loads closed. Data loaded before that change
came in as record_state='draft', is_locked=false regardless of status — which
puts rows in the Closed stage whose Submitted column reads "Draft".

This applies the same rule to whatever is already in the table, so the fix
does not require a destructive full reload.

Idempotent: rows already carrying the right flags are not touched.

Run with: python -m app.loading.scripts.backfill_closed_submitted
"""

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models

from app.database import SessionLocal
from app.imports.models import Consignment
from app.loading.scripts.imports.load_05_consignments import TERMINAL_STATUSES


def run():
    db = SessionLocal()
    try:
        updated = 0

        for status, (record_state, is_locked) in TERMINAL_STATUSES.items():
            rows = db.query(Consignment).filter(
                Consignment.current_status == status,
            ).all()

            for consignment in rows:
                if (consignment.record_state, consignment.is_locked) == (record_state, is_locked):
                    continue
                consignment.record_state = record_state
                consignment.is_locked = is_locked
                updated += 1

            print(f"  {status}: {len(rows)} row(s) at this status "
                  f"-> record_state={record_state!r}, is_locked={is_locked}")

        db.commit()
        print(f"Updated {updated} consignment(s).")
    finally:
        db.close()


if __name__ == "__main__":
    run()
