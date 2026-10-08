"""add durable search events

Revision ID: f81ef2e38717
Revises: 1f28dd80f951
Create Date: 2026-10-08 17:03:35.579534

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f81ef2e38717'
down_revision: Union[str, Sequence[str], None] = '1f28dd80f951'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # The composite primary key creates the ordered replay B-tree index.
    op.create_table('search_events',
    sa.Column('search_id', sa.UUID(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=32), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['search_id'], ['search_tasks.search_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('search_id', 'sequence')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('search_events')
