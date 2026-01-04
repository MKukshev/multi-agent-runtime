"""Add template_id to agent_instances

Revision ID: 0002_add_template_id_to_agent_instances
Revises: 0001_initial
Create Date: 2024-08-01 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_add_template_id_to_agent_instances"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_instances", sa.Column("template_id", sa.String(length=36), nullable=True))

    agent_instances = sa.table(
        "agent_instances",
        sa.column("id", sa.String(length=36)),
        sa.column("template_id", sa.String(length=36)),
        sa.column("template_version_id", sa.String(length=36)),
    )
    template_versions = sa.table(
        "template_versions",
        sa.column("id", sa.String(length=36)),
        sa.column("template_id", sa.String(length=36)),
    )

    backfill_stmt = sa.update(agent_instances).values(
        template_id=sa.select(template_versions.c.template_id)
        .where(template_versions.c.id == agent_instances.c.template_version_id)
        .scalar_subquery()
    )
    op.execute(backfill_stmt)

    with op.batch_alter_table("agent_instances", recreate="auto") as batch_op:
        batch_op.alter_column("template_id", existing_type=sa.String(length=36), nullable=False)

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_agent_instances_template",
            source_table="agent_instances",
            referent_table="agent_templates",
            local_cols=["template_id"],
            remote_cols=["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_agent_instances_template", "agent_instances", type_="foreignkey")
    op.drop_column("agent_instances", "template_id")
