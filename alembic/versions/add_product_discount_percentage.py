"""Add discount_percentage to products table

Revision ID: add_product_discount_percentage
Revises: add_gallery_field
Create Date: 2026-04-23 15:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "add_product_discount_percentage"
down_revision = "add_gallery_field"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("discount_percentage", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("products", "discount_percentage")
