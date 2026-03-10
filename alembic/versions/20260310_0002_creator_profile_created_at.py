"""creator profile timestamps

Revision ID: 20260310_0002
Revises: 20260310_0001
Create Date: 2026-03-10 16:45:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260310_0002"
down_revision = "20260310_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        default_expr = sa.text("NOW()")
    elif dialect == "sqlite":
        default_expr = sa.text("(datetime('now'))")
    else:
        default_expr = sa.text("CURRENT_TIMESTAMP")

    op.add_column(
        "creator_profiles",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=default_expr),
    )
    op.create_index("ix_creator_profiles_updated_at", "creator_profiles", ["updated_at"])

    if dialect != "sqlite":
        op.alter_column("creator_profiles", "created_at", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_creator_profiles_updated_at", table_name="creator_profiles")
    op.drop_column("creator_profiles", "created_at")
