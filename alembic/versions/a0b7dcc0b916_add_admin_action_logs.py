"""add_admin_action_logs

Revision ID: a0b7dcc0b916
Revises: f138a46b20b0
Create Date: 2026-06-17 18:12:27.618372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0b7dcc0b916'
down_revision: Union[str, Sequence[str], None] = 'f138a46b20b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('admin_action_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_count', sa.Integer(), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['admin_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_admin_action_logs_action', 'admin_action_logs', ['action'])
    op.create_index('ix_admin_action_logs_admin_id', 'admin_action_logs', ['admin_id'])
    op.create_index('ix_admin_action_logs_created_at', 'admin_action_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_admin_action_logs_created_at', table_name='admin_action_logs')
    op.drop_index('ix_admin_action_logs_admin_id', table_name='admin_action_logs')
    op.drop_index('ix_admin_action_logs_action', table_name='admin_action_logs')
    op.drop_table('admin_action_logs')
