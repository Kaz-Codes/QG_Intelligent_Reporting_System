"""Create the Transporter master and link trucking jobs to it.

WHAT THIS DOES
    1. Creates the `transporters` table (create_all only ever ADDS missing
       tables, so this is safe on a populated database).
    2. Adds `trucking_consignments.transporter_id` — create_all cannot add a
       column to an existing table, so that one is a hand-written ALTER.
    3. Seeds one transporter per distinct `transporter_name` already on jobs.
    4. Backfills `transporter_id` by case-insensitive name match.

WHY THE SEEDED ROWS LAND UNVERIFIED
    They are harvested from free text nobody ever validated — the same reason
    the Customer master seeds unverified (see add_customer_master.py). The
    distinct names may hold duplicates ("ABC Goods Transport" vs "ABC Goods
    Transport (Pvt) Ltd."). Seeding them verified would assert a cleanliness
    the data does not have, so they land in the Masters review queue instead.

USAGE
    python -m app.loading.scripts.add_transporter_master
    python -m app.loading.scripts.add_transporter_master --check   # report only

Idempotent: re-running adds only names that are missing and re-links only rows
whose transporter_id is not already correct.
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
    """Create the transporters table and the trucking FK column."""
    Base.metadata.create_all(bind=engine)

    exists = db.execute(text("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'trucking_consignments' AND column_name = 'transporter_id'
    """)).scalar()

    if exists:
        print("  trucking_consignments.transporter_id already present")
        return

    db.execute(text("""
        ALTER TABLE trucking_consignments
        ADD COLUMN transporter_id INTEGER
        REFERENCES transporters(id) ON DELETE SET NULL
    """))
    db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_trucking_consignments_transporter_id
        ON trucking_consignments (transporter_id)
    """))
    db.commit()
    print("  added trucking_consignments.transporter_id (+ index)")


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
                SELECT 1 FROM information_schema.tables WHERE table_name = 'transporters'
            """)).scalar()
            print(f"schema: transporters table {'exists' if has_table else 'MISSING'}")
            if not has_table:
                print("\n--check given and the table does not exist yet; "
                      "nothing further to report.")
                return

        # ---- the names currently on trucking jobs ----
        rows = db.execute(text("""
            SELECT transporter_name, count(*)
            FROM trucking_consignments
            WHERE is_deleted = false AND transporter_name IS NOT NULL
              AND btrim(transporter_name) <> ''
            GROUP BY transporter_name
            ORDER BY count(*) DESC
        """)).all()

        names = {normalise(n): c for n, c in rows if normalise(n)}
        jobs_with_name = sum(names.values())

        total_jobs = db.execute(text(
            "SELECT count(*) FROM trucking_consignments WHERE is_deleted = false"
        )).scalar()

        print(f"\njobs: {total_jobs} live, {jobs_with_name} carry a transporter name")
        print(f"distinct names: {len(names)}")

        existing = {
            normalise(n).lower(): i
            for i, n in db.execute(text("SELECT id, name FROM transporters")).all()
        }
        missing = [n for n in names if n.lower() not in existing]
        print(f"transporters already in the master: {len(existing)}")
        print(f"to be created: {len(missing)}")

        if check_only:
            print("\n--check given, so nothing was changed.")
            report_duplicates(names)
            return

        # ---- seed ----
        #
        # Deduplicated CASE-INSENSITIVELY, the same reasoning as the customer
        # seeder: transporters.name is unique case-SENSITIVELY, so inserting
        # both "ABC Movers" and "abc movers" would succeed and then
        # resolve_transporter_id's case-insensitive lookup would have two rows
        # to choose from. One row per lowercased name closes that off. The
        # spelling kept is whichever the most jobs actually use.
        canonical = {}
        for name in missing:
            key = name.lower()
            if key not in canonical or names[name] > names[canonical[key]]:
                canonical[key] = name

        collapsed = len(missing) - len(canonical)

        for name in canonical.values():
            db.execute(
                text("""INSERT INTO transporters (name, is_active, is_verified)
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
            "SELECT setval('transporters_id_seq', (SELECT COALESCE(MAX(id), 1) FROM transporters))"
        ))
        db.commit()
        print(f"\ncreated {len(missing)} transporter(s), all unverified")

        # ---- backfill the link ----
        linked = db.execute(text("""
            UPDATE trucking_consignments AS j
            SET transporter_id = t.id
            FROM transporters AS t
            WHERE lower(btrim(j.transporter_name)) = lower(t.name)
              AND (j.transporter_id IS DISTINCT FROM t.id)
        """)).rowcount
        db.commit()
        print(f"linked {linked} job(s) to a transporter")

        # ---- verify ----
        still_null = db.execute(text("""
            SELECT count(*) FROM trucking_consignments
            WHERE is_deleted = false AND transporter_id IS NULL
              AND transporter_name IS NOT NULL AND btrim(transporter_name) <> ''
        """)).scalar()
        total_transporters = db.execute(text("SELECT count(*) FROM transporters")).scalar()

        print(f"\nresulting state:")
        print(f"   transporters         {total_transporters}")
        print(f"   jobs linked          "
              f"{db.execute(text('SELECT count(*) FROM trucking_consignments WHERE transporter_id IS NOT NULL')).scalar()}")
        print(f"   named but unlinked   {still_null}  (should be 0)")

        # Judged against the master as it now stands, not the raw job names.
        master_names = current_transporter_names(db)
        set_verification(db, master_names)
        report_duplicates(master_names)

    except Exception as e:
        db.rollback()
        print("failed:", e)
        raise

    finally:
        db.close()


def merge_case_duplicates(db):
    """Collapse transporters whose names differ only by capitalisation.

    Safe to do automatically, unlike the suffix duplicates report_duplicates
    lists — those are a business judgement about whether two spellings are the
    same company, this is just case. Jobs are moved onto the survivor before
    the extra rows are deleted, so no job loses its link. The survivor is the
    spelling the most jobs use.
    """
    groups = db.execute(text("""
        SELECT lower(name) AS key, array_agg(id ORDER BY id) AS ids
        FROM transporters
        GROUP BY lower(name)
        HAVING count(*) > 1
    """)).all()

    if not groups:
        return

    merged = 0
    moved = 0

    for _key, ids in groups:
        usage = dict(db.execute(text("""
            SELECT t.id, count(j.id)
            FROM transporters t
            LEFT JOIN trucking_consignments j
                   ON j.transporter_id = t.id AND j.is_deleted = false
            WHERE t.id = ANY(:ids)
            GROUP BY t.id
        """), {"ids": list(ids)}).all())

        # Most-used spelling wins; lowest id breaks a tie so the choice is
        # deterministic across runs.
        keep = max(ids, key=lambda i: (usage.get(i, 0), -i))
        drop = [i for i in ids if i != keep]

        moved += db.execute(text("""
            UPDATE trucking_consignments
            SET transporter_id = :keep
            WHERE transporter_id = ANY(:drop)
        """), {"keep": keep, "drop": drop}).rowcount

        db.execute(text("DELETE FROM transporters WHERE id = ANY(:drop)"), {"drop": drop})
        merged += len(drop)

    db.commit()
    print(f"  merged {merged} case-only duplicate transporter(s); "
          f"moved {moved} job link(s) onto the survivor")


SUFFIXES = (
    " (pvt.) ltd.", " (pvt) ltd.", " (pvt.) ltd", " (pvt) ltd",
    " pvt ltd", " limited", " ltd.", " ltd", " inc.", " inc", " co.",
    " transport", " transporters", " goods transport", " logistics",
)


def _stem(name):
    """A transporter name with trailing company suffixes and case stripped."""
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


def current_transporter_names(db):
    """The names actually IN the master right now — see add_customer_master's
    identical helper for why ambiguity must be judged against these, not the
    raw job names."""
    return [n for (n,) in db.execute(text("SELECT name FROM transporters")).all()]


def set_verification(db, names):
    """Verify the clean names; leave only the ambiguous ones for review.

    Same targeted approach as the customer seeder: a name that is the ONLY
    spelling of its stem is unambiguous and lands verified; a name sharing a
    stem with another stays unverified, because which of them is the real
    transporter (or whether they are two transporters that happen to share a
    stem) is a business call.
    """
    ambiguous = {v for variants in duplicate_groups(names).values() for v in variants}

    if ambiguous:
        db.execute(
            text("""UPDATE transporters SET is_verified = false
                    WHERE name = ANY(:names) AND is_verified = true"""),
            {"names": sorted(ambiguous)},
        )

    db.execute(
        text("""UPDATE transporters SET is_verified = true
                WHERE NOT (name = ANY(:names)) AND is_verified = false"""),
        {"names": sorted(ambiguous) or [""]},
    )
    db.commit()

    verified = db.execute(text(
        "SELECT count(*) FROM transporters WHERE is_verified = true"
    )).scalar()
    unverified = db.execute(text(
        "SELECT count(*) FROM transporters WHERE is_verified = false"
    )).scalar()

    print(f"\nverification: {verified} clean name(s) verified, "
          f"{unverified} ambiguous left for review")


def report_duplicates(names):
    """Names that differ only by a trailing company suffix or by case.

    Not merged automatically — a business call, same as the customer seeder.
    This just puts the candidates in front of somebody who can decide, from
    the Masters screen.
    """
    clashes = duplicate_groups(names)

    if not clashes:
        print("\nno obvious duplicate names.")
        return

    print(f"\n{len(clashes)} name group(s) look like the same transporter "
          f"(these are the unverified ones in the review queue):")
    for stem_name, variants in sorted(clashes.items()):
        print(f"   {stem_name!r}")
        for v in sorted(variants):
            print(f"       - {v}")


if __name__ == "__main__":
    main()
