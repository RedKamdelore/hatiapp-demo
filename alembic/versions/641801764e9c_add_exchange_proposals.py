"""add exchange proposals

Revision ID: 641801764e9c
Revises: 80d8addfb9ff
Create Date: 2026-06-22 13:49:29.142054

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '641801764e9c'
down_revision: Union[str, Sequence[str], None] = '80d8addfb9ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('exchange_proposals',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sender_id', sa.Integer(), nullable=False),
    sa.Column('receiver_id', sa.Integer(), nullable=False),
    sa.Column('sender_booking_id', sa.Integer(), nullable=False),
    sa.Column('receiver_booking_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('resolved_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['receiver_booking_id'], ['bookings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['receiver_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['sender_booking_id'], ['bookings.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('sender_id', 'receiver_id', 'status', name='uq_exchange_sender_receiver_status')
    )
    op.create_index(op.f('ix_exchange_proposals_receiver_booking_id'), 'exchange_proposals', ['receiver_booking_id'], unique=False)
    op.create_index(op.f('ix_exchange_proposals_receiver_id'), 'exchange_proposals', ['receiver_id'], unique=False)
    op.create_index(op.f('ix_exchange_proposals_sender_booking_id'), 'exchange_proposals', ['sender_booking_id'], unique=False)
    op.create_index(op.f('ix_exchange_proposals_sender_id'), 'exchange_proposals', ['sender_id'], unique=False)
    op.add_column('chat_messages', sa.Column('payload', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chat_messages', 'payload')
    op.drop_index(op.f('ix_exchange_proposals_sender_id'), table_name='exchange_proposals')
    op.drop_index(op.f('ix_exchange_proposals_sender_booking_id'), table_name='exchange_proposals')
    op.drop_index(op.f('ix_exchange_proposals_receiver_id'), table_name='exchange_proposals')
    op.drop_index(op.f('ix_exchange_proposals_receiver_booking_id'), table_name='exchange_proposals')
    op.drop_constraint('uq_exchange_sender_receiver_status', 'exchange_proposals', type_='unique')
    op.drop_table('exchange_proposals')
