from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '002_point_in_time_features'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    # UUID default value depends on dialect
    uuid_default = sa.text('gen_random_uuid()') if not is_sqlite else sa.text('lower(hex(randomblob(16)))')
    
    # JSON type depends on dialect
    json_type = JSONB if not is_sqlite else sa.JSON
    
    # fundamentals_point_in_time table
    op.create_table(
        'fundamentals_point_in_time',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()') if not is_sqlite else sa.text('lower(hex(randomblob(16)))')),
        sa.Column('symbol', sa.String(10), index=True),
        sa.Column('period_end', sa.Date, index=True),
        sa.Column('filing_date', sa.Date, index=True),
        sa.Column('knowledge_timestamp', sa.DateTime, index=True),
        sa.Column('form_type', sa.String(10)),
        sa.Column('fiscal_year', sa.Integer),
        sa.Column('fiscal_period', sa.String(10)),
        sa.Column('net_income', sa.Numeric(20, 2), nullable=True),
        sa.Column('revenue', sa.Numeric(20, 2), nullable=True),
        sa.Column('total_assets', sa.Numeric(20, 2), nullable=True),
        sa.Column('total_liabilities', sa.Numeric(20, 2), nullable=True),
        sa.Column('stockholders_equity', sa.Numeric(20, 2), nullable=True),
        sa.Column('shares_outstanding', sa.Numeric(20, 4), nullable=True),
        sa.Column('eps_basic', sa.Numeric(10, 4), nullable=True),
        sa.Column('operating_income', sa.Numeric(20, 2), nullable=True),
        sa.Column('cash_equivalents', sa.Numeric(20, 2), nullable=True),
        sa.Column('gross_profit', sa.Numeric(20, 2), nullable=True),
        sa.Column('research_development', sa.Numeric(20, 2), nullable=True),
        sa.Column('selling_general_admin', sa.Numeric(20, 2), nullable=True),
        sa.Column('depreciation_amortization', sa.Numeric(20, 2), nullable=True),
        sa.Column('interest_expense', sa.Numeric(20, 2), nullable=True),
        sa.Column('income_tax_expense', sa.Numeric(20, 2), nullable=True),
        sa.Column('capital_expenditures', sa.Numeric(20, 2), nullable=True),
        sa.Column('free_cash_flow', sa.Numeric(20, 2), nullable=True),
        sa.Column('dividends_per_share', sa.Numeric(10, 4), nullable=True),
        sa.Column('book_value_per_share', sa.Numeric(10, 4), nullable=True),
        sa.Column('tags_used', sa.JSON if is_sqlite else JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('symbol', 'period_end', 'filing_date', name='uq_fundamentals_symbol_period_filing'),
    )
    
    op.create_index('ix_fundamentals_pit_symbol_filing', 'fundamentals_point_in_time', ['symbol', 'filing_date'])
    op.create_index('ix_fundamentals_pit_symbol_period', 'fundamentals_point_in_time', ['symbol', 'period_end'])
    op.create_index('ix_fundamentals_pit_knowledge_ts', 'fundamentals_point_in_time', ['knowledge_timestamp'])
    
    # ml_features_weekly materialized view - only for PostgreSQL
    if not bind.dialect.name == 'sqlite':
        op.execute("""
            CREATE MATERIALIZED VIEW ml_features_weekly AS
            WITH weekly_ohlcv AS (
                SELECT
                    symbol,
                    date_trunc('week', time)::date AS week_end,
                    MAX(time) AS max_time,
                    FIRST_VALUE(open) OVER (PARTITION BY symbol, date_trunc('week', time) ORDER BY time) AS week_open,
                    MAX(high) AS week_high,
                    MIN(low) AS week_low,
                    LAST_VALUE(close) OVER (PARTITION BY symbol, date_trunc('week', time) ORDER BY time
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS week_close,
                    SUM(volume) AS week_volume,
                    LAST_VALUE(vwap) OVER (PARTITION BY symbol, date_trunc('week', time) ORDER BY time
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS week_vwap,
                    MAX(ingestion_timestamp) AS max_ingestion_ts
                FROM ohlcv
                GROUP BY symbol, date_trunc('week', time)
            ),
            weekly_features AS (
                SELECT
                    symbol,
                    week_end AS as_of_date,
                    GREATEST(max_ingestion_ts, max_time) AS knowledge_timestamp,
                    
                    -- Returns
                    LOG(week_close / LAG(week_close, 1) OVER (PARTITION BY symbol ORDER BY week_end)) AS ret_1w,
                    LOG(week_close / LAG(week_close, 4) OVER (PARTITION BY symbol ORDER BY week_end)) AS ret_4w,
                    LOG(week_close / LAG(week_close, 12) OVER (PARTITION BY symbol ORDER BY week_end)) AS ret_12w,
                    LOG(week_close / LAG(week_close, 52) OVER (PARTITION BY symbol ORDER BY week_end)) AS ret_52w,
                    
                    -- Technical indicators (using last daily value of week)
                    NULL::numeric AS rsi_14,
                    NULL::numeric AS macd_hist,
                    NULL::numeric AS bb_pct,
                    NULL::numeric AS atr_14,
                    NULL::numeric AS adx_14,
                    
                    -- Forward returns (labels)
                    LOG(LEAD(week_close, 1) OVER (PARTITION BY symbol ORDER BY week_end) / week_close) AS fwd_ret_1w,
                    LOG(LEAD(week_close, 4) OVER (PARTITION BY symbol ORDER BY week_end) / week_close) AS fwd_ret_4w,
                    LOG(LEAD(week_close, 12) OVER (PARTITION BY symbol ORDER BY week_end) / week_close) AS fwd_ret_12w
                FROM weekly_ohlcv
            )
            SELECT * FROM weekly_features
            WHERE fwd_ret_4w IS NOT NULL
            WITH NO DATA;
        """)
        
        op.create_index('ix_ml_features_weekly_symbol_date', 'ml_features_weekly', ['symbol', 'as_of_date'])
        op.create_index('ix_ml_features_weekly_knowledge_ts', 'ml_features_weekly', ['knowledge_timestamp'])
        
        # fundamentals_latest view (latest filing per symbol as of each date)
        op.execute("""
            CREATE VIEW fundamentals_latest AS
            SELECT DISTINCT ON (f.symbol, f.filing_date)
                f.symbol,
                f.filing_date AS knowledge_timestamp,
                f.period_end,
                f.fiscal_year,
                f.fiscal_period,
                f.net_income,
                f.revenue,
                f.total_assets,
                f.total_liabilities,
                f.stockholders_equity,
                f.shares_outstanding,
                f.eps_basic,
                f.operating_income,
                f.cash_equivalents,
                f.gross_profit,
                f.research_development,
                f.selling_general_admin,
                f.depreciation_amortization,
                f.interest_expense,
                f.income_tax_expense,
                f.capital_expenditures,
                f.free_cash_flow,
                f.dividends_per_share,
                f.book_value_per_share,
                CASE 
                    WHEN f.shares_outstanding > 0 AND f.net_income IS NOT NULL 
                    THEN f.net_income / f.shares_outstanding 
                END AS eps_calculated,
                CASE 
                    WHEN f.stockholders_equity > 0 AND f.net_income IS NOT NULL 
                    THEN f.net_income / f.stockholders_equity 
                END AS roe,
                CASE 
                    WHEN f.total_liabilities > 0 AND f.stockholders_equity > 0 
                    THEN f.total_liabilities / f.stockholders_equity 
                END AS debt_to_equity,
                CASE 
                    WHEN f.revenue > 0 AND f.net_income IS NOT NULL 
                    THEN f.net_income / f.revenue 
                END AS net_margin,
                CASE 
                    WHEN f.shares_outstanding > 0 AND f.stockholders_equity > 0 
                    THEN f.stockholders_equity / f.shares_outstanding 
                END AS book_value_ps_calculated
            FROM fundamentals_point_in_time f
            ORDER BY f.symbol, f.filing_date, f.filing_date DESC;
        """)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    if not is_sqlite:
        op.execute("DROP VIEW IF EXISTS fundamentals_latest;")
        op.execute("DROP MATERIALIZED VIEW IF EXISTS ml_features_weekly;")
    op.drop_table('fundamentals_point_in_time')