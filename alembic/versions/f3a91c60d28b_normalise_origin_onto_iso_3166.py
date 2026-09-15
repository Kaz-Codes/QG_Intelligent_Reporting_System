"""normalise consignment origin onto ISO 3166 country names

Revision ID: f3a91c60d28b
Revises: c7b210d4e9f3
Create Date: 2026-09-14

WHY A MIGRATION AND NOT A TRANSLATION ON EVERY RENDER
=====================================================

`origin` is free text on the order and has been since the workbooks. Step 8
made "Country of origin" a searchable list of the 249 ISO 3166-1 names, which
exposed how far the stored data is from them: of the 174 consignments that
state an origin, **59 carry a spelling that is not an ISO name** - `Turkey`,
`UAE`, `SA`, `USA`, `South Korea`, `Korea`, `Taiwan`, `Tanzania`, `KSA`, and
two misspellings of the Philippines.

Translating those at display time would mean every screen, every export and
every report carrying the same lookup table, and the underlying column would
stay wrong for anything that reads it directly - including the chatbot, see
below. Correcting the stored data once is the smaller and more durable change.

IT UPDATES BOTH COPIES OF THE COLUMN, AND THAT IS NOT BELT AND BRACES
=====================================================================

`origin` lives on `consignment_batch_groups` (the live column) AND on
`consignments` (the pre-batching copy, left in place with no mapped attribute
until Revision B - design section 4.5/4.7). The loaders deliberately write
both, and they hold identical distributions today.

**`v_import_shafts` reads `consignments.origin`** - one of the two semantic
views that belong to `chatbot_backend`, are absent from `Base.metadata`, and
are invisible to `create_all`, to autogenerate and to `configure_mappers()`
(design section 4.6). Updating only the group would leave the ERP reporting
`United Arab Emirates` while the chatbot went on reporting `UAE` for the same
consignment, with nothing anywhere to say why. Confirmed by asking the
database:

    SELECT viewname FROM pg_views
     WHERE schemaname = 'public' AND definition ILIKE '%origin%';
    -- v_import_shafts

WHAT IS MAPPED, AND THE ONE DECISION THAT WAS NOT MINE
======================================================

Every mapping below is a whole-value match onto the ISO 3166-1 English short
name in `React_Frontend-main/frontend/src/lib/countries.ts`.

**`SA` -> Saudi Arabia is a BUSINESS DECISION, taken by the project owner.**
It was reported as genuinely ambiguous and not migrated on my own reading:
`SA` is 11 consignments, the third commonest value in the column, and this
database holds BOTH candidate countries under other names (`South Africa` 7
rows, `KSA` 1). It is recorded here rather than in a commit message because
this file is what a later reader will find when they wonder why eleven
consignments changed country.

Nothing is mapped on a guess. A value with no unambiguous ISO equivalent would
have been left alone and reported; after this revision there are none left.

REVERSIBILITY - THE DOWNGRADE IS A DELIBERATE NO-OP
===================================================

This mapping is many-to-one: `SA` and `KSA` both become Saudi Arabia, `Korea`
and `South Korea` both become Korea, Republic of, and `Phillpines` and
`Philipine` both become Philippines. The original spelling is not recoverable
from the result, so a downgrade could only pick one representative per ISO
name and would silently invent history for the other - writing `KSA` onto
eleven rows that said `SA`, or the reverse.

So `downgrade()` does nothing and says so. The upgrade is a data correction,
not a structural change: nothing downstream depends on the old spellings, and
a schema rollback past this point leaves the corrected text in place, which is
harmless. If the old values are genuinely wanted back, they are in any backup
taken before this ran.

DURABILITY - THE LOADER HAD TO CHANGE TOO
=========================================

A migration alone would not hold: `load_05_consignments` writes `origin`
straight from the workbook's `Country` column, so the next
`reload_changed` / `load_all` would put `UAE` and `Turkey` back. `map_country`
in that loader applies the same mapping at load time, the way `map_currency`
and `map_mode_of_shipment` already do for their columns. The table is
duplicated there rather than imported from here on purpose: an Alembic
revision is a snapshot of what was true when it ran, and must not change
meaning because a constant somewhere else was edited later.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a91c60d28b"
down_revision: Union[str, Sequence[str], None] = "c7b210d4e9f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Stored spelling -> ISO 3166-1 English short name.
#
# Frozen here, deliberately not imported from the loader: see the module
# docstring. The counts are what this database held when the revision was
# written and are recorded so a run that touches a very different number of
# rows is recognisable as such.
ORIGIN_TO_ISO = [
    ("Turkey",      "Türkiye"),                     # 16
    ("UAE",         "United Arab Emirates"),        # 12
    ("SA",          "Saudi Arabia"),                # 11  <- the business call
    ("USA",         "United States of America"),    #  6
    ("South Korea", "Korea, Republic of"),          #  4
    ("Korea",       "Korea, Republic of"),          #  3
    ("Taiwan",      "Taiwan, Province of China"),   #  2
    ("Tanzania",    "Tanzania, United Republic of"),#  2
    ("KSA",         "Saudi Arabia"),                #  1
    ("Phillpines",  "Philippines"),                 #  1
    ("Philipine",   "Philippines"),                 #  1
]

# Both copies of the column. See the module docstring for why the second one
# is not optional.
ORIGIN_TABLES = ("consignment_batch_groups", "consignments")


def upgrade() -> None:
    conn = op.get_bind()

    for table in ORIGIN_TABLES:
        # A table that does not exist is not an error here: `consignments.origin`
        # is scheduled for removal in Revision B, and this revision must still
        # apply cleanly to a database where that has already happened.
        if not _has_origin(conn, table):
            print(f"  {table}: no `origin` column, skipped")
            continue

        total = 0
        for stored, iso in ORIGIN_TO_ISO:
            # MATCHED CASE-INSENSITIVELY AND TRIMMED, on the WHOLE value.
            # The column is hand-typed free text, so ` uae ` and `Uae` are the
            # same mistake as `UAE`; matching the whole trimmed value is what
            # keeps `Korea` from also catching `South Korea`.
            result = conn.execute(
                sa.text(
                    f"UPDATE {table} SET origin = :iso "  # noqa: S608 - fixed list
                    "WHERE lower(btrim(origin)) = lower(:stored)"
                ),
                {"iso": iso, "stored": stored},
            )
            if result.rowcount:
                print(f"  {table}: {stored!r} -> {iso!r}  ({result.rowcount} rows)")
                total += result.rowcount

        print(f"  {table}: {total} rows normalised")

        # WHAT IS LEFT THAT IS STILL NOT ISO - reported, never guessed at. A
        # workbook loaded after this revision was written can perfectly well
        # carry a spelling nobody has seen yet, and the honest outcome is a
        # named leftover rather than a silent one or a wrong mapping.
        leftovers = conn.execute(
            sa.text(
                f"SELECT origin, count(*) FROM {table} "  # noqa: S608 - fixed list
                "WHERE origin IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
            )
        ).all()
        unknown = [(o, n) for o, n in leftovers if o not in _ISO_NAMES]
        if unknown:
            print(f"  {table}: STILL NOT ISO, left as they are - {unknown}")


def downgrade() -> None:
    """Deliberately does nothing. See the module docstring.

    The mapping is many-to-one, so there is no faithful reverse: restoring it
    would mean choosing one of `SA`/`KSA` for eleven rows that were `SA` and
    one that was `KSA`, and writing the loser's spelling onto records that
    never carried it. A migration that invents history is worse than one that
    declines to run backwards.
    """
    print("  origin normalisation is not reversed - the mapping is many-to-one "
          "and the original spellings are not recoverable from the result. "
          "See the revision docstring.")


#---------------------------------------------------------------------------
# helpers
#---------------------------------------------------------------------------

def _has_origin(conn, table):
    return bool(conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = 'origin'"
        ),
        {"t": table},
    ).scalar())


# Only the names this revision can produce, plus the ones already correct in
# this database. Used for the leftover report above and nothing else - it is
# not a validation list, and a name missing from it is reported rather than
# rejected.
_ISO_NAMES = {
    "Türkiye", "United Arab Emirates", "Saudi Arabia",
    "United States of America", "Korea, Republic of",
    "Taiwan, Province of China", "Tanzania, United Republic of", "Philippines",
    "China", "South Africa", "Canada", "Hong Kong", "Italy", "Germany",
    "Sweden", "Pakistan", "Malaysia", "Singapore",
}
