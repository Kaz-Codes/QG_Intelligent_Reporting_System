"""
One-off migration: add `stock.rank` and backfill it from the AB Items workbook.

Needed because `create_all()` only ever creates MISSING tables — it never adds a
column to a table that already exists, so a schema change like this has to be
applied by hand (see CLAUDE.md). A full `load_all` would also do it, but that is
destructive: it drops and reloads every transaction table, including anything
entered through the app. This touches only the new column.

The rank map is imported from the stock loader rather than restated here, so the
migration and the loader can never drift apart.

Idempotent — safe to re-run.

Run with: python -m app.loading.scripts.add_stock_rank
"""

import app.accounts.models
import app.masters.models
import app.imports.models
import app.logistics.models
import app.trucking.models
import app.loading.schemas.stores_schemas

from app.database import SessionLocal
from app.enums import ItemRank
from app.loading.scripts.stores.load_05_stock import build_rank_map
from sqlalchemy import text

DEFAULT = ItemRank.C.value


def run():
    db = SessionLocal()
    try:
        # 1. Add the column if it isn't there yet.
        exists = db.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'stock' AND column_name = 'rank'
        """)).fetchone()

        if exists:
            print("stock.rank already exists — skipping DDL")
        else:
            db.execute(text(
                f"ALTER TABLE stock ADD COLUMN rank VARCHAR(1) NOT NULL DEFAULT '{DEFAULT}'"
            ))
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_stock_rank ON stock (rank)"))
            db.commit()
            print(f"added stock.rank (VARCHAR(1) NOT NULL DEFAULT '{DEFAULT}') + index")

        # 2. Backfill. Reset to the default first so a re-run can't leave a
        #    stale A/B on a row the workbook no longer ranks.
        db.execute(text("UPDATE stock SET rank = :d"), {"d": DEFAULT})

        rank_map = build_rank_map()
        print(f"\nAB entries read: {len(rank_map)}")

        updated = 0
        for (code, branch), rank in rank_map.items():
            res = db.execute(
                text("UPDATE stock SET rank = :r WHERE item_code = :c AND branch = :b"),
                {"r": rank, "c": code, "b": branch},
            )
            updated += res.rowcount

        db.commit()
        print(f"stock rows set to A/B: {updated}")

        # 3. Report the resulting spread.
        print("\nresulting distribution:")
        for rank, n in db.execute(text(
            "SELECT rank, count(*) FROM stock GROUP BY rank ORDER BY rank"
        )).fetchall():
            print(f"   {rank}  {n:>6}")

        unmatched = [k for k in rank_map if not db.execute(
            text("SELECT 1 FROM stock WHERE item_code = :c AND branch = :b LIMIT 1"),
            {"c": k[0], "b": k[1]},
        ).fetchone()]
        if unmatched:
            print(f"\n{len(unmatched)} AB entries have no stock row at that branch "
                  f"(nothing to rank); e.g. {unmatched[:3]}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
