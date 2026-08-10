"""audio: add chunk time columns

Revision ID: 748dc15bf7dc
Revises: 1b7bd667b24c
Create Date: 2026-08-09 14:41:03.864575+00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '748dc15bf7dc'
down_revision: str | None = '1b7bd667b24c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('chunks', sa.Column('start_seconds', sa.Float(), nullable=True))
    op.add_column('chunks', sa.Column('end_seconds', sa.Float(), nullable=True))
    op.alter_column('chunks', 'page_start',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.alter_column('chunks', 'page_end',
               existing_type=sa.INTEGER(),
               nullable=True)
    # NOTE: ix_chunks_embedding_hnsw is intentionally NOT dropped here.
    # The index is created in the original 'add chunks' migration and the
    # Chunk model no longer declares it inline, so autogenerate thinks
    # it was removed. The index stays.


def downgrade() -> None:
    op.drop_column('chunks', 'end_seconds')
    op.drop_column('chunks', 'start_seconds')
    op.alter_column('chunks', 'page_start',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.alter_column('chunks', 'page_end',
               existing_type=sa.INTEGER(),
               nullable=False)
    # NOTE: ix_chunks_embedding_hnsw is not recreated here either.
