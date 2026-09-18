"""logistics mill total_packages customer_note budgeted_packing_cost columns

Four new columns for the logistics wizard's Step 1 fields: none of them
exist in the source workbook (confirmed by reading the actual sheet headers
in app/loading/data/logistics/Logistics Data (1).xlsx — see the
conversation this revision came out of), so this is a plain additive change
with no backfill. All four are nullable with no server-side default, so an
existing order simply reads NULL until someone fills them in through the app.

Revision ID: ec9e445ae48c
Revises: b4d18e05c7a2
Create Date: 2026-09-18 09:00:05.405652

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ec9e445ae48c'
down_revision: Union[str, Sequence[str], None] = 'b4d18e05c7a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('logistics_consignments', sa.Column('mill', sa.String(length=500), nullable=True))
    op.add_column('logistics_consignments', sa.Column('total_packages', sa.Integer(), nullable=True))
    op.add_column('logistics_consignments', sa.Column('customer_note', sa.String(length=1000), nullable=True))
    op.add_column('logistics_items', sa.Column('budgeted_packing_cost', sa.Numeric(precision=14, scale=3), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('logistics_items', 'budgeted_packing_cost')
    op.drop_column('logistics_consignments', 'customer_note')
    op.drop_column('logistics_consignments', 'total_packages')
    op.drop_column('logistics_consignments', 'mill')
