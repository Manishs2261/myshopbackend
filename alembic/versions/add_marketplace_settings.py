"""Add marketplace settings table

Revision ID: add_marketplace_settings
Revises: add_gallery_field
Create Date: 2026-04-23 23:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_marketplace_settings'
down_revision = 'add_gallery_field'
branch_labels = None
depends_on = None


def upgrade():
    # Create the marketplace_settings table
    op.create_table(
        'marketplace_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('theme', sa.String(), nullable=True),
        sa.Column('primary_color', sa.String(), nullable=True),
        sa.Column('secondary_color', sa.String(), nullable=True),
        sa.Column('background_color', sa.String(), nullable=True),
        sa.Column('banner_text', sa.String(), nullable=True),
        sa.Column('banner_subtext', sa.String(), nullable=True),
        sa.Column('show_banner', sa.Boolean(), nullable=True),
        sa.Column('show_vendor_info', sa.Boolean(), nullable=True),
        sa.Column('show_contact_info', sa.Boolean(), nullable=True),
        sa.Column('show_ratings', sa.Boolean(), nullable=True),
        sa.Column('products_per_page', sa.Integer(), nullable=True),
        sa.Column('custom_css', sa.Text(), nullable=True),
        sa.Column('facebook_url', sa.String(), nullable=True),
        sa.Column('instagram_url', sa.String(), nullable=True),
        sa.Column('twitter_url', sa.String(), nullable=True),
        sa.Column('whatsapp_number', sa.String(), nullable=True),
        sa.Column('enable_reviews', sa.Boolean(), nullable=True),
        sa.Column('enable_wishlist', sa.Boolean(), nullable=True),
        sa.Column('enable_sharing', sa.Boolean(), nullable=True),
        sa.Column('meta_title', sa.String(), nullable=True),
        sa.Column('meta_description', sa.Text(), nullable=True),
        sa.Column('meta_keywords', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vendor_id')
    )


def downgrade():
    # Drop the marketplace_settings table
    op.drop_table('marketplace_settings')
