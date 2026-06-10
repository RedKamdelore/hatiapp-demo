"""direction_multi_leaders

Revision ID: 68bb4f72a251
Revises: 0fd42d4992d2
Create Date: 2026-05-27 17:44:19.174498

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68bb4f72a251'
down_revision: Union[str, Sequence[str], None] = '0fd42d4992d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Создать таблицу связи
    op.create_table('direction_leaders',
        sa.Column('direction_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['direction_id'], ['directions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('direction_id', 'user_id')
    )

    # 2. Перенести существующих руководителей
    op.execute("""
        INSERT INTO direction_leaders (direction_id, user_id)
        SELECT id, leader_id FROM directions WHERE leader_id IS NOT NULL
    """)

    # 3. Удалить колонку leader_id (SQLite — через batch_alter_table)
    with op.batch_alter_table('directions') as batch_op:
        batch_op.drop_column('leader_id')


def downgrade() -> None:
    """Downgrade schema."""
    # 1. Добавить колонку leader_id обратно
    with op.batch_alter_table('directions') as batch_op:
        batch_op.add_column(sa.Column('leader_id', sa.Integer(), nullable=True))

    # 2. Восстановить первого руководителя
    op.execute("""
        UPDATE directions
        SET leader_id = (
            SELECT user_id FROM direction_leaders
            WHERE direction_leaders.direction_id = directions.id
            LIMIT 1
        )
    """)

    # 3. Удалить таблицу связи
    op.drop_table('direction_leaders')
