"""Add extended profile fields to users table

Revision ID: add_user_profile_fields
Revises: merge_heads_before_profile
Create Date: 2026-05-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_user_profile_fields'
down_revision = 'merge_heads_before_profile'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('gender', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('date_of_birth', sa.Date(), nullable=True))
    op.add_column('users', sa.Column('alternate_phone', sa.String(length=20), nullable=True))
    op.add_column('users', sa.Column('pincode', sa.String(length=10), nullable=True))
    op.add_column('users', sa.Column('city', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('state', sa.String(length=100), nullable=True))
    op.add_column('users', sa.Column('language', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('users', 'language')
    op.drop_column('users', 'state')
    op.drop_column('users', 'city')
    op.drop_column('users', 'pincode')
    op.drop_column('users', 'alternate_phone')
    op.drop_column('users', 'date_of_birth')
    op.drop_column('users', 'gender')
