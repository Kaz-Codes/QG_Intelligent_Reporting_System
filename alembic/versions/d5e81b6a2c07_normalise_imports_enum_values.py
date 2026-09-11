"""normalise the imports enum values loaded from the workbooks

WHAT THIS FIXES, AND WHY IT IS URGENT RATHER THAN TIDY

A LOADED CONSIGNMENT CANNOT BE SAVED. The detail route returns
`mode_of_shipment: 'Sea'`; the wizard posts the whole draft back on every save
(it must - the update route diffs item lines against the payload); and
`ConsignmentSchema` types that field as `ModeOfShipment`, which holds only
'Sea freight FCL', 'Sea freight LCL', 'Air freight' and 'Land/courier'. So the
PUT is rejected 422 on a field the operator never touched.

Measured on the development database (178 live consignments, 450 item lines):

    consignments.mode_of_shipment              171 of 178  - NOT ONE valid
    consignments.payment_instrument             87 of 178
    consignment_batch_groups.payment_instrument 87 of 178  <-- THE COPY THAT IS READ
    consignment_items.unit_of_measurement        59 of 450 lines
    consignment_order_items.unit_of_measurement  59 of 450 rows
    --------------------------------------------------------------------------
    consignments carrying at least one          172 of 178  (96.6%)

A DATA MIGRATION IS A WRITE PATH, AND IN AN EXPAND-AND-CONTRACT GAP IT HAS TO
MAINTAIN BOTH COPIES LIKE EVERY OTHER ONE

The third line above was missed on the first pass, and the way it was missed is
worth more than the fix. Revision A COPIES `payment_instrument` onto
`consignment_batch_groups`, and the serializer reads it from the group
(`order_view.order_payment_instrument`). So updating `consignments` alone
corrected the copy nothing reads and left the one everything reads holding
'Advance', 'FOC' and 'Contract' — a loaded consignment still rejected its own
save, while every test in this revision passed.

This is the second instance of the same lesson (design section 4.7, fourth
bypass path): during the gap between expand and contract, a value exists twice
and EVERY write path has to maintain both. The first instance was an ordinary
ORM update; this one is a migration. Neither bypasses the model, which is why
neither was caught by the control 4.7 was built around.

`mode_of_shipment` needs no group entry — it stays per batch. The other shared
columns were measured ON THE GROUP rather than inferred from the consignment,
because inferring is what produced this: `currency` (USD/JPY/EUR/GBP) and
`consignment_type` (EFS/Regular import) are clean there, and `incoterm` and
`rate_source` are NULL on every row.

THE THIRD COLUMN WAS FOUND BY THE TEST, NOT BY THE SURVEY

The first survey looked at the consignment header's enum columns and at
`requisition_type`. It missed `unit_of_measurement`, which sits on the item LINE
and is typed `Optional[UnitOfMeasurement]` in `ConsignmentItemSchema` — so a
round-trip still 422'd, on `items[0].unit_of_measurement`, after both header
columns were clean. 8 of the 36 unlocked live consignments failed that way.

Worth recording as a method point rather than a detail: the header survey
answered the question it was asked, and the question was too narrow. What
established the real blast radius was driving the actual PUT over every record.

Nothing on the front end normalises it either: `importsMap.apiToDraft` casts
with `as ConsignmentDraft['modeOfShipment']`, which is a compile-time assertion
with no runtime effect, and `draftToPayload` passes the raw string straight back
through `strOrUndef`. The only field with a real gate is `consignment_type`
(`CONSIGNMENT_TYPE_TO_API`).

It has gone unnoticed for one reason only: nobody has edited a loaded
consignment yet. That is about to change, which is why this runs before the
batching work that inverts the write path - landing a write-path change on a
path already rejecting 96.6% of records means debugging two faults as one.

WHY AN ALEMBIC REVISION AND NOT A SCRIPT IN app/loading/scripts

Because it has to be applied exactly once, on deploy, on a database where
nobody can check afterwards whether somebody remembered to run it. A one-off
script is remembered or it is not; a revision is part of `alembic upgrade head`,
which CLAUDE.md already names as a required deploy step.

THE MAPPING IS A BUSINESS DECISION, NOT A DERIVATION

Given by the business rather than inferred from the data:

    mode_of_shipment
        Sea, By Sea                      -> Sea freight FCL
        the container specs (1 x 20' OT) -> Sea freight FCL
        LCL                              -> Sea freight LCL
        Air, By Air                      -> Air freight

    Full container is the norm here, and the container-spec rows say so
    themselves.

    payment_instrument
        Advance   -> Adv
        100%LC    -> LC
        TT        -> Adv      the same thing in practice
        FOC, Exp, Contract -> NULL        junk

THE UNIT MAPPING IS A DIFFERENT KIND OF THING, AND ONE ENTRY NEEDS A DECISION

Unlike the two above, these are not a vocabulary the business has to rule on -
they are the SAME unit spelled differently, and each target is already in the
enum:

    Kgs  -> Kg        Pcs. -> Pcs
    Tons -> Ton       Pc   -> Pcs
                      Pc.  -> Pcs

    MT   -> Ton       <-- THE ONE JUDGEMENT CALL, AND IT IS MINE, NOT THE
                          BUSINESS'S. 'MT' is metric tonne. The enum has only
                          'Ton' and no short/long-ton distinction anywhere in
                          the system, so 'Ton' is the only value it can land on
                          - but if 'Ton' is meant to mean something other than
                          1000 kg, these 7 lines are being quietly restated and
                          this entry should be removed and the 7 rows looked at
                          by hand. Flagged rather than buried.

MATCHED ON THE VALUE, NEVER ON THE COUNT

Every number above was measured on a database holding 178 consignments.
Production holds 191 and will hold more. So this revision matches on what the
column SAYS and reports what it actually changed; it asserts nothing about how
many rows say it. Matching is case- and whitespace-insensitive, because loaded
data varies ('By Sea', 'By  Air' with two spaces) and a fix that lands on one
spelling and not another is worse than no fix - it leaves a residue nobody
looks for.

ANYTHING UNRECOGNISED IS LEFT ALONE AND REPORTED. A value nobody anticipated is
a thing to look at, not a thing to blank. This revision prints it and moves on.

IT IS REVERSIBLE, AND THAT IS WHY THE AUDIT TABLE EXISTS

`downgrade()` cannot restore 'By Sea' from 'Sea freight FCL' by rule - the
mapping is many-to-one, so the original string is genuinely unrecoverable from
the result. Rather than declare this one-way and ask for a backup (section 4.6's
approach), it records every value it overwrites in
`enum_normalisation_audit` and restores from that row by row. The table is
small (one row per changed cell) and is the same mechanism that answers the
second problem below.

THE CONTAINER DETAIL WOULD OTHERWISE BE DESTROYED - CHECKED, NOT ASSUMED

12 consignments record their container configuration in `mode_of_shipment` and
NOWHERE ELSE. Verified against the schema and the rows: `container_detention`
is a PKR amount, `free_days_allowed` is an integer, and `remarks` reads
"On time" on all twelve. There is no container count, size or type column on
`consignments` at all.

    id 2,3     1 x 20' OT     id 134      2 x 20' STD
    id 5       2 x 20' OT     id 135,136  3 x 20' Std.
    id 6       1 x 40' OT     id 137      1 x 20' STD
    id 7       3 x 20' OT     id 138      4 x 20' Std.
    id 8       1 x 20' O/T    id 147      1 x 40' HC

Collapsing all twelve to 'Sea freight FCL' loses the count, the size and the
type (OT = open top, STD = standard, HC = high cube) - real operational facts,
on shipments that actually happened. The audit table below PRESERVES every one
of them, so nothing is destroyed by this revision.

It is preservation, not a home. A proper column on `consignments` (a free-text
`container_summary`, or a child table if imports ever needs per-container rows
the way logistics does) is the right long-term answer and is a schema decision
for the owner rather than something to slip into a data fix.

THE SAME BUG EXISTS IN TRUCKING AND LOGISTICS AND IS DELIBERATELY NOT FIXED HERE

    trucking  payment_status   'Paid' (210), 'To pay' (91), 'Topay' (2)
              container_type   '20 FT' (94), '40 FT' (11)
              tracking_status  'On Road' (23), 'Planned' (4)
              -> 309 of 1369 jobs cannot be saved

    logistics department       'G.I Floor Mills' (1)
              -> 1 of 745 orders cannot be saved
              (logistics_containers.container_type holds 'LCL' and 'AIR' but
               its schema types that field as a plain str, so it does not
               reject - which is why only department bites)

Their mappings need the same business decision this one had ('Paid' and
'To pay' are a different vocabulary from 'Customer to pay' / 'QG to pay', and
'Planned' is a tracking state the enum does not have at all). Reported rather
than guessed.

AUTOGENERATE WILL NOT PROPOSE DROPPING THE AUDIT TABLE - CHECKED

`enum_normalisation_audit` is created here and is deliberately NOT in
`Base.metadata`: it is a record of this migration, not part of the application's
schema, and nothing under `app/` reads it. That would normally mean the next
`--autogenerate` reads it as "removed" and emits a DROP - the trap revision A's
docstring warns about for the orphaned columns.

It does not, and the reason is already in the tree: `alembic/env.py`'s
`include_object` returns False for any reflected table with no counterpart in
the metadata (it was written to stop autogenerate dropping chatbot_backend's
tables, which live in the same database and are owned by a different service).
This table gets the same protection for the same reason. Verified against that
filter rather than assumed, because the table holds the only copy of the twelve
container specifications and `downgrade()` cannot work without it.

Revision ID: d5e81b6a2c07
Revises: a1c4f27b93de
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e81b6a2c07"
down_revision: Union[str, Sequence[str], None] = "a1c4f27b93de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AUDIT_TABLE = "enum_normalisation_audit"

# The normalisation key: lower-cased, inner whitespace collapsed. 'By  Air'
# with two spaces and 'by air' both reduce to 'by air', so one mapping entry
# catches every spelling of a value instead of one entry per spelling.
#
# Keys here are already normalised. `_key()` below must stay the only thing that
# produces them, or a mapping entry can quietly stop matching.
MODE_OF_SHIPMENT = {
    "sea": "Sea freight FCL",
    "by sea": "Sea freight FCL",
    "lcl": "Sea freight LCL",
    "air": "Air freight",
    "by air": "Air freight",
}

PAYMENT_INSTRUMENT = {
    "advance": "Adv",
    "100%lc": "LC",
    "tt": "Adv",
    # Junk: these are not payment instruments. NULL, not a guess.
    "foc": None,
    "exp": None,
    "contract": None,
}

# Spelling variants of units already in the enum. See the docstring for why
# `mt` is the one entry here carrying an interpretation.
UNIT_OF_MEASUREMENT = {
    "kgs": "Kg",
    "tons": "Ton",
    "mt": "Ton",
    "pcs.": "Pcs",
    "pc": "Pcs",
    "pc.": "Pcs",
}

# WHAT TO NORMALISE, AS DATA: (table, column, mapping, container specs allowed).
#
# Table-driven rather than three hardcoded blocks, because the third column was
# missed once already and the same column appears on TWO tables — revision A
# copied `unit_of_measurement` onto `consignment_order_items`, so fixing only the
# line table would leave the order line holding the old spelling and the two
# copies disagreeing about the same unit.
TARGETS = [
    ("consignments", "mode_of_shipment", MODE_OF_SHIPMENT, True),
    ("consignments", "payment_instrument", PAYMENT_INSTRUMENT, False),
    # THE COPY THE CODE ACTUALLY READS. Revision A copies payment_instrument
    # onto the batch group, and the serializer reads it from THERE
    # (order_view.order_payment_instrument). Fixing only `consignments` updated
    # the unread copy and left the group holding 'Advance', 'FOC' and
    # 'Contract' — so a loaded consignment still 422'd, with every test here
    # passing. See the docstring: "A DATA MIGRATION IS A WRITE PATH".
    ("consignment_batch_groups", "payment_instrument", PAYMENT_INSTRUMENT, False),
    ("consignment_items", "unit_of_measurement", UNIT_OF_MEASUREMENT, False),
    ("consignment_order_items", "unit_of_measurement", UNIT_OF_MEASUREMENT, False),
]

def _key(value):
    """The match key: lower-cased with inner whitespace collapsed."""
    return " ".join(value.lower().split()) if value is not None else None


def _rows(conn, table, column):
    """Every distinct stored value of one column, with its row count."""
    return conn.execute(sa.text(
        f"SELECT {column} AS value, count(*) AS n FROM {table} "
        f"WHERE {column} IS NOT NULL GROUP BY {column} ORDER BY {column}"
    )).all()


def _is_container_spec(value):
    """"1 x 20' OT", "3 x 20' Std.", "1 x 40' HC" — a container specification
    somebody typed into the shipment-mode column, not a shipment mode.

    Matched by SHAPE (<digits> x <digits>) rather than by listing the twelve
    spellings, because the list is a fact about this database and the next
    workbook will spell them differently. Every one is a sea shipment in a full
    container, so they all land on FCL; the specification itself survives in the
    audit table, which is its only copy.
    """
    import re
    return bool(re.match(r"^\s*\d+\s*[xX]\s*\d+", value or ""))


def upgrade() -> None:
    conn = op.get_bind()

    # The audit table. Created here rather than in the models because it is a
    # record of THIS migration, not part of the application's schema - nothing
    # in app/ reads it, and `downgrade` is its only consumer.
    #
    # It is deliberately NOT dropped on downgrade: see the comment there.
    op.create_table(
        AUDIT_TABLE,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("table_name", sa.String(length=100), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.String(length=100), nullable=False),
        sa.Column("old_value", sa.String(length=255), nullable=True),
        sa.Column("new_value", sa.String(length=255), nullable=True),
        sa.Column("revision", sa.String(length=50), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        if_not_exists=True,
    )
    # THE INDEX IS CREATED SEPARATELY, and that is not a style choice.
    #
    # `create_table(if_not_exists=True)` guards the TABLE only; an `sa.Index`
    # declared inside the table definition is still emitted as its own CREATE
    # INDEX with no guard on it. So downgrade-then-upgrade — the ordinary
    # rollback-and-retry path — died on `DuplicateTable: relation
    # "ix_enum_normalisation_audit_target" already exists`, because downgrade
    # deliberately keeps the table (see below) and therefore keeps its index.
    #
    # Found by actually running that path rather than by reading the code: the
    # first attempt reported nothing amiss because the failure happened before
    # any work, so the audit row count had not changed and that looked like
    # "nothing to do" instead of "it fell over".
    op.create_index(f"ix_{AUDIT_TABLE}_target", AUDIT_TABLE,
                    ["table_name", "row_id", "column_name"], if_not_exists=True)

    # A RE-UPGRADE REDOES THE SAME WORK, so it must not leave two audit rows per
    # cell. With two, `downgrade` would pick between them arbitrarily — harmless
    # here only because both would hold the same original value, which is the
    # kind of "harmless" that stops being true after one more change.
    conn.execute(sa.text(f"DELETE FROM {AUDIT_TABLE} WHERE revision = :rev"),
                 {"rev": revision})

    print("\n--- normalising imports enum values "
          "(matched on the stored value, not on expected counts) ---")

    total_changed = 0
    unrecognised = []

    for table, column, mapping, allow_container_spec in TARGETS:
        print(f"\n  {table}.{column}:")
        changed_here = 0

        for value, n in _rows(conn, table, column):
            key = _key(value)

            if key in mapping:
                new_value = mapping[key]
            elif allow_container_spec and _is_container_spec(value):
                # A container specification. Lands on FCL; the spec itself is
                # kept in the audit table, which is the only copy of it.
                new_value = "Sea freight FCL"
            else:
                # ALREADY VALID, or something nobody anticipated. Either way it
                # is left exactly as it is and named below. A value we cannot
                # place is evidence, not rubbish.
                unrecognised.append((f"{table}.{column}", value, n))
                continue

            if value == new_value:
                continue

            # The audit row first, then the update, so a failure between them
            # cannot leave a changed cell with no record of what it held.
            conn.execute(
                sa.text(f"""
                    INSERT INTO {AUDIT_TABLE}
                        (table_name, row_id, column_name, old_value, new_value, revision)
                    SELECT :tbl, id, :col, {column}, :new_value, :rev
                      FROM {table}
                     WHERE {column} = :old_value
                """),
                {"tbl": table, "col": column, "new_value": new_value,
                 "old_value": value, "rev": revision},
            )
            result = conn.execute(
                sa.text(f"UPDATE {table} SET {column} = :new_value "
                        f"WHERE {column} = :old_value"),
                {"new_value": new_value, "old_value": value},
            )
            changed_here += result.rowcount
            print(f"    {value!r:>22} -> {new_value!r:<18} {result.rowcount:>4} rows")

        total_changed += changed_here
        print(f"    {'':>22}    {'':<18} {changed_here:>4} changed")

    if unrecognised:
        print("\n  LEFT UNCHANGED (already valid, or not in the mapping — "
              "check the second group):")
        for column, value, n in unrecognised:
            print(f"    {column}.{value!r} — {n} rows")

    print(f"\n  {total_changed} cells changed in total. "
          f"Originals are in {AUDIT_TABLE} and downgrade() restores from it.\n")

    # WHAT IS LEFT REJECTING, reported rather than assumed fixed. A row whose
    # value this revision could not place still cannot be saved, and saying so
    # here is the difference between a fix and a fix that looks complete.
    UOM = ("'Pcs','Set','Pair','Roll','Box','Carton','Drum','Pallet','Kg','Gram',"
           "'Ton','Lb','Metre','Centimetre','Foot','Inch','Sq. metre','Cu. metre','Litre'")
    still_bad = conn.execute(sa.text(f"""
        SELECT count(*) FROM consignments c
         WHERE c.is_deleted = false
           AND ((c.mode_of_shipment IS NOT NULL
                 AND c.mode_of_shipment NOT IN ('Sea freight FCL','Sea freight LCL',
                                                'Air freight','Land/courier'))
             OR (c.payment_instrument IS NOT NULL
                 AND c.payment_instrument NOT IN ('LC','Adv','DP','CAD'))
             -- AND THE GROUP'S COPY, which is the one the serializer reads.
             -- Checking the consignment alone is precisely how this revision
             -- first reported success over 87 records that still could not be
             -- saved.
             OR EXISTS (SELECT 1 FROM consignment_batch_groups g
                         WHERE g.id = c.batch_group_id
                           AND g.payment_instrument IS NOT NULL
                           AND g.payment_instrument NOT IN ('LC','Adv','DP','CAD'))
             -- The item lines count too: a consignment whose LINE holds a bad
             -- unit still cannot be saved, so a header-only check would report
             -- success while the record stayed stuck. That is exactly how the
             -- third column was missed the first time.
             OR EXISTS (SELECT 1 FROM consignment_items i
                         WHERE i.consignment_id = c.id AND i.is_deleted = false
                           AND i.unit_of_measurement IS NOT NULL
                           AND i.unit_of_measurement NOT IN ({UOM})))
    """)).scalar()
    live = conn.execute(sa.text(
        "SELECT count(*) FROM consignments WHERE is_deleted = false")).scalar()
    print(f"  live consignments still holding an out-of-enum value ANYWHERE "
          f"(header or item line): {still_bad} of {live}\n")


def downgrade() -> None:
    """Put every overwritten value back, from the audit table.

    Row by row rather than by rule, because the mapping is MANY-TO-ONE: 'Sea',
    'By Sea' and twelve container specifications all became 'Sea freight FCL',
    so nothing in the result says which one a given row held. The audit row is
    the only thing that does.

    THE AUDIT TABLE IS NOT DROPPED. It is the sole surviving copy of the twelve
    consignments' container specifications (see the docstring), and dropping it
    on downgrade would make a rollback destroy data that the upgrade went out of
    its way to preserve. It is a few hundred rows and nothing in the application
    reads it; leaving it costs nothing and losing it cannot be undone.
    """
    conn = op.get_bind()
    total = 0

    # Driven off the same TARGETS list the upgrade used, so a column added there
    # is restored here without a second edit — the failure mode being a revision
    # that normalises four columns and puts three of them back.
    for table, column, _mapping, _spec in TARGETS:
        result = conn.execute(sa.text(f"""
            UPDATE {table} t
               SET {column} = a.old_value
              FROM {AUDIT_TABLE} a
             WHERE a.table_name = :tbl
               AND a.column_name = :col
               AND a.row_id = t.id
               AND a.revision = :rev
        """), {"tbl": table, "col": column, "rev": revision})
        total += result.rowcount
        print(f"  restored {result.rowcount:>4} rows of {table}.{column}")

    print(f"\n  {total} cells restored from {AUDIT_TABLE} — the table is KEPT, "
          f"because it holds the only copy of the container specifications\n")
