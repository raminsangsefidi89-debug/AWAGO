"""Market + news layer (addendum) — market_quotes, market_snapshots, news_items, news_events.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_quotes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument", sa.String(32), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit_currency", sa.String(12), nullable=False),
        sa.Column("unit_quantity", sa.String(16), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(), nullable=False),
        sa.Column("fetched_at_utc", sa.DateTime(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_unofficial", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_live", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_market_quotes_inst", "market_quotes", ["instrument", "as_of_utc"])
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument", sa.String(32), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit_currency", sa.String(12), nullable=False),
        sa.Column("unit_quantity", sa.String(16), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("dispersion_pct", sa.Float(), nullable=True),
        sa.Column("n_sources", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_unofficial", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_market_snapshots_inst", "market_snapshots", ["instrument", "as_of_utc"])
    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False, server_default=""),
        sa.Column("published_at_utc", sa.DateTime(), nullable=True),
        sa.Column("fetched_at_utc", sa.DateTime(), nullable=False),
        sa.Column("available_at_utc", sa.DateTime(), nullable=False),
        sa.Column("language", sa.String(8), nullable=False, server_default="fa"),
        sa.Column("cluster_key", sa.String(64), nullable=True),
        sa.Column("reliability_tier", sa.String(16), nullable=False, server_default="unrated"),
        sa.Column("is_rumor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("topics_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sentiment", sa.Float(), nullable=True),
        sa.Column("sentiment_model", sa.String(64), nullable=False, server_default="lexicon-fa-en/1"),
    )
    op.create_index("ix_news_avail", "news_items", ["available_at_utc"])
    op.create_table(
        "news_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("detected_by", sa.String(64), nullable=False, server_default="rules/1"),
    )
    # provenance source_registry: verification status of every feed/source
    op.create_table(
        "source_registry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),  # market | news
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("verified_live", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.Text(), nullable=False, server_default="unverified"),
        sa.Column("last_checked_utc", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    for t in ("source_registry", "news_events", "news_items", "market_snapshots", "market_quotes"):
        op.drop_table(t)
