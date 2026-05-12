"""Add is_sponsored and sponsor_request_status to products

Revision ID: add_sponsored_to_products
Revises: add_website_settings
Create Date: 2026-05-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_sponsored_to_products'
down_revision = 'add_product_discount_percentage'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('is_sponsored', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('products', sa.Column('sponsor_request_status', sa.String(length=20), nullable=True, server_default='none'))


def downgrade():
    op.drop_column('products', 'sponsor_request_status')
    op.drop_column('products', 'is_sponsored')
