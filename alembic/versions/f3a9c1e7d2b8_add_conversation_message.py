"""add conversation_message

Revision ID: f3a9c1e7d2b8
Revises: edc35f8cbf65
Create Date: 2026-11-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a9c1e7d2b8'
down_revision: Union[str, Sequence[str], None] = 'edc35f8cbf65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('conversation_message',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
    sa.Column('message_id', sa.String(length=64), nullable=False),
    sa.Column('conversation_id', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.String(length=64), nullable=True),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('sources', sa.JSON(), nullable=True),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('message_id')
    )
    op.create_index('ix_conversation_message_conv', 'conversation_message', ['conversation_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_conversation_message_conv', table_name='conversation_message')
    op.drop_table('conversation_message')
