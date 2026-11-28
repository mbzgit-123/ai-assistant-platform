"""add practice_session session_type

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-11-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('practice_session', sa.Column('session_type', sa.String(length=16), nullable=True))
    # 存量数据统一视为普通练习，保证历史记录可被「练习记录」页过滤到
    op.execute("UPDATE practice_session SET session_type = 'practice' WHERE session_type IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('practice_session', 'session_type')
