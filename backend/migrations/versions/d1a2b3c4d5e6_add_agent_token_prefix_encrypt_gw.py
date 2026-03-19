"""add agent_token_prefix and encrypt gateway tokens

Revision ID: d1a2b3c4d5e6
Revises: 1a7b2c3d4e5f
Create Date: 2026-03-19 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "d1a2b3c4d5e6"
down_revision = "1a7b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Add agent_token_prefix to agents table
    agent_columns = {column["name"] for column in inspector.get_columns("agents")}
    if "agent_token_prefix" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column("agent_token_prefix", sa.String(), nullable=True),
        )
        op.create_index(
            "ix_agents_agent_token_prefix",
            "agents",
            ["agent_token_prefix"],
        )

    # Add encrypted_token to gateways table
    gw_columns = {column["name"] for column in inspector.get_columns("gateways")}
    if "encrypted_token" not in gw_columns:
        op.add_column(
            "gateways",
            sa.Column("encrypted_token", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    gw_columns = {column["name"] for column in inspector.get_columns("gateways")}
    if "encrypted_token" in gw_columns:
        op.drop_column("gateways", "encrypted_token")

    agent_columns = {column["name"] for column in inspector.get_columns("agents")}
    if "agent_token_prefix" in agent_columns:
        op.drop_index("ix_agents_agent_token_prefix", table_name="agents")
        op.drop_column("agents", "agent_token_prefix")
