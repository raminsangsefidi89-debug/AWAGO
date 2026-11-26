"""Data platform v2: provenance, quality reports, job cancellation.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-26

Adds:
* price_bars: fetched_at, dataset_version, quality_flag + a CHECK constraint
  enforcing the demo/real split at the schema level
  (is_demo = (data_source = 'demo')) — applied via batch rebuild (SQLite).
* quality_reports table (stored data-quality reports).
* job_records: cancel_requested, correlation_id.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("price_bars") as batch_op:
        batch_op.add_column(sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("dataset_version", sa.String(length=64), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("quality_flag", sa.String(length=16), nullable=False, server_default="ok"))
        batch_op.create_check_constraint("ck_bar_demo_source", "is_demo = (data_source = 'demo')")

    op.create_table(
        "quality_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pair_symbol", sa.String(length=16), nullable=False),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_version", sa.String(length=8), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="clean"),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("report_json", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_quality_reports_pair", "quality_reports", ["pair_symbol", "data_source"])

    with op.batch_alter_table("job_records") as batch_op:
        batch_op.add_column(sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        batch_op.add_column(sa.Column("correlation_id", sa.String(length=64), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("job_records") as batch_op:
        batch_op.drop_column("correlation_id")
        batch_op.drop_column("cancel_requested")
    op.drop_index("ix_quality_reports_pair", table_name="quality_reports")
    op.drop_table("quality_reports")
    with op.batch_alter_table("price_bars") as batch_op:
        batch_op.drop_constraint("ck_bar_demo_source", type_="check")
        batch_op.drop_column("quality_flag")
        batch_op.drop_column("dataset_version")
        batch_op.drop_column("fetched_at")
