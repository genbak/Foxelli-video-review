"""Local videos and human comments only."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(64), nullable=False, unique=True),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("brand_context", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("duration_ms > 0", name="video_positive_duration"),
        sa.CheckConstraint("byte_size > 0", name="video_positive_size"),
        sa.CheckConstraint("brand_context IN ('NONE', 'MRQ')", name="video_context"),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("video_id", sa.Uuid(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("author", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("timestamp_ms >= 0", name="comment_nonnegative_time"),
        sa.CheckConstraint("char_length(trim(text)) BETWEEN 1 AND 1000", name="comment_text_length"),
        sa.CheckConstraint("author = 'HUMAN'", name="comment_author"),
    )
    op.create_index("ix_comments_video_time", "comments", ["video_id", "timestamp_ms"])


def downgrade():
    op.drop_table("comments")
    op.drop_table("videos")
