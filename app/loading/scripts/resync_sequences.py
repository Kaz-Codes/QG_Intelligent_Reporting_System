"""Re-sync every id sequence with the data already in its table.

WHY THIS EXISTS
    The loaders insert with explicit ids through raw psycopg2, which does not
    advance the table's id sequence. Any table whose loader forgot to bump it
    afterwards will hand out an id that is already taken the first time the APP
    inserts a row — a primary-key violation that surfaces as a bare
    "Internal server error" with nothing on screen to explain it.

    That is what made "Add Supplier", "Add Branch" and "Add Clearing Agent" on
    the Masters screen fail while "Add Port" and "Add Works" worked: ports and
    every other loaded table bumped their sequence, those three did not.

    The loaders now bump their own sequences (etl_common.bump_sequence), so a
    fresh `load_all` is correct on its own. This script repairs a database that
    was loaded BEFORE that fix, without forcing a destructive reload.

USAGE
    python -m app.loading.scripts.resync_sequences          # report + repair
    python -m app.loading.scripts.resync_sequences --check  # report only

Safe to run at any time: it only ever moves a sequence FORWARD to max(id), and
tables that are already correct are left untouched.
"""

import sys

from sqlalchemy import text

# Importing the model modules registers every table on Base.metadata, which is
# what tells us which tables to inspect.
import app.accounts.models          # noqa: F401
import app.masters.models           # noqa: F401
import app.imports.models           # noqa: F401
import app.logistics.models         # noqa: F401
import app.trucking.models          # noqa: F401
import app.logs.models              # noqa: F401
import app.reports.models           # noqa: F401
import app.loading.schemas.stores_schemas  # noqa: F401

from app.database import Base, SessionLocal


def sequence_state(db, table):
    """(sequence name, max id, next id to be issued) — or None if no sequence.

    Join tables (user_permissions) and any table without an integer `id` have
    no sequence, so they are skipped rather than treated as broken.
    """
    sequence = db.execute(
        text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}
    ).scalar()

    if not sequence:
        return None

    max_id = db.execute(text(f'SELECT COALESCE(MAX(id), 0) FROM "{table}"')).scalar()
    last_value, is_called = db.execute(
        text(f"SELECT last_value, is_called FROM {sequence}")
    ).one()

    # A sequence that has never been used reports is_called = false, meaning
    # last_value itself is still up for grabs.
    next_id = last_value + 1 if is_called else last_value

    return sequence, max_id, next_id


def main():
    check_only = "--check" in sys.argv
    db = SessionLocal()

    try:
        broken = []
        skipped = 0

        print(f"{'table':<34} {'max(id)':>9} {'next id':>9}   state")
        print("-" * 72)

        for table in sorted(Base.metadata.tables):
            try:
                state = sequence_state(db, table)
            except Exception:
                # A table in the metadata but not in the database yet.
                db.rollback()
                continue

            if state is None:
                skipped += 1
                continue

            _sequence, max_id, next_id = state
            ok = next_id > max_id

            if not ok:
                broken.append((table, max_id, next_id))

            # Only the interesting rows: anything broken, plus anything that
            # actually holds data. Empty, correct tables are just noise.
            if max_id or not ok:
                print(f"{table:<34} {max_id:>9} {next_id:>9}   "
                      f"{'ok' if ok else 'COLLIDES'}")

        print("-" * 72)
        print(f"{skipped} table(s) have no id sequence (join tables) — skipped")

        if not broken:
            print("\nEvery sequence is ahead of its data. Nothing to do.")
            return

        print(f"\n{len(broken)} table(s) would fail on the next app-side INSERT:")
        for table, max_id, next_id in broken:
            print(f"   {table:<32} would issue {next_id}, but {max_id} is taken")

        if check_only:
            print("\n--check given, so nothing was changed.")
            return

        for table, _max_id, _next_id in broken:
            db.execute(text(
                f"SELECT setval('{table}_id_seq', "
                f"(SELECT COALESCE(MAX(id), 1) FROM \"{table}\"))"
            ))

        db.commit()
        print(f"\nRepaired {len(broken)} sequence(s).")

        for table, _max_id, _next_id in broken:
            _sequence, max_id, next_id = sequence_state(db, table)
            print(f"   {table:<32} now issues {next_id} (max id {max_id})")

    except Exception as e:
        db.rollback()
        print("failed:", e)
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
