from sqlalchemy import (
    Column, String, DateTime, Numeric, Integer, Boolean, 
    ForeignKey, Index, PrimaryKeyConstraint, text, Date, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
import uuid
from datetime import datetime, date

Base = declarative_base()


class Ticker(Base):
    __tablename__ = "tickers"
    
    symbol = Column(String(10), primary_key=True)
    name = Column(String(255))
    sector = Column(String(100))
    industry = Column(String(100))
    exchange = Column(String(20))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OHLCV(Base):
    __tablename__ = "ohlcv"
    
    time = Column(DateTime, primary_key=True)
    symbol = Column(String(10), primary_key=True)
    open = Column(Numeric(12, 4))
    high = Column(Numeric(12, 4))
    low = Column(Numeric(12, 4))
    close = Column(Numeric(12, 4))
    volume = Column(Numeric(20, 0))
    vwap = Column(Numeric(12, 4))
    trade_count = Column(Integer)
    ingestion_timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_ohlcv_symbol_time", "symbol", "time"),
    )


class Position(Base):
    __tablename__ = "positions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), index=True)
    side = Column(String(10))  # long, short
    qty = Column(Numeric(12, 4))
    avg_entry_price = Column(Numeric(12, 4))
    market_value = Column(Numeric(12, 4))
    unrealized_pl = Column(Numeric(12, 4))
    unrealized_plpc = Column(Numeric(10, 4))
    current_price = Column(Numeric(12, 4))
    lastday_price = Column(Numeric(12, 4))
    change_today = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alpaca_order_id = Column(String(50), unique=True, index=True)
    client_order_id = Column(String(50), index=True)
    symbol = Column(String(10), index=True)
    side = Column(String(10))  # buy, sell
    type = Column(String(20))  # market, limit, stop, stop_limit
    time_in_force = Column(String(10))  # day, gtc, opg, cls, ioc, fok
    qty = Column(Numeric(12, 4))
    limit_price = Column(Numeric(12, 4), nullable=True)
    stop_price = Column(Numeric(12, 4), nullable=True)
    filled_qty = Column(Numeric(12, 4), default=0)
    filled_avg_price = Column(Numeric(12, 4), nullable=True)
    status = Column(String(20))  # new, partially_filled, filled, canceled, rejected, expired
    submitted_at = Column(DateTime)
    filled_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Fill(Base):
    __tablename__ = "fills"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), index=True)
    alpaca_trade_id = Column(String(50), unique=True)
    symbol = Column(String(10), index=True)
    side = Column(String(10))
    qty = Column(Numeric(12, 4))
    price = Column(Numeric(12, 4))
    timestamp = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ExecutionGuard(Base):
    __tablename__ = "execution_guards"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guard_type = Column(String(50), unique=True)  # kill_switch, rate_limit, drawdown, position_limit
    is_active = Column(Boolean, default=True)
    config = Column(Numeric, nullable=True)  # JSON stored as text
    triggered_at = Column(DateTime, nullable=True)
    trigger_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"
    
    time = Column(DateTime, primary_key=True)
    equity = Column(Numeric(15, 2))
    cash = Column(Numeric(15, 2))
    buying_power = Column(Numeric(15, 2))
    portfolio_value = Column(Numeric(15, 2))
    daily_pl = Column(Numeric(15, 2))
    daily_plpc = Column(Numeric(10, 4))
    positions_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class CorporateAction(Base):
    __tablename__ = "corporate_actions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), index=True)
    action_type = Column(String(20))  # split, dividend, merger, spinoff
    ratio = Column(Numeric(10, 4), nullable=True)  # for splits
    amount = Column(Numeric(10, 4), nullable=True)  # for dividends
    ex_date = Column(DateTime, index=True)
    pay_date = Column(DateTime, nullable=True)
    announcement_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("symbol", "action_type", "ex_date", name="uq_corporate_action_symbol_type_exdate"),
    )


class FundamentalsPointInTime(Base):
    __tablename__ = "fundamentals_point_in_time"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(10), index=True)
    period_end = Column(Date, index=True)
    filing_date = Column(Date, index=True)
    knowledge_timestamp = Column(DateTime, index=True)
    form_type = Column(String(10))
    fiscal_year = Column(Integer)
    fiscal_period = Column(String(10))
    net_income = Column(Numeric(20, 2), nullable=True)
    revenue = Column(Numeric(20, 2), nullable=True)
    total_assets = Column(Numeric(20, 2), nullable=True)
    total_liabilities = Column(Numeric(20, 2), nullable=True)
    stockholders_equity = Column(Numeric(20, 2), nullable=True)
    shares_outstanding = Column(Numeric(20, 4), nullable=True)
    eps_basic = Column(Numeric(10, 4), nullable=True)
    operating_income = Column(Numeric(20, 2), nullable=True)
    cash_equivalents = Column(Numeric(20, 2), nullable=True)
    gross_profit = Column(Numeric(20, 2), nullable=True)
    research_development = Column(Numeric(20, 2), nullable=True)
    selling_general_admin = Column(Numeric(20, 2), nullable=True)
    depreciation_amortization = Column(Numeric(20, 2), nullable=True)
    interest_expense = Column(Numeric(20, 2), nullable=True)
    income_tax_expense = Column(Numeric(20, 2), nullable=True)
    capital_expenditures = Column(Numeric(20, 2), nullable=True)
    free_cash_flow = Column(Numeric(20, 2), nullable=True)
    dividends_per_share = Column(Numeric(10, 4), nullable=True)
    book_value_per_share = Column(Numeric(10, 4), nullable=True)
    tags_used = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("symbol", "period_end", "filing_date", name="uq_fundamentals_symbol_period_filing"),
        Index("ix_fundamentals_pit_symbol_filing", "symbol", "filing_date"),
        Index("ix_fundamentals_pit_symbol_period", "symbol", "period_end"),
        Index("ix_fundamentals_pit_knowledge_ts", "knowledge_timestamp"),
    )