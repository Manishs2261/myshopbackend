"""Add website_settings table

Revision ID: add_website_settings
Revises: add_storefront_payload_columns
Create Date: 2026-05-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'add_website_settings'
down_revision = 'add_storefront_payload_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'website_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        # General
        sa.Column('site_name', sa.String(), nullable=True, server_default='LocalShop'),
        sa.Column('tagline', sa.String(), nullable=True, server_default='Your Local Shopping Destination'),
        sa.Column('contact_email', sa.String(), nullable=True, server_default='admin@localshop.in'),
        sa.Column('contact_phone', sa.String(), nullable=True, server_default='+91 9800000000'),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('timezone', sa.String(), nullable=True, server_default='Asia/Kolkata'),
        sa.Column('currency', sa.String(), nullable=True, server_default='INR'),
        # Appearance
        sa.Column('logo_url', sa.String(), nullable=True),
        sa.Column('favicon_url', sa.String(), nullable=True),
        sa.Column('primary_color', sa.String(), nullable=True, server_default='#6c5ce7'),
        sa.Column('accent_color', sa.String(), nullable=True, server_default='#00cec9'),
        sa.Column('theme_mode', sa.String(), nullable=True, server_default='Dark'),
        sa.Column('font_family', sa.String(), nullable=True, server_default='DM Sans'),
        # SEO
        sa.Column('seo_meta_title', sa.String(), nullable=True),
        sa.Column('seo_meta_description', sa.Text(), nullable=True),
        sa.Column('seo_meta_keywords', sa.String(), nullable=True),
        sa.Column('seo_og_image_url', sa.String(), nullable=True),
        sa.Column('seo_canonical_url', sa.String(), nullable=True),
        # Shipping
        sa.Column('shipping_free_above', sa.Float(), nullable=True, server_default='499'),
        sa.Column('shipping_standard_rate', sa.Float(), nullable=True, server_default='49'),
        sa.Column('shipping_express_rate', sa.Float(), nullable=True, server_default='99'),
        sa.Column('shipping_estimated_days', sa.Integer(), nullable=True, server_default='3'),
        sa.Column('shipping_policy', sa.Text(), nullable=True),
        # Payments
        sa.Column('payment_commission_pct', sa.Float(), nullable=True, server_default='10'),
        sa.Column('payment_min_payout', sa.Float(), nullable=True, server_default='500'),
        sa.Column('payment_razorpay_enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('payment_cod_enabled', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('payment_razorpay_key_id', sa.String(), nullable=True),
        sa.Column('payment_razorpay_key_secret', sa.String(), nullable=True),
        # Email / SMTP
        sa.Column('smtp_host', sa.String(), nullable=True, server_default='smtp.gmail.com'),
        sa.Column('smtp_port', sa.Integer(), nullable=True, server_default='587'),
        sa.Column('smtp_username', sa.String(), nullable=True),
        sa.Column('smtp_password', sa.String(), nullable=True),
        sa.Column('smtp_from_name', sa.String(), nullable=True, server_default='LocalShop'),
        sa.Column('smtp_from_email', sa.String(), nullable=True, server_default='noreply@localshop.in'),
        sa.Column('smtp_encryption', sa.String(), nullable=True, server_default='TLS'),
        # Social
        sa.Column('social_facebook', sa.String(), nullable=True),
        sa.Column('social_instagram', sa.String(), nullable=True),
        sa.Column('social_twitter', sa.String(), nullable=True),
        sa.Column('social_youtube', sa.String(), nullable=True),
        sa.Column('social_linkedin', sa.String(), nullable=True),
        # Maintenance
        sa.Column('maintenance_enabled', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('maintenance_message', sa.Text(), nullable=True),
        sa.Column('maintenance_allowed_ips', sa.String(), nullable=True),
        sa.Column('maintenance_estimated_downtime', sa.String(), nullable=True),
        # JSON sections
        sa.Column('banner_slides', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('promo_sections', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('blog_posts', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('blog_view_all_url', sa.String(), nullable=True, server_default='/blog'),
        sa.Column('blog_section_visible', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('top_navigation', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('browse_categories', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_website_settings_id', 'website_settings', ['id'])


def downgrade():
    op.drop_index('ix_website_settings_id', table_name='website_settings')
    op.drop_table('website_settings')
