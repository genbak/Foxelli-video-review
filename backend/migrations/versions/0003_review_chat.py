"""Add persistent review conversation and AI comments."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("comment_author", "comments", type_="check")
    op.create_check_constraint(
        "comment_author", "comments", "author IN ('HUMAN', 'AI')"
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "video_id",
            sa.Uuid(),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("role IN ('USER', 'ASSISTANT')", name="message_role"),
        sa.CheckConstraint(
            "char_length(trim(text)) BETWEEN 1 AND 8000", name="message_text_length"
        ),
    )
    op.create_index("ix_messages_video_id", "messages", ["video_id", "id"])


def downgrade():
    op.drop_table("messages")
    op.execute("DELETE FROM comments WHERE author = 'AI'")
    op.drop_constraint("comment_author", "comments", type_="check")
    op.create_check_constraint("comment_author", "comments", "author = 'HUMAN'")
