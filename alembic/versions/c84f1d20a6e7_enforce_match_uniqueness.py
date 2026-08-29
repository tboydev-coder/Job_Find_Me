"""enforce match uniqueness and track successful notifications

Revision ID: c84f1d20a6e7
Revises: b7630ec21456
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c84f1d20a6e7"
down_revision: Union[str, Sequence[str], None] = "b7630ec21456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Preserve one match per profile/job before enforcing uniqueness."""
    op.add_column(
        "job_matches",
        sa.Column("notified_at", sa.DateTime(), nullable=True),
    )

    # Preserve notification history when older application versions inserted
    # the same profile/job more than once. PostgreSQL is the supported store.
    op.execute(
        """
        UPDATE job_matches AS kept
        SET notified = summary.was_notified,
            notified_at = summary.notified_at
        FROM (
            SELECT profile_id,
                   job_id,
                   BOOL_OR(notified) AS was_notified,
                   MAX(CASE WHEN notified THEN created_at END) AS notified_at,
                   MAX(id) AS keep_id
            FROM job_matches
            GROUP BY profile_id, job_id
        ) AS summary
        WHERE kept.id = summary.keep_id
        """
    )
    op.execute(
        """
        DELETE FROM job_matches AS duplicate
        USING (
            SELECT profile_id, job_id, MAX(id) AS keep_id
            FROM job_matches
            GROUP BY profile_id, job_id
        ) AS summary
        WHERE duplicate.profile_id = summary.profile_id
          AND duplicate.job_id = summary.job_id
          AND duplicate.id <> summary.keep_id
        """
    )

    op.create_unique_constraint(
        "uq_job_matches_profile_job",
        "job_matches",
        ["profile_id", "job_id"],
    )
    op.create_index(
        "ix_job_matches_notified_at",
        "job_matches",
        ["notified_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_matches_notified_at",
        table_name="job_matches",
    )
    op.drop_constraint(
        "uq_job_matches_profile_job",
        "job_matches",
        type_="unique",
    )
    op.drop_column("job_matches", "notified_at")
