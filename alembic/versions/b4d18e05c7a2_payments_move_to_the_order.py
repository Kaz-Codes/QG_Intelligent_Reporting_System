"""payments move from the batch to the ORDER

Revision ID: b4d18e05c7a2
Revises: f3a91c60d28b
Create Date: 2026-09-15

WHY
===

`payments.consignment_id` pointed at what is now a BATCH row, while the
requirements put payments once per consignment, on batch 1 (requirements, Step
4). As it stood, two batches of one LC could each carry a full payment history
and nothing would object — design section 4.4.

**THIS IS NOT A ONE-ROW MIGRATION, whatever the row count says.** Section 4.4
records that revision 2 of the design used "there is a single payment record in
the entire database" to argue the change was cheap, and withdraws that framing:
the count is low because staff have not started using the screen, not because
the screen is dead. The orphan check below is written as though the table were
full, for that reason.

EXPAND AND CONTRACT
===================

Add nullable -> back-fill -> SET NOT NULL, and **leave `consignment_id` in
place**. It is still NOT NULL, so every insert after this migration must
populate it - see `Payment.consignment_id` in models.py for what the
application now writes there and why.

**REVISION B OWES ONE MORE COLUMN AFTER THIS: `payments.consignment_id`.** It
joins the orphaned `consignments` and `consignment_items` columns from
revision A. Nothing in the ORM maps it any more (the `Consignment.payments`
relationship is removed in the same change, deliberately - a relationship that
works today and is scheduled for deletion is exactly what makes Revision B
dangerous), so the only writer is the explicit default in the create path.

THE ORPHAN CHECK
================

`SET NOT NULL` on a back-filled column fails as a bare constraint violation
naming no row. Two populations would produce that, and both are silent:

  * a payment whose consignment has a NULL `batch_group_id` - impossible since
    revision A made that column NOT NULL, checked anyway because the cost is
    one query and the failure mode is a migration that stops half way;
  * a payment whose consignment row has since been soft-deleted. The FK is
    `ON DELETE CASCADE` so a hard delete would have taken the payment with it,
    but a soft-deleted consignment keeps its payments and they still need an
    order to hang from.

The second is not an error - a soft-deleted batch still belongs to its order,
so its payments back-fill normally. It is REPORTED rather than refused, so a
migration that moves more rows than anybody expected says so out loud.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4d18e05c7a2"
down_revision: Union[str, Sequence[str], None] = "f3a91c60d28b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    op.add_column(
        "payments",
        sa.Column("batch_group_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_payments_batch_group_id",
        "payments", "consignment_batch_groups",
        ["batch_group_id"], ["id"],
    )

    total = conn.execute(sa.text("SELECT count(*) FROM payments")).scalar()
    soft_deleted = conn.execute(sa.text("""
        SELECT count(*) FROM payments p
          JOIN consignments c ON c.id = p.consignment_id
         WHERE c.is_deleted = true
    """)).scalar()

    conn.execute(sa.text("""
        UPDATE payments p
           SET batch_group_id = c.batch_group_id
          FROM consignments c
         WHERE c.id = p.consignment_id
    """))

    # WHAT COULD NOT BE GIVEN AN ORDER. Counted BEFORE the constraint, so the
    # failure names the rows instead of being a bare NotNullViolation.
    orphans = conn.execute(sa.text(
        "SELECT id, consignment_id FROM payments WHERE batch_group_id IS NULL"
    )).all()

    print(f"  payments: {total} rows, {soft_deleted} on soft-deleted batches "
          f"(back-filled normally - a deleted batch still belongs to its order)")

    if orphans:
        raise RuntimeError(
            f"{len(orphans)} payment(s) could not be given an order and the "
            f"column cannot be made NOT NULL: "
            f"{[{'payment': pid, 'consignment': cid} for pid, cid in orphans[:20]]}"
            f"{' …' if len(orphans) > 20 else ''}. Each names a payment whose "
            f"consignment is missing or has no batch_group_id. Fix the data, "
            f"then re-run - nothing has been dropped."
        )

    op.alter_column("payments", "batch_group_id", nullable=False)
    print(f"  payments: {total} rows now hang off the order")


def downgrade() -> None:
    """Honestly reversible, unlike the origin normalisation.

    Nothing was lost on the way up: `consignment_id` is still populated on
    every row, so dropping the new column restores the previous shape exactly.
    """
    op.drop_constraint("fk_payments_batch_group_id", "payments", type_="foreignkey")
    op.drop_column("payments", "batch_group_id")
