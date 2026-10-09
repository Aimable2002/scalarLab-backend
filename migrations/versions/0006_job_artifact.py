"""Associate each job with its output artifact."""

from alembic import op
import sqlalchemy as sa

revision = "0006_job_artifact"
down_revision = "0005_experiment_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("artifact_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_artifact_id_artifacts",
        "jobs",
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.alter_column("jobs", "artifact_id", nullable=False)


def downgrade() -> None:
    op.drop_constraint("fk_jobs_artifact_id_artifacts", "jobs", type_="foreignkey")
    op.drop_column("jobs", "artifact_id")