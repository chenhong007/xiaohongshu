"""Add account health status fields

Revision ID: add_health_status
Revises: 
Create Date: 2024-12-17

This migration adds health status tracking fields to the accounts table:
- health_status: Current health status (healthy, cookie_expired, rate_limited, etc.)
- health_message: Detailed message about the health status
- health_updated_at: When the health status was last updated
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_health_status'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Add health status columns to accounts table."""
    # Check if columns already exist (for idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('accounts')]
    
    if 'health_status' not in columns:
        op.add_column('accounts', sa.Column('health_status', sa.String(32), nullable=True, server_default='healthy'))
    
    if 'health_message' not in columns:
        op.add_column('accounts', sa.Column('health_message', sa.Text(), nullable=True))
    
    if 'health_updated_at' not in columns:
        op.add_column('accounts', sa.Column('health_updated_at', sa.DateTime(), nullable=True))


def downgrade():
    """Remove health status columns from accounts table."""
    op.drop_column('accounts', 'health_updated_at')
    op.drop_column('accounts', 'health_message')
    op.drop_column('accounts', 'health_status')

