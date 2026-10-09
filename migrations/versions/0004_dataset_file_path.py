"""Track the provider-relative file selected for a dataset version."""

from alembic import op
import sqlalchemy as sa

revision = "0004_dataset_file_path"
down_revision = "0003_model_version_artifacts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_versions",
        sa.Column("file_path", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dataset_versions", "file_path")