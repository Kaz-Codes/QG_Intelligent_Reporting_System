"""allocation quantity lower bounds

Adds `ordered_quantity >= 0` and `allocated_quantity >= 0` to
`consignment_order_items`.

WHY THE UPPER BOUND ALONE IS NOT AN INVARIANT

    `ck_allocation_within_order` (revision a1c4f27b93de) says
    `allocated_quantity <= ordered_quantity`, and `allocated_quantity` is a
    SUM - the total of every live line on every live batch of one order.

    A sum containing a negative term can satisfy that check while the
    quantities it is made of do not. Order 250 units; batch 1 takes 400 and
    batch 2 takes -150; the sum is 250, the CHECK passes, and 400 units have
    been committed against an order for 250. Over-allocation becomes
    arithmetically invisible - which is the one failure the whole invariant
    exists to prevent.

    `ordered_quantity >= 0` closes the mirror of it. A negative order makes
    every allocation an over-allocation, or - paired with a negative
    allocation - makes nothing one.

WHY IT IS NOT COVERED BY THE PYDANTIC SCHEMA ALREADY

    `ConsignmentItemSchema.quantity` is `gt=0`, but that constrains a REQUEST
    BODY. Neither of these two columns is written from one: both are written by
    `helpers.reconcile_allocation` from a SQL aggregate, and the loaders write
    them through raw psycopg2 with no schema in the path at all. A rule that
    only the request layer enforces is not enforced on the paths that have
    historically broken these columns.

SAFE ON EXISTING DATA - CHECKED, NOT ASSUMED

    Verified against a clone of production before writing this file: 455 of 455
    order items have `ordered_quantity >= 0` and `allocated_quantity >= 0`, and
    the minimum of each is 0. So both constraints validate immediately and
    neither needs NOT VALID.

    The two rows at `ordered_quantity = 0` are section 4.3's COALESCE rows -
    sheet lines that carried no quantity. They satisfy `>= 0` and are left
    exactly as they are; allocating against them is refused at the server with
    a message naming the fix (`helpers.OrderLineHasNoQuantity`), because a line
    that ordered nothing is a line waiting to be corrected rather than an order
    of zero.

Revision ID: c7b210d4e9f3
Revises: d5e81b6a2c07
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c7b210d4e9f3"
down_revision: Union[str, Sequence[str], None] = "d5e81b6a2c07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORDERED = "ck_order_item_ordered_quantity_non_negative"
ALLOCATED = "ck_order_item_allocated_quantity_non_negative"


def upgrade() -> None:
    op.create_check_constraint(
        ORDERED, "consignment_order_items", "ordered_quantity >= 0"
    )
    op.create_check_constraint(
        ALLOCATED, "consignment_order_items", "allocated_quantity >= 0"
    )


def downgrade() -> None:
    # Genuinely reversible: this revision adds two constraints and changes no
    # data, so dropping them restores the previous schema exactly.
    op.drop_constraint(ALLOCATED, "consignment_order_items", type_="check")
    op.drop_constraint(ORDERED, "consignment_order_items", type_="check")
