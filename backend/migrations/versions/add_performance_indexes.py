"""添加性能优化索引

修复笔记下载页面查询慢的问题，添加以下索引：
1. ix_notes_last_updated - 用于时间范围回退查询
2. ix_notes_type_upload_time - 复合索引，按类型筛选后排序

Revision ID: add_performance_indexes
Revises: add_account_health_status
Create Date: 2024-12-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'add_performance_indexes'
down_revision = 'add_account_health_status'
branch_labels = None
depends_on = None


def upgrade():
    """添加性能优化索引"""
    # 使用 batch mode 以支持 SQLite
    with op.batch_alter_table('notes', schema=None) as batch_op:
        # 添加 last_updated 索引，用于时间范围回退查询
        batch_op.create_index('ix_notes_last_updated', ['last_updated'], unique=False)
        # 添加 type + upload_time 复合索引，按类型筛选后排序
        batch_op.create_index('ix_notes_type_upload_time', ['type', 'upload_time'], unique=False)


def downgrade():
    """移除性能优化索引"""
    with op.batch_alter_table('notes', schema=None) as batch_op:
        batch_op.drop_index('ix_notes_type_upload_time')
        batch_op.drop_index('ix_notes_last_updated')

