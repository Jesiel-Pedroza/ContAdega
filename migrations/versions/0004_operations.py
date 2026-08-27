"""operational audit

Revision ID: 0004_operations
Revises: 0003_offline_pwa
"""
from alembic import op
import sqlalchemy as sa

revision="0004"; down_revision="0003"; branch_labels=None; depends_on=None

def upgrade():
    op.create_table("audit_logs",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("action",sa.String(60),nullable=False),sa.Column("entity_type",sa.String(60)),sa.Column("entity_id",sa.String(64)),sa.Column("detail",sa.Text()),sa.Column("created_at",sa.DateTime(),nullable=False))
    op.create_index("ix_audit_logs_action","audit_logs",["action"]); op.create_index("ix_audit_logs_created_at","audit_logs",["created_at"])

def downgrade(): op.drop_table("audit_logs")
