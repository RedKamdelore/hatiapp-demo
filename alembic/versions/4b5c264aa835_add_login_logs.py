"""add_login_logs

Revision ID: 4b5c264aa835
Revises: 68bb4f72a251
Create Date: 2026-05-28 00:23:17.633952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b5c264aa835'
down_revision: Union[str, Sequence[str], None] = '68bb4f72a251'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('login_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('mac_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('device_type', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_login_logs_user_id', 'login_logs', ['user_id'])
    op.create_index('ix_login_logs_created_at', 'login_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_login_logs_created_at', table_name='login_logs')
    op.drop_index('ix_login_logs_user_id', table_name='login_logs')
    op.drop_table('login_logs')
