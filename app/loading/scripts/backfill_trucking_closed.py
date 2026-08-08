"""
Mark loaded trucking jobs whose trucks have all arrived as finished work.

`helpers.is_closed` is "every active vehicle Delivered AND submitted" (the same
two-part rule as imports and logistics). Jobs loaded from the workbooks came in
as unlocked drafts regardless, so a job whose every truck reads "Delivered"
would show Submitted="Draft" and Closed="—" — a contradiction.

This has to run AFTER the vehicles are inserted, which is why it is a separate
pass rather than a column the trucking loader writes inline: a job's closed
state is a property of its vehicles, and at consignment-insert time they do not
exist yet. `load_03_trucking` calls `mark_closed_jobs(conn)` at the end for
exactly that reason.

Idempotent — safe to re-run.

Run standalone with:
    python -m app.loading.scripts.backfill_trucking_closed
"""

SQL = """
UPDATE trucking_consignments c
SET record_state = 'submitted', is_locked = true
WHERE c.is_deleted = false
  AND (c.record_state <> 'submitted' OR c.is_locked <> true)
  -- has at least one live vehicle ...
  AND EXISTS (
        SELECT 1 FROM trucking_vehicles v
        WHERE v.consignment_id = c.id AND v.is_deleted = false
  )
  -- ... and not one of them is anything other than Delivered
  AND NOT EXISTS (
        SELECT 1 FROM trucking_vehicles v
        WHERE v.consignment_id = c.id AND v.is_deleted = false
          AND v.tracking_status IS DISTINCT FROM 'Delivered'
  )
"""


def mark_closed_jobs(conn):
    """Raw-psycopg2 form, for the loader (which owns its own connection)."""
    with conn.cursor() as cur:
        cur.execute(SQL)
        count = cur.rowcount
    conn.commit()
    print(f"  trucking: {count} job(s) with all vehicles delivered -> submitted + closed")
    return count


def run():
    import app.accounts.models
    import app.masters.models
    import app.imports.models
    import app.logistics.models
    import app.trucking.models
    import app.loading.schemas.stores_schemas

    from app.database import SessionLocal
    from sqlalchemy import text

    db = SessionLocal()
    try:
        print("before:")
        _report(db, text)

        res = db.execute(text(SQL))
        db.commit()
        print(f"\nupdated {res.rowcount} job(s)")

        print("\nafter:")
        _report(db, text)
    finally:
        db.close()


def _report(db, text):
    for rs, lk, n in db.execute(text(
        "SELECT record_state, is_locked, count(*) FROM trucking_consignments "
        "WHERE is_deleted = false GROUP BY 1, 2 ORDER BY 3 DESC"
    )).fetchall():
        print(f"   record_state={rs:<10} is_locked={str(lk):<5} {n}")


if __name__ == "__main__":
    run()
