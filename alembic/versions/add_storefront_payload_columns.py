"""Add storefront draft/published payload columns

Revision ID: add_storefront_payload_columns
Revises: add_marketplace_settings
Create Date: 2026-04-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_storefront_payload_columns"
down_revision = "add_marketplace_settings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("marketplace_settings", sa.Column("storefront_draft", sa.JSON(), nullable=True))
    op.add_column("marketplace_settings", sa.Column("storefront_published", sa.JSON(), nullable=True))
    op.add_column("marketplace_settings", sa.Column("storefront_status", sa.String(), nullable=True))
    op.add_column("marketplace_settings", sa.Column("published_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("marketplace_settings", "published_at")
    op.drop_column("marketplace_settings", "storefront_status")
    op.drop_column("marketplace_settings", "storefront_published")
    op.drop_column("marketplace_settings", "storefront_draft")
