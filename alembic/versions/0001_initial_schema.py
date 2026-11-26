"""Initial schema — exactly the AWAGO v1 schema.

Revision ID: 0001
Revises:
Create Date: 2026-11-26

A database created by v1 (create_all) has precisely these tables; legacy
databases are stamped at this revision and then upgraded normally.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currency_pairs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("base", sa.String(length=8), nullable=False),
        sa.Column("quote", sa.String(length=8), nullable=False),
        sa.Column("display_name_fa", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_currency_pairs_symbol", "currency_pairs", ["symbol"], unique=True)

    op.create_table(
        "price_bars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pair_symbol", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["pair_symbol"], ["currency_pairs.symbol"]),
        sa.UniqueConstraint("pair_symbol", "timestamp", "interval", "data_source", name="uq_bar_identity"),
    )
    op.create_index("ix_price_bars_pair_ts", "price_bars", ["pair_symbol", "timestamp"])

    op.create_table(
        "model_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pair_symbol", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("train_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("train_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("n_rows", sa.Integer(), nullable=False),
        sa.Column("features_version", sa.String(length=16), nullable=False),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metrics_json", sa.Text(), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "pair_symbol", "horizon", "model_name", "data_source", name="uq_model_identity"
        ),
    )
    op.create_index("ix_model_artifacts_pair_symbol", "model_artifacts", ["pair_symbol"])

    op.create_table(
        "metric_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pair_symbol", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("mae", sa.Float(), nullable=False),
        sa.Column("rmse", sa.Float(), nullable=False),
        sa.Column("smape", sa.Float(), nullable=False),
        sa.Column("directional_accuracy", sa.Float(), nullable=False),
        sa.Column("baseline_mae", sa.Float(), nullable=False),
        sa.Column("baseline_rmse", sa.Float(), nullable=False),
        sa.Column("beats_baseline", sa.Boolean(), nullable=False),
        sa.Column("n_test", sa.Integer(), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_source", sa.String(length=32), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
    )
    op.create_index("ix_metric_records_pair_symbol", "metric_records", ["pair_symbol"])

    op.create_table(
        "job_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("params_json", sa.Text(), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("job_records")
    op.drop_index("ix_metric_records_pair_symbol", table_name="metric_records")
    op.drop_table("metric_records")
    op.drop_index("ix_model_artifacts_pair_symbol", table_name="model_artifacts")
    op.drop_table("model_artifacts")
    op.drop_index("ix_price_bars_pair_ts", table_name="price_bars")
    op.drop_table("price_bars")
    op.drop_index("ix_currency_pairs_symbol", table_name="currency_pairs")
    op.drop_table("currency_pairs")
