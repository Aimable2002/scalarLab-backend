"""Link model versions to durable artifacts."""

from alembic import op
import sqlalchemy as sa

revision = "0003_model_version_artifacts"
down_revision = "0002_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_versions",
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_model_versions_artifact_id_artifacts",
        "model_versions",
        "artifacts",
        ["artifact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_model_versions_artifact_id", "model_versions", ["artifact_id"])


def downgrade() -> None:
    op.drop_constraint("uq_model_versions_artifact_id", "model_versions", type_="unique")
    op.drop_constraint(
        "fk_model_versions_artifact_id_artifacts", "model_versions", type_="foreignkey"
    )
    op.drop_column("model_versions", "artifact_id")