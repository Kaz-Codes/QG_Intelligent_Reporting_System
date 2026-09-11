"""batching revision A - expand

Creates the batch group and order item tables, adds the link columns, and
COPIES the values that are moving up or down a level onto the new rows.

WHAT "ADDITIVE" MEANS HERE, AND WHY IT IS THE WHOLE POINT

    This revision creates and it copies. It does not drop a column, alter a
    column, or move data off anything. Every column it reads keeps its value
    exactly where it was; the new tables hold a second copy, and only the new
    copy is read once the code catches up.

    That is what makes `downgrade()` below trivial and genuinely reversible: it
    drops what this revision added and nothing else. There is no data-restoring
    downgrade to write, and therefore no untested path shipping alongside the
    risky deploy. Revision B - a release later, once batching has actually run -
    is the one that drops the now-orphaned columns and the one that needs a
    backup taken first.

    If a future edit to this file finds itself writing data back in
    `downgrade()`, the revision has stopped being additive and the change
    belongs in revision B instead.

WHAT IT DOES NOT DO

    It does not split the 15 historical consignments that carry several values
    in the free-text `batch_no`. Splitting them would restate `foreign_total`
    and `pkr_total` on consignments whose goods have arrived and whose figures
    have been reported, inside a migration where nobody reviews the arithmetic,
    and roughly twelve of the fifteen are locked. `batch_no` stays readable as
    the historical record of how those consignments were split and is never
    converted.

A NOTE FOR WHOEVER RUNS `--autogenerate` NEXT

    Once the mapped attributes for the copied columns are removed from
    `Consignment` and `ConsignmentItem` (a separate change), those columns still
    exist in the database with nothing in the models to match. The next
    autogenerate for any unrelated change will therefore propose DROPPING them -
    that is revision B arriving early inside a revision nobody meant to be
    revision B. Delete those drops from the generated file. Autogenerate is a
    first draft, not a fact.

Revision ID: a1c4f27b93de
Revises: 3142a00a5b31
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1c4f27b93de'
down_revision: Union[str, Sequence[str], None] = '3142a00a5b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The eleven values that are shared by every batch of one order, plus the
# header branch. They are copied onto the group and LEFT IN PLACE on the
# consignment; revision B drops the originals.
#
# `branch_id` becomes `works_branch_id`: Works and Branch were always the same
# thing to the business, and with branch moving to the item level the group is
# where the header-level branch now lives.
SHARED_COLUMNS = [
    "supplier_id",
    "origin",
    "currency",
    "consignment_type",
    "incoterm",
    "payment_instrument",
    "instrument_number",
    "exchange_rate",
    "rate_booked_on",
    "rate_source",
]


def upgrade() -> None:
    #-------------------------------------------------
    # 1. THE TWO NEW TABLES
    #-------------------------------------------------

    op.create_table(
        "consignment_batch_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("founding_consignment_id", sa.Integer(), nullable=False),
        sa.Column("batches_ever", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=True),
        sa.Column("consignment_type", sa.String(length=50), nullable=True),
        sa.Column("incoterm", sa.String(length=10), nullable=True),
        sa.Column("payment_instrument", sa.String(length=20), nullable=True),
        sa.Column("instrument_number", sa.String(length=100), nullable=True),
        sa.Column("exchange_rate", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("rate_booked_on", sa.Date(), nullable=True),
        sa.Column("rate_source", sa.String(length=50), nullable=True),
        sa.Column("works_branch_id", sa.Integer(), nullable=True),
        sa.Column("insurance_amount", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT",
                                name="fk_batch_groups_created_by"),
        sa.ForeignKeyConstraint(["deleted_by_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_batch_groups_deleted_by"),
        # DEFERRABLE, and so is consignments.batch_group_id below. The two
        # tables reference each other and BOTH columns are NOT NULL, so with
        # the checks done per statement there is no order in which a new order
        # and its first batch can be inserted: the group needs a consignment
        # that does not exist yet, and the consignment needs a group that does
        # not exist yet. Verified against the database, in all three orderings.
        #
        # Deferring to COMMIT does not weaken the constraint - it is still
        # enforced, and a transaction that leaves either side dangling still
        # fails. It only lets the two inserts happen in the same transaction,
        # which is the only way either of them can happen at all.
        sa.ForeignKeyConstraint(["founding_consignment_id"], ["consignments.id"],
                                ondelete="RESTRICT", name="fk_batch_groups_founding_consignment",
                                deferrable=True, initially="DEFERRED"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="SET NULL",
                                name="fk_batch_groups_supplier"),
        sa.ForeignKeyConstraint(["works_branch_id"], ["branches.id"], ondelete="SET NULL",
                                name="fk_batch_groups_works_branch"),
        sa.PrimaryKeyConstraint("id", name="pk_consignment_batch_groups"),
    )
    op.create_index("ix_consignment_batch_groups_founding_consignment_id",
                    "consignment_batch_groups", ["founding_consignment_id"])
    op.create_index("ix_consignment_batch_groups_is_deleted",
                    "consignment_batch_groups", ["is_deleted"])

    op.create_table(
        "consignment_order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_group_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("item_code", sa.String(length=100), nullable=True),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("placeholder_name", sa.String(length=255), nullable=True),
        sa.Column("specification", sa.String(length=500), nullable=True),
        sa.Column("hs_code", sa.String(length=50), nullable=True),
        sa.Column("ordered_quantity", sa.Numeric(precision=14, scale=3), nullable=False),
        sa.Column("allocated_quantity", sa.Numeric(precision=14, scale=3),
                  server_default=sa.text("0"), nullable=False),
        sa.Column("unit_of_measurement", sa.String(length=50), nullable=True),
        sa.Column("price_basis", sa.String(length=20),
                  server_default="quantity", nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("weight_unit_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("unit_weight", sa.Numeric(precision=14, scale=3), nullable=True),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("requisition_date", sa.Date(), nullable=True),
        sa.Column("required_date", sa.Date(), nullable=True),
        sa.Column("requisition_type", sa.String(length=50), nullable=True),
        sa.Column("reference_number", sa.String(length=100), nullable=True),
        sa.Column("job_number", sa.String(length=100), nullable=True),
        sa.Column("mo_number", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),

        # THE BACKSTOP, NOT THE ENFORCEMENT. The rule is that the SUM of a
        # group's batch lines may not exceed what was ordered, and no CHECK can
        # express that - the quantities being summed live on rows of another
        # table, under different consignments. The server takes a row lock on
        # this row and checks the sum before writing; that is the enforcement.
        # `allocated_quantity` is that sum, denormalised onto the parent row
        # where a CHECK *can* see it, so any path that skips the server check -
        # the loaders included - still cannot over-allocate.
        sa.CheckConstraint("allocated_quantity <= ordered_quantity",
                           name="ck_allocation_within_order"),

        sa.ForeignKeyConstraint(["batch_group_id"], ["consignment_batch_groups.id"],
                                ondelete="CASCADE", name="fk_order_items_batch_group"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="SET NULL",
                                name="fk_order_items_branch"),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL",
                                name="fk_order_items_item"),
        sa.PrimaryKeyConstraint("id", name="pk_consignment_order_items"),
    )
    op.create_index("ix_consignment_order_items_batch_group_id",
                    "consignment_order_items", ["batch_group_id"])
    op.create_index("ix_consignment_order_items_is_deleted",
                    "consignment_order_items", ["is_deleted"])

    #-------------------------------------------------
    # 2. THE LINK COLUMNS - NULLABLE FOR NOW
    #
    # `consignments` holds 183 rows and `consignment_items` 455, so adding
    # either link column as NOT NULL in one statement aborts the migration:
    # every existing row would violate it the instant the column appears. They
    # go on nullable, the back-fill in step 3 fills them, and step 4 tightens
    # them to NOT NULL once no NULL is left.
    #
    # `batch_sequence` is the exception and can be NOT NULL immediately, because
    # it carries a server_default that every existing row takes: they are all
    # batch 1 of their own group.
    #-------------------------------------------------

    op.add_column("consignments", sa.Column("batch_group_id", sa.Integer(), nullable=True))
    op.add_column("consignments", sa.Column("batch_sequence", sa.Integer(),
                                            server_default=sa.text("1"), nullable=False))
    op.add_column("consignment_items", sa.Column("order_item_id", sa.Integer(), nullable=True))

    #-------------------------------------------------
    # 3. THE BACK-FILL
    #
    # Every consignment that exists becomes a group of ONE - including the
    # soft-deleted ones. Excluding those would break undo-delete: restoring a
    # consignment with no group would restore it into a state the schema says
    # cannot exist.
    #
    # `founding_consignment_id` is the consignment's OWN id, which is what makes
    # every displayed number come through this migration unchanged: a group that
    # has only ever held one batch shows no suffix, and the number it shows is
    # the id it already showed.
    #-------------------------------------------------

    shared = ", ".join(SHARED_COLUMNS)

    # created_at / updated_at are copied from the consignment rather than left
    # to now(). The group IS the order, and the order was raised when the
    # consignment was; defaulting them would date every order in the system to
    # migration day and quietly wreck any figure built on how old an order is.
    op.execute(f"""
        INSERT INTO consignment_batch_groups (
            founding_consignment_id, batches_ever,
            {shared},
            works_branch_id,
            created_by_id, is_deleted, deleted_at, deleted_by_id,
            created_at, updated_at
        )
        SELECT
            c.id, 1,
            {", ".join("c." + col for col in SHARED_COLUMNS)},
            c.branch_id,
            c.created_by_id, c.is_deleted, c.deleted_at, c.deleted_by_id,
            c.created_at, c.updated_at
        FROM consignments c
        ORDER BY c.id
    """)

    op.execute("""
        UPDATE consignments c
           SET batch_group_id = g.id
          FROM consignment_batch_groups g
         WHERE g.founding_consignment_id = c.id
    """)

    # A temporary column carries the line each order item was derived from, so
    # the lines can be pointed back at the right row in one statement. Matching
    # on anything else - insertion order, an item code, a quantity - would be a
    # guess, and a wrong guess here attaches a line to another line's order.
    # Dropped again at the end of this step.
    op.add_column("consignment_order_items",
                  sa.Column("migration_source_line_id", sa.Integer(), nullable=True))

    # ordered_quantity and allocated_quantity both take the line's quantity: the
    # whole of what was ordered went in the single batch that exists, which is
    # exactly what these rows mean today. The CHECK is satisfied by equality.
    #
    # COALESCE, because two lines (ids 451 and 460, on soft-deleted
    # consignments 179 and 182) are entirely blank - no item code, no name, no
    # quantity - and ordered_quantity is NOT NULL. A blank line orders nothing,
    # so it back-fills as 0 rather than blocking the migration. This is the one
    # place the revision writes a value the source did not hold, and it is
    # confined to two rows that hold nothing at all.
    #
    # branch_id, requisition_date and required_date come from the CONSIGNMENT,
    # not from the line: they are header columns today and per-item columns
    # afterwards, and the header value is the true one for every line under it
    # while a consignment can only have had one branch and one pair of dates.
    op.execute("""
        INSERT INTO consignment_order_items (
            batch_group_id,
            item_id, item_code, item_name, placeholder_name, specification, hs_code,
            ordered_quantity, allocated_quantity, unit_of_measurement,
            price_basis, unit_price,
            branch_id, requisition_date, required_date,
            requisition_type, reference_number, job_number, mo_number, description,
            is_deleted, deleted_at,
            created_at, updated_at,
            migration_source_line_id
        )
        SELECT
            c.batch_group_id,
            i.item_id, i.item_code, i.item_name, i.placeholder_name,
            i.specification, i.hs_code,
            COALESCE(i.quantity, 0), COALESCE(i.quantity, 0), i.unit_of_measurement,
            'quantity', i.unit_price,
            c.branch_id, c.requisition_date, c.required_date,
            i.requisition_type, i.reference_number, i.job_number, i.mo_number,
            i.description,
            i.is_deleted, i.deleted_at,
            i.created_at, i.updated_at,
            i.id
        FROM consignment_items i
        JOIN consignments c ON c.id = i.consignment_id
        ORDER BY i.id
    """)

    op.execute("""
        UPDATE consignment_items i
           SET order_item_id = o.id
          FROM consignment_order_items o
         WHERE o.migration_source_line_id = i.id
    """)

    op.drop_column("consignment_order_items", "migration_source_line_id")

    #-------------------------------------------------
    # 4. TIGHTEN THE LINKS
    #
    # After the back-fill there is no window in which a consignment has no order
    # above it or a line has no order item, so both become NOT NULL and every
    # reader downstream is spared a NULL case that can never occur.
    #-------------------------------------------------

    op.alter_column("consignments", "batch_group_id", nullable=False)
    op.alter_column("consignment_items", "order_item_id", nullable=False)

    #-------------------------------------------------
    # 5. INDEXES AND FOREIGN KEYS ON THE LINK COLUMNS
    #
    # Built after the back-fill rather than before it: an index maintained
    # through a bulk UPDATE costs more than one built once over the finished
    # column, and an FK checked per row costs more than one validated in a pass.
    #
    # Every constraint is NAMED. An unnamed one gets whatever name Postgres
    # invents, which `downgrade()` then has no way to drop.
    #-------------------------------------------------

    # NO SEPARATE INDEX ON batch_group_id ALONE. The unique index below leads
    # with that same column, so it already serves every lookup by group and the
    # foreign key check. A second index would cost a write on every consignment
    # insert and update for ever and answer nothing the first cannot.
    #
    # A sequence number is unique WITHIN its group and is never reused: delete a
    # batch and its siblings keep their numbers, leaving a gap. Renumbering
    # would make an old 177-3 become 177-2, so a number already out on an
    # invoice would resolve to a DIFFERENT shipment with both parties believing
    # they agree - worse than a number that resolves to nothing.
    op.create_index("uq_consignments_group_sequence", "consignments",
                    ["batch_group_id", "batch_sequence"], unique=True)

    # DEFERRABLE - see fk_batch_groups_founding_consignment above for why the
    # circular pair has to be, and why deferring does not weaken it.
    op.create_foreign_key("fk_consignments_batch_group", "consignments",
                          "consignment_batch_groups", ["batch_group_id"], ["id"],
                          ondelete="RESTRICT", deferrable=True, initially="DEFERRED")

    op.create_index("ix_consignment_items_order_item_id", "consignment_items",
                    ["order_item_id"])
    op.create_foreign_key("fk_consignment_items_order_item", "consignment_items",
                          "consignment_order_items", ["order_item_id"], ["id"],
                          ondelete="RESTRICT")

    #-------------------------------------------------
    # 6. THE INVARIANT: AT ARRIVED AT WORKS IMPLIES LOCKED
    #
    # THIS STATEMENT MATCHES ZERO ROWS TODAY, AND THAT IS WHY IT IS HERE.
    #
    # All 142 consignments at "Arrived at Works" - live and soft-deleted alike -
    # are already submitted and already locked, and no locked row sits at any
    # other status. The one-part and two-part closing tests agree on every row
    # in the database, so nothing changes state when the rule changes.
    #
    # That count is a snapshot, not a guarantee. Between the count and the
    # deploy an operator can move a draft to Arrived at Works, and any of the
    # four soft-deleted rows can come back through undo-delete. A statement that
    # no-ops today and catches a row that appeared last Tuesday is the cheap
    # side of that bet.
    #
    # It also states the invariant in SQL where a later reader can see it,
    # rather than leaving them to trust that it happened to hold.
    #
    # NOT UNDONE BY `downgrade()`: see the note there.
    #-------------------------------------------------

    op.execute("""
        UPDATE consignments
           SET is_locked = true
         WHERE current_status = 'Arrived at Works'
           AND NOT is_locked
    """)


def downgrade() -> None:
    """Drop what `upgrade()` added, and nothing else.

    Nothing is hand-written here and no data is copied back, because nothing was
    moved: every column this revision read still holds its own value. Dropping
    the two tables and the three link columns returns the schema exactly to
    revision 3142a00a5b31.

    Rolling this back loses any batches created since it ran. That is the
    correct behaviour for rolling back the feature that created them - and it is
    a statement about the schema, not about the business, which is what the
    feature flag is for.

    THE LOCK UPDATE IS DELIBERATELY NOT REVERSED. Un-locking rows would be
    writing data back, which is the one thing this downgrade must not do, and
    the invariant it asserts - at Arrived at Works implies locked - held before
    this revision ran and holds after it is undone. It changed zero rows on the
    way in; there is nothing to restore on the way out.
    """
    op.drop_constraint("fk_consignment_items_order_item", "consignment_items",
                       type_="foreignkey")
    op.drop_index("ix_consignment_items_order_item_id", table_name="consignment_items")
    op.drop_column("consignment_items", "order_item_id")

    op.drop_constraint("fk_consignments_batch_group", "consignments", type_="foreignkey")
    op.drop_index("uq_consignments_group_sequence", table_name="consignments")
    op.drop_column("consignments", "batch_sequence")
    op.drop_column("consignments", "batch_group_id")

    op.drop_index("ix_consignment_order_items_is_deleted",
                  table_name="consignment_order_items")
    op.drop_index("ix_consignment_order_items_batch_group_id",
                  table_name="consignment_order_items")
    op.drop_table("consignment_order_items")

    op.drop_index("ix_consignment_batch_groups_is_deleted",
                  table_name="consignment_batch_groups")
    op.drop_index("ix_consignment_batch_groups_founding_consignment_id",
                  table_name="consignment_batch_groups")
    op.drop_table("consignment_batch_groups")
