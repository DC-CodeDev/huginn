"""remove_timezone_from_datetime_columns

SQLite no implementa DateTime(timezone=True) — los valores aware se
leen de vuelta como naive.  Se elimina timezone=True de todas las
columnas datetime del proyecto y se adopta la convención de trabajar
con datetimes naive que representan siempre UTC.

Revision ID: 1f621998aecf
Revises: e847afe87df5
Create Date: 2026-07-07 09:41:20.000425

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f621998aecf'
down_revision: Union[str, Sequence[str], None] = 'e847afe87df5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove timezone=True from all DateTime columns."""
    # En SQLite esta migración es un no-op porque el dialecto no
    # distingue DateTime(timezone=True) de DateTime simple.
    # Se incluye batch_alter_table para compatibilidad con motores
    # que sí respetan el modificador (PostgreSQL, etc.).
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("created_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))
        batch_op.alter_column("updated_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("expires_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))
        batch_op.alter_column("created_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))

    with op.batch_alter_table("studios") as batch_op:
        batch_op.alter_column("created_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))

    with op.batch_alter_table("boards") as batch_op:
        batch_op.alter_column("created_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))
        batch_op.alter_column("updated_at", type_=sa.DateTime(), existing_type=sa.DateTime(timezone=True))


def downgrade() -> None:
    """Restore timezone=True on all DateTime columns."""
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("created_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())
        batch_op.alter_column("updated_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())

    with op.batch_alter_table("sessions") as batch_op:
        batch_op.alter_column("expires_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())
        batch_op.alter_column("created_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())

    with op.batch_alter_table("studios") as batch_op:
        batch_op.alter_column("created_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())

    with op.batch_alter_table("boards") as batch_op:
        batch_op.alter_column("created_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())
        batch_op.alter_column("updated_at", type_=sa.DateTime(timezone=True), existing_type=sa.DateTime())
