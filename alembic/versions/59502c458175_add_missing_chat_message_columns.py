"""add missing chat message columns

Revision ID: 59502c458175
Revises: 641801764e9c
Create Date: 2026-06-22 17:13:02.369161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59502c458175'
down_revision: Union[str, Sequence[str], None] = '641801764e9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    rows = conn.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    """Upgrade schema."""
    # SQLite-friendly: use batch_alter_table to add columns and foreign key.
    with op.batch_alter_table('chat_messages', schema=None, recreate='always') as batch_op:
        if not _column_exists('chat_messages', 'attachment_url'):
            batch_op.add_column(sa.Column('attachment_url', sa.String(), nullable=True))
        if not _column_exists('chat_messages', 'reply_to_id'):
            batch_op.add_column(sa.Column('reply_to_id', sa.Integer(), nullable=True))
        if not _column_exists('chat_messages', 'deleted_for'):
            batch_op.add_column(sa.Column('deleted_for', sa.Text(), nullable=True))
        if not _column_exists('chat_messages', 'payload'):
            batch_op.add_column(sa.Column('payload', sa.JSON(), nullable=True))
        # SQLite needs the FK inside batch_alter_table as well.
        batch_op.create_foreign_key(
            'fk_chat_messages_reply_to_id',
            'chat_messages',
            ['reply_to_id'],
            ['id']
        )

    # Relax login_logs.created_at to nullable to match the model.
    with op.batch_alter_table('login_logs', schema=None, recreate='always') as batch_op:
        batch_op.alter_column(
            'created_at',
            existing_type=sa.DATETIME(),
            nullable=True,
            existing_server_default=sa.text('(CURRENT_TIMESTAMP)')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('login_logs', schema=None, recreate='always') as batch_op:
        batch_op.alter_column(
            'created_at',
            existing_type=sa.DATETIME(),
            nullable=False,
            existing_server_default=sa.text('(CURRENT_TIMESTAMP)')
        )

    with op.batch_alter_table('chat_messages', schema=None, recreate='always') as batch_op:
        batch_op.drop_constraint('fk_chat_messages_reply_to_id', type_='foreignkey')
        batch_op.drop_column('payload')
        batch_op.drop_column('deleted_for')
        batch_op.drop_column('reply_to_id')
        batch_op.drop_column('attachment_url')
