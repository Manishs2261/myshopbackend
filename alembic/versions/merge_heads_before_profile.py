"""Merge heads before adding user profile fields

Revision ID: merge_heads_before_profile
Revises: add_sponsored_to_products, add_website_settings
Create Date: 2026-05-16 00:00:00.000000

"""
from alembic import op

revision = 'merge_heads_before_profile'
down_revision = ('add_sponsored_to_products', 'add_website_settings')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
