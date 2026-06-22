"""add announcement reactions

Revision ID: 80d8addfb9ff
Revises: b9f99a573f9c
Create Date: 2026-06-19 19:06:38.946849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '80d8addfb9ff'
down_revision: Union[str, Sequence[str], None] = 'b9f99a573f9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('announcement_reactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('announcement_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('reaction', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
    sa.ForeignKeyConstraint(['announcement_id'], ['announcements.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('announcement_id', 'user_id', 'reaction', name='uq_announcement_reaction_user')
    )
    op.create_index(op.f('ix_announcement_reactions_announcement_id'), 'announcement_reactions', ['announcement_id'], unique=False)
    op.create_index(op.f('ix_announcement_reactions_user_id'), 'announcement_reactions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_announcement_reactions_user_id'), table_name='announcement_reactions')
    op.drop_index(op.f('ix_announcement_reactions_announcement_id'), table_name='announcement_reactions')
    op.drop_table('announcement_reactions')
