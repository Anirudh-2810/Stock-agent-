"""Initial migration - create hypertables

Revision ID: 001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Get the database dialect to conditionally apply TimescaleDB commands
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    # UUID default value depends on dialect
    uuid_default = sa.text('gen_random_uuid()') if not is_sqlite else sa.text('lower(hex(randomblob(16)))')
    
    if not is_sqlite:
        # Enable TimescaleDB extension (PostgreSQL only)
        op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
    
    # tickers table
    op.create_table(
        'tickers',
        sa.Column('symbol', sa.String(10), primary_key=True),
        sa.Column('name', sa.String(255)),
        sa.Column('sector', sa.String(100)),
        sa.Column('industry', sa.String(100)),
        sa.Column('exchange', sa.String(20)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # ohlcv hypertable
    op.create_table(
        'ohlcv',
        sa.Column('time', sa.DateTime, primary_key=True),
        sa.Column('symbol', sa.String(10), primary_key=True),
        sa.Column('open', sa.Numeric(12, 4)),
        sa.Column('high', sa.Numeric(12, 4)),
        sa.Column('low', sa.Numeric(12, 4)),
        sa.Column('close', sa.Numeric(12, 4)),
        sa.Column('volume', sa.Numeric(20, 0)),
        sa.Column('vwap', sa.Numeric(12, 4)),
        sa.Column('trade_count', sa.Integer),
        sa.Column('ingestion_timestamp', sa.DateTime, default=sa.func.now()),
    )
    op.create_index('ix_ohlcv_symbol_time', 'ohlcv', ['symbol', 'time'])
    if not is_sqlite:
        op.execute("SELECT create_hypertable('ohlcv', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);")
    
    # positions table
    op.create_table(
        'positions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=uuid_default),
        sa.Column('symbol', sa.String(10), index=True),
        sa.Column('side', sa.String(10)),
        sa.Column('qty', sa.Numeric(12, 4)),
        sa.Column('avg_entry_price', sa.Numeric(12, 4)),
        sa.Column('market_value', sa.Numeric(12, 4)),
        sa.Column('unrealized_pl', sa.Numeric(12, 4)),
        sa.Column('unrealized_plpc', sa.Numeric(10, 4)),
        sa.Column('current_price', sa.Numeric(12, 4)),
        sa.Column('lastday_price', sa.Numeric(12, 4)),
        sa.Column('change_today', sa.Numeric(10, 4)),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # orders table
    op.create_table(
        'orders',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=uuid_default),
        sa.Column('alpaca_order_id', sa.String(50), unique=True, index=True),
        sa.Column('client_order_id', sa.String(50), index=True),
        sa.Column('symbol', sa.String(10), index=True),
        sa.Column('side', sa.String(10)),
        sa.Column('type', sa.String(20)),
        sa.Column('time_in_force', sa.String(10)),
        sa.Column('qty', sa.Numeric(12, 4)),
        sa.Column('limit_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('stop_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('filled_qty', sa.Numeric(12, 4), default=0),
        sa.Column('filled_avg_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('status', sa.String(20)),
        sa.Column('submitted_at', sa.DateTime),
        sa.Column('filled_at', sa.DateTime, nullable=True),
        sa.Column('canceled_at', sa.DateTime, nullable=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # fills table
    op.create_table(
        'fills',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=uuid_default),
        sa.Column('order_id', UUID(as_uuid=True), sa.ForeignKey('orders.id'), index=True),
        sa.Column('alpaca_trade_id', sa.String(50), unique=True),
        sa.Column('symbol', sa.String(10), index=True),
        sa.Column('side', sa.String(10)),
        sa.Column('qty', sa.Numeric(12, 4)),
        sa.Column('price', sa.Numeric(12, 4)),
        sa.Column('timestamp', sa.DateTime, index=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )
    
    # execution_guards table
    op.create_table(
        'execution_guards',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=uuid_default),
        sa.Column('guard_type', sa.String(50), unique=True),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('config', sa.Text, nullable=True),
        sa.Column('triggered_at', sa.DateTime, nullable=True),
        sa.Column('trigger_count', sa.Integer, default=0),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # account_snapshots hypertable
    op.create_table(
        'account_snapshots',
        sa.Column('time', sa.DateTime, primary_key=True),
        sa.Column('equity', sa.Numeric(15, 2)),
        sa.Column('cash', sa.Numeric(15, 2)),
        sa.Column('buying_power', sa.Numeric(15, 2)),
        sa.Column('portfolio_value', sa.Numeric(15, 2)),
        sa.Column('daily_pl', sa.Numeric(15, 2)),
        sa.Column('daily_plpc', sa.Numeric(10, 4)),
        sa.Column('positions_count', sa.Integer),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )
    if not is_sqlite:
        op.execute("SELECT create_hypertable('account_snapshots', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);")
    
    # corporate_actions table
    op.create_table(
        'corporate_actions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=uuid_default),
        sa.Column('symbol', sa.String(10), index=True),
        sa.Column('action_type', sa.String(20)),
        sa.Column('ratio', sa.Numeric(10, 4), nullable=True),
        sa.Column('amount', sa.Numeric(10, 4), nullable=True),
        sa.Column('ex_date', sa.DateTime, index=True),
        sa.Column('pay_date', sa.DateTime, nullable=True),
        sa.Column('announcement_date', sa.DateTime),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
        sa.UniqueConstraint('symbol', 'action_type', 'ex_date', name='uq_corporate_action_symbol_type_exdate'),
    )
    
    # Insert default execution guards
    op.execute("""
        INSERT INTO execution_guards (guard_type, is_active, config) VALUES
        ('kill_switch', true, '{}'),
        ('rate_limit', true, '{"max_orders_per_minute": 10}'),
        ('drawdown', true, '{"max_daily_drawdown_pct": 2.0}'),
        ('position_limit', true, '{"max_position_pct": 10.0}'),
        ('sector_limit', true, '{"max_sector_pct": 25.0}')
        ON CONFLICT (guard_type) DO NOTHING;
    """)


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'
    
    op.drop_table('corporate_actions')
    op.execute("DROP TABLE IF EXISTS account_snapshots;")
    op.drop_table('execution_guards')
    op.drop_table('fills')
    op.drop_table('orders')
    op.drop_table('positions')
    op.execute("DROP TABLE IF EXISTS ohlcv;")
    op.drop_table('tickers')
    if not is_sqlite:
        op.execute("DROP EXTENSION IF EXISTS timescaledb;")