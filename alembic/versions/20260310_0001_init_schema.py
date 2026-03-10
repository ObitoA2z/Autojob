"""init schema

Revision ID: 20260310_0001
Revises:
Create Date: 2026-03-10 15:50:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260310_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("brand", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("campaign_url", sa.String(length=1024), nullable=False),
        sa.Column("budget", sa.Float(), nullable=True),
        sa.Column("niche", sa.String(length=128), nullable=True),
        sa.Column("target_platform", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("campaign_url", name="uq_campaigns_campaign_url"),
    )
    op.create_index("ix_campaigns_platform", "campaigns", ["platform"])
    op.create_index("ix_campaigns_external_id", "campaigns", ["external_id"])
    op.create_index("ix_campaigns_niche", "campaigns", ["niche"])
    op.create_index("ix_campaigns_target_platform", "campaigns", ["target_platform"])
    op.create_index("ix_campaigns_status", "campaigns", ["status"])

    op.create_table(
        "creator_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("niche", sa.String(length=128), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("audience_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("platforms", sa.String(length=256), nullable=False, server_default="tiktok,instagram"),
        sa.Column("min_budget", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("auto_apply", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("email", name="uq_creator_profiles_email"),
    )

    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"])

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.Integer(), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("generated_message", sa.Text(), nullable=True),
        sa.Column("response_message", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_applications_campaign_id", "applications", ["campaign_id"])
    op.create_index("ix_applications_platform", "applications", ["platform"])
    op.create_index("ix_applications_status", "applications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_applications_status", table_name="applications")
    op.drop_index("ix_applications_platform", table_name="applications")
    op.drop_index("ix_applications_campaign_id", table_name="applications")
    op.drop_table("applications")

    op.drop_index("ix_scan_runs_status", table_name="scan_runs")
    op.drop_table("scan_runs")

    op.drop_table("creator_profiles")

    op.drop_index("ix_campaigns_status", table_name="campaigns")
    op.drop_index("ix_campaigns_target_platform", table_name="campaigns")
    op.drop_index("ix_campaigns_niche", table_name="campaigns")
    op.drop_index("ix_campaigns_external_id", table_name="campaigns")
    op.drop_index("ix_campaigns_platform", table_name="campaigns")
    op.drop_table("campaigns")
