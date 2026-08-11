"""Create the Customer master and link logistics orders to it.

WHAT THIS DOES
    1. Creates the `customers` table (create_all only ever ADDS missing tables,
       so this is safe on a populated database).
    2. Adds `logistics_consignments.customer_id` — create_all cannot add a
       column to an existing table, so that one is a hand-written ALTER.
    3. Seeds one customer per distinct `customer_name` already on the orders.
    4. Backfills `customer_id` by case-insensitive name match.

WHY THE SEEDED ROWS LAND UNVERIFIED
    They are harvested from free text nobody ever validated. The distinct names
    contain obvious duplicates — "CHERAT CEMENT" and "CHERAT CEMENT LTD." are
    one company, "JK SUGAR MILLS (PVT.) LTD. I" and "... II" may or may not be.
    Seeding them verified would assert a cleanliness the data does not have, so
    they go into the Masters review queue instead, where they can be confirmed,
    renamed or deactivated. The report at the end lists the likely duplicates.

USAGE
    python -m app.loading.scripts.add_customer_master
    python -m app.loading.scripts.add_customer_master --check   # report only

Idempotent: re-running adds only names that are missing and re-links only rows
whose customer_id is not already correct.
"""

import sys
from collections import defaultdict

from sqlalchemy import text

import app.accounts.models          # noqa: F401
import app.masters.models           # noqa: F401
import app.imports.models           # noqa: F401
import app.logistics.models         # noqa: F401
import app.trucking.models          # noqa: F401
import app.logs.models              # noqa: F401
import app.reports.models           # noqa: F401
import app.loading.schemas.stores_schemas  # noqa: F401

from app.database import Base, SessionLocal, engine


def ensure_schema(db):
    """Create the customers table and the logistics FK column."""
    Base.metadata.create_all(bind=engine)

    exists = db.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'logistics_consignments' AND column_name = 'customer_id'
    """)).scalar()

    if exists:
        print("  logistics_consignments.customer_id already present")
        return

    db.execute(text("""
        ALTER TABLE logistics_consignments
        ADD COLUMN customer_id INTEGER
        REFERENCES customers(id) ON DELETE SET NULL
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_logistics_consignments_customer_id
        ON logistics_consignments (customer_id)
    """))
    db.commit()
    print("  added logistics_consignments.customer_id (+ index)")


def normalise(name):
    return (name or "").strip()


def main():
    check_only = "--check" in sys.argv
    db = SessionLocal()

    try:
        if not check_only:
            print("schema:")
            ensure_schema(db)
        else:
            has_table = db.execute(text("""
                SELECT 1 FROM information_schema.tables WHERE table_name = 'customers'
            """)).scalar()
            print(f"schema: customers table {'exists' if has_table else 'MISSING'}")
            if not has_table:
                print("\n--check given and the table does not exist yet; "
                      "nothing further to report.")
                return

        # ---- the names currently on orders ----
        rows = db.execute(text("""
            SELECT customer_name, count(*)
            FROM logistics_consignments
            WHERE is_deleted = false AND customer_name IS NOT NULL
              AND btrim(customer_name) <> ''
            GROUP BY customer_name
            ORDER BY count(*) DESC
        """)).all()

        names = {normalise(n): c for n, c in rows if normalise(n)}
        orders_with_name = sum(names.values())

        total_orders = db.execute(text(
            "SELECT count(*) FROM logistics_consignments WHERE is_deleted = false"
        )).scalar()

        print(f"\norders: {total_orders} live, {orders_with_name} carry a customer name")
        print(f"distinct names: {len(names)}")

        existing = {
            normalise(n).lower(): i
            for i, n in db.execute(text("SELECT id, name FROM customers")).all()
        }
        missing = [n for n in names if n.lower() not in existing]
        print(f"customers already in the master: {len(existing)}")
        print(f"to be created: {len(missing)}")

        if check_only:
            print("\n--check given, so nothing was changed.")
            report_duplicates(names)
            return

        # ---- seed ----
        #
        # Deduplicated CASE-INSENSITIVELY. "GREEN FUEL" and "Green Fuel" are one
        # customer by any reading, but customers.name is unique case-SENSITIVELY,
        # so inserting both succeeds and then the case-insensitive lookup in
        # logistics.helpers.resolve_customer_id has two rows to choose from and
        # picks arbitrarily. One row per lowercased name closes that off.
        #
        # The spelling kept is the one the most orders actually use — the house
        # style, rather than whichever happened to sort first.
        canonical = {}
        for name in missing:
            key = name.lower()
            if key not in canonical or names[name] > names[canonical[key]]:
                canonical[key] = name

        collapsed = len(missing) - len(canonical)

        for name in canonical.values():
            db.execute(
                text("""INSERT INTO customers (name, is_active, is_verified)
                        VALUES (:n, true, false)
                        ON CONFLICT (name) DO NOTHING"""),
                {"n": name},
            )
        db.commit()

        if collapsed:
            print(f"  collapsed {collapsed} case-only duplicate name(s) while seeding")

        missing = list(canonical.values())

        # Repair a database seeded by an earlier run that did NOT dedupe.
        merge_case_duplicates(db)

        # Loaded with the ORM's own sequence, so no bump is needed — but stay
        # consistent with every other loader and make sure.
        db.execute(text(
            "SELECT setval('customers_id_seq', (SELECT COALESCE(MAX(id), 1) FROM customers))"
        ))
        db.commit()
        print(f"\ncreated {len(missing)} customer(s), all unverified")

        # ---- backfill the link ----
        linked = db.execute(text("""
            UPDATE logistics_consignments AS l
            SET customer_id = c.id
            FROM customers AS c
            WHERE lower(btrim(l.customer_name)) = lower(c.name)
              AND (l.customer_id IS DISTINCT FROM c.id)
        """)).rowcount
        db.commit()
        print(f"linked {linked} order(s) to a customer")

        # ---- verify ----
        still_null = db.execute(text("""
            SELECT count(*) FROM logistics_consignments
            WHERE is_deleted = false AND customer_id IS NULL
              AND customer_name IS NOT NULL AND btrim(customer_name) <> ''
        """)).scalar()
        total_customers = db.execute(text("SELECT count(*) FROM customers")).scalar()

        print(f"\nresulting state:")
        print(f"   customers            {total_customers}")
        print(f"   orders linked        "
              f"{db.execute(text('SELECT count(*) FROM logistics_consignments WHERE customer_id IS NOT NULL')).scalar()}")
        print(f"   named but unlinked   {still_null}  (should be 0)")

        # Judged against the master as it now stands, not the raw order names.
        master_names = current_customer_names(db)
        set_verification(db, master_names)
        report_duplicates(master_names)

    except Exception as e:
        db.rollback()
        print("failed:", e)
        raise

    finally:
        db.close()


def merge_case_duplicates(db):
    """Collapse customers whose names differ only by capitalisation.

    Safe to do automatically, unlike the suffix duplicates report_duplicates
    lists: "GREEN FUEL" and "Green Fuel" are the same string bar case, whereas
    "CHERAT CEMENT" vs "CHERAT CEMENT LTD." is a business judgement about
    whether those are one company.

    Orders are moved onto the survivor before the extra rows are deleted, so no
    order loses its link. The survivor is the spelling the most orders use.
    """
    groups = db.execute(text("""
        SELECT lower(name) AS key, array_agg(id ORDER BY id) AS ids
        FROM customers
        GROUP BY lower(name)
        HAVING count(*) > 1
    """)).all()

    if not groups:
        return

    merged = 0
    moved = 0

    for _key, ids in groups:
        usage = dict(db.execute(text("""
            SELECT c.id, count(l.id)
            FROM customers c
            LEFT JOIN logistics_consignments l
                   ON l.customer_id = c.id AND l.is_deleted = false
            WHERE c.id = ANY(:ids)
            GROUP BY c.id
        """), {"ids": list(ids)}).all())

        # Most-used spelling wins; lowest id breaks a tie so the choice is
        # deterministic across runs.
        keep = max(ids, key=lambda i: (usage.get(i, 0), -i))
        drop = [i for i in ids if i != keep]

        moved += db.execute(text("""
            UPDATE logistics_consignments
            SET customer_id = :keep
            WHERE customer_id = ANY(:drop)
        """), {"keep": keep, "drop": drop}).rowcount

        db.execute(text("DELETE FROM customers WHERE id = ANY(:drop)"), {"drop": drop})
        merged += len(drop)

    db.commit()
    print(f"  merged {merged} case-only duplicate customer(s); "
          f"moved {moved} order link(s) onto the survivor")


SUFFIXES = (
    " (pvt.) ltd.", " (pvt) ltd.", " (pvt.) ltd", " (pvt) ltd",
    " pvt ltd", " limited", " ltd.", " ltd", " inc.", " inc", " co.",
)


def _stem(name):
    """A customer name with trailing company suffixes and case stripped."""
    s = name.strip().lower()
    changed = True
    while changed:
        changed = False
        for suffix in SUFFIXES:
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
                changed = True
    return s.rstrip(".,- ")


def duplicate_groups(names):
    """{stem: [variant, ...]} for stems with more than one spelling."""
    groups = defaultdict(list)
    for name in names:
        groups[_stem(name)].append(name)
    return {k: v for k, v in groups.items() if len(v) > 1}


def current_customer_names(db):
    """The names actually IN the master right now.

    Ambiguity must be judged against these, not against the raw names harvested
    from orders: the case-only duplicates have already been merged away, so
    "(S) NAKAMBALA" is gone and its survivor "(S) Nakambala" is the only
    spelling left — no longer ambiguous, and it should not be held back for
    review because a name that no longer exists once resembled it.
    """
    return [n for (n,) in db.execute(text("SELECT name FROM customers")).all()]


def set_verification(db, names):
    """Verify the clean names; leave only the ambiguous ones for review.

    Seeding all 335 customers unverified floods the review queue and puts an
    "Unverified" badge on every row, which makes the badge mean nothing. Seeding
    them all verified is the opposite lie — it asserts somebody checked names
    that came straight out of free text.

    So verification is targeted: a name that is the ONLY spelling of its stem is
    unambiguous and lands verified; a name that shares a stem with another
    ("CHERAT CEMENT" vs "CHERAT CEMENT LTD.") stays unverified, because which of
    them is the real customer is a decision only the business can make. That
    leaves a review queue holding exactly the rows that need a human.
    """
    ambiguous = {v for variants in duplicate_groups(names).values() for v in variants}

    if ambiguous:
        db.execute(
            text("""UPDATE customers SET is_verified = false
                    WHERE name = ANY(:names) AND is_verified = true"""),
            {"names": sorted(ambiguous)},
        )

    db.execute(
        text("""UPDATE customers SET is_verified = true
                WHERE NOT (name = ANY(:names)) AND is_verified = false"""),
        {"names": sorted(ambiguous) or [""]},
    )
    db.commit()

    verified = db.execute(text(
        "SELECT count(*) FROM customers WHERE is_verified = true"
    )).scalar()
    unverified = db.execute(text(
        "SELECT count(*) FROM customers WHERE is_verified = false"
    )).scalar()

    print(f"\nverification: {verified} clean name(s) verified, "
          f"{unverified} ambiguous left for review")


def report_duplicates(names):
    """Names that differ only by a trailing company suffix or by case.

    Not merged automatically — which of "CHERAT CEMENT" and "CHERAT CEMENT LTD."
    is the real customer, and whether "JK SUGAR MILLS I" and "II" are one site
    or two, is a business call. This just puts the candidates in front of
    somebody who can decide, from the Masters screen.
    """
    clashes = duplicate_groups(names)

    if not clashes:
        print("\nno obvious duplicate names.")
        return

    print(f"\n{len(clashes)} name group(s) look like the same customer "
          f"(these are the unverified ones in the review queue):")
    for stem_name, variants in sorted(clashes.items()):
        print(f"   {stem_name!r}")
        for v in sorted(variants):
            print(f"       - {v}")


if __name__ == "__main__":
    main()
