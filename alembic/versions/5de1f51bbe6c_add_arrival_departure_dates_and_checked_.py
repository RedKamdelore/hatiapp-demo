"""add arrival_departure_dates and checked_in

Revision ID: 5de1f51bbe6c
Revises: 4b5c264aa835
Create Date: 2026-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5de1f51bbe6c'
down_revision = '4b5c264aa835'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('arrival_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('departure_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('checked_in', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('checked_in')
        batch_op.drop_column('departure_date')
        batch_op.drop_column('arrival_date')
