"""addenda - amendments to the LC, on the ORDER

Revision ID: a7c2e94f5b31
Revises: b4d18e05c7a2
Create Date: 2026-09-17

WHY
===

Requirements, Step 4: *"Addenda - rather than fixed '1st addendum' and '2nd
addendum' sections, an 'Add addendum' button so any number can be added"*. The
count is open, so this is a child table rather than two more columns on the
order.

ON THE GROUP, like payments since `b4d18e05c7a2` and for the same reason: an LC
is amended once, not once per arrival. A batch-level addenda table would let two
arrivals of one LC each carry a different amendment history.

`value` IS A SIGNED DELTA, NOT A REVISED TOTAL
==============================================

An increase is positive, a reduction negative, and the current LC value is the
original plus the sum of the live rows. The reasoning is in `models.py` beside
the column, where somebody reading `value` will actually be - repeated here only
because a migration is where the column first appears: a revised-total column
would make the current figure depend on which row is newest, and soft-deleting a
middle row would then be silently wrong.

NOTHING SUMS IT YET
===================

This revision creates the table and nothing reads it into any figure. Addenda
are stored and displayed; wiring them into the LC value changes a number that is
already on screen and in printed sheets (CLAUDE.md rule 4), which is a change of
its own with its own drive against the export and the dashboards.
`tests/test_addenda.py::TestNothingIsWiredIntoTheArithmetic` is what holds that
line, and it is meant to be deleted deliberately when the wiring is built.

AND ONE INDEX THAT PART 1 DECLARED BUT NEVER CREATED
====================================================

`Payment.batch_group_id` is `index=True` in the model, but `b4d18e05c7a2` added
the column with `op.add_column` - which does not honour that flag - and never
issued the `CREATE INDEX`. So the model and every deployed database disagree,
and the FK that EVERY payment read filters on has no index behind it.

Found by `alembic check` while verifying this revision, not by a slow query:
the table is small enough today that nothing is visibly wrong, which is exactly
how it would have stayed until it was not. Created here rather than by editing
`b4d18e05c7a2`, which has already run on the server. `IF NOT EXISTS`, so a
database that somehow has it is not a failed migration.

PURELY ADDITIVE, so `downgrade()` drops what it added and nothing else - no
data-copying reversal to write and no untested path, the same property that made
Revision A cleanly reversible (section 4.6).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c2e94f5b31"
down_revision: Union[str, Sequence[str], None] = "b4d18e05c7a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_addenda",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_group_id", sa.Integer(), nullable=False),
        sa.Column("addendum_date", sa.Date(), nullable=True),
        sa.Column("reference", sa.String(length=100), nullable=True),
        # SIGNED. No CHECK constraint bounding it below - a reduction is
        # negative and a `value >= 0` here would reject exactly the case the
        # delta design exists to support.
        sa.Column("value", sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("bank_charges", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["batch_group_id"], ["consignment_batch_groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Every list of addenda is "this order's, not deleted", so both columns are
    # indexed - matching `payments`, which indexes the same pair.
    op.create_index("ix_payment_addenda_batch_group_id", "payment_addenda",
                    ["batch_group_id"])
    op.create_index("ix_payment_addenda_is_deleted", "payment_addenda",
                    ["is_deleted"])

    # PART 1's MISSING INDEX - see the header. `Payment.batch_group_id` has
    # said `index=True` since `b4d18e05c7a2` and no database has ever had the
    # index.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_payments_batch_group_id "
        "ON payments (batch_group_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_payments_batch_group_id")
    op.drop_index("ix_payment_addenda_is_deleted", table_name="payment_addenda")
    op.drop_index("ix_payment_addenda_batch_group_id", table_name="payment_addenda")
    op.drop_table("payment_addenda")
