"""Add Gemini video preparation state."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "videos",
        sa.Column("ai_status", sa.String(12), nullable=False, server_default="FAILED"),
    )
    op.add_column("videos", sa.Column("gemini_file_name", sa.String(255), nullable=True))
    op.add_column("videos", sa.Column("gemini_file_uri", sa.Text(), nullable=True))
    op.add_column(
        "videos", sa.Column("gemini_file_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("videos", sa.Column("ai_error", sa.Text(), nullable=True))
    op.add_column(
        "videos",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_check_constraint(
        "video_ai_status", "videos", "ai_status IN ('PROCESSING', 'READY', 'FAILED')"
    )
    op.execute(
        "UPDATE videos SET ai_error = "
        "'This video has not been prepared for AI review. Retry preparation.'"
    )
    op.alter_column("videos", "ai_status", server_default="PROCESSING")


def downgrade():
    op.drop_constraint("video_ai_status", "videos", type_="check")
    op.drop_column("videos", "updated_at")
    op.drop_column("videos", "ai_error")
    op.drop_column("videos", "gemini_file_expires_at")
    op.drop_column("videos", "gemini_file_uri")
    op.drop_column("videos", "gemini_file_name")
    op.drop_column("videos", "ai_status")
