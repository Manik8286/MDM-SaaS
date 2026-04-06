"""add_agent_token_and_script_jobs

Revision ID: 186b228acd97
Revises: 88186ad468a3
Create Date: 2026-04-01 12:19:01.285696
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '186b228acd97'
down_revision: Union[str, None] = '88186ad468a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('agent_token', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_devices_agent_token'), 'devices', ['agent_token'], unique=True)

    # script_jobs may already exist if the app ran create_all before this migration
    op.execute("""
        CREATE TABLE IF NOT EXISTS script_jobs (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
            device_id VARCHAR(36) NOT NULL REFERENCES devices(id),
            command TEXT NOT NULL,
            label VARCHAR(100),
            status VARCHAR(50) NOT NULL DEFAULT 'pending',
            exit_code INTEGER,
            stdout TEXT,
            stderr TEXT,
            queued_at TIMESTAMP NOT NULL DEFAULT now(),
            completed_at TIMESTAMP,
            created_by_id VARCHAR(36) REFERENCES users(id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_script_jobs_tenant_id ON script_jobs (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_script_jobs_device_id ON script_jobs (device_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_script_jobs_status ON script_jobs (status)")


def downgrade() -> None:
    op.drop_table('script_jobs')
    op.drop_index(op.f('ix_devices_agent_token'), table_name='devices')
    op.drop_column('devices', 'agent_token')
