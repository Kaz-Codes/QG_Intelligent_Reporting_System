"""ports name uniqueness relaxed, used_as nullable

The dedicated ports workbook (world_trade_ports_unlocode.xlsx, ~133,000 rows)
genuinely repeats a port NAME across rows that differ only by `Type` —
Karachi appears as Sea, Air and Land, all real distinct ports the wizard's
dropdowns need to keep separate. `Port.name`'s UNIQUE constraint made that
combination unrepresentable, so it is dropped here; the loader was already
updated to rely on this (see app/loading/scripts/imports/load_04_ports.py).

`used_as` moves to nullable for the same load: `PortUsedAs.BOTH` is the
loader's default, but the column itself was never meant to be a hard
requirement — a NOT NULL here served no one once the loader always fills it.

Finds the unique constraint by querying the catalogue rather than assuming
its name, since it was declared as a bare `unique=True` on the column
(no explicit constraint name in the model) — Postgres's own default naming
for that shape is `ports_name_key`, but this does not assume it.

Revision ID: 7c0e45af8452
Revises: ec9e445ae48c
Create Date: 2026-09-18 09:06:21.160683

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c0e45af8452'
down_revision: Union[str, Sequence[str], None] = 'ec9e445ae48c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop whatever the unique constraint on ports.name is actually called —
    # found by querying the catalogue instead of assuming a name, since it
    # was never given one explicitly in the model.
    op.execute("""
        DO $$
        DECLARE
            conname text;
        BEGIN
            SELECT tc.constraint_name INTO conname
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = current_schema()
              AND tc.table_name = 'ports'
              AND tc.constraint_type = 'UNIQUE'
              AND kcu.column_name = 'name';

            IF conname IS NOT NULL THEN
                EXECUTE format('ALTER TABLE ports DROP CONSTRAINT %I', conname);
            END IF;
        END $$;
    """)
    op.alter_column('ports', 'used_as', existing_type=sa.String(length=20), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Fails loudly (rather than silently deleting rows) if the data now holds
    # duplicate names or a NULL used_as — both are expected once ports has
    # been loaded from the dedicated workbook, and a downgrade that quietly
    # dropped rows to make the constraint fit would be far worse than one
    # that just refuses to run.
    op.alter_column('ports', 'used_as', existing_type=sa.String(length=20), nullable=False)
    op.create_unique_constraint('ports_name_key', 'ports', ['name'])
