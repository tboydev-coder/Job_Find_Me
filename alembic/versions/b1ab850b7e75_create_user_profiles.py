"""create user profiles

Revision ID: b1ab850b7e75
Revises: 
Create Date: 2026-08-18 16:12:10.838984

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1ab850b7e75'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=True),
        sa.Column("target_titles", sa.Text(), nullable=True),
        sa.Column("locations", sa.Text(), nullable=True),
        sa.Column(
            "minimum_match",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("75"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("user_profiles")
