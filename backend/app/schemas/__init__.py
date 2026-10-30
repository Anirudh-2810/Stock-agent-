from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from datetime import datetime
from decimal import Decimal
from uuid import UUID


class OrderRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    
    symbol: str = Field(..., min_length=1, max_length=10)
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    time_in_force: Literal["day", "gtc", "opg", "cls", "ioc", "fok"] = "day"
    qty: Decimal = Field(..., gt=0)
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    client_order_id: Optional[str] = None


class OrderResponse(BaseModel):
    id: UUID
    alpaca_order_id: Optional[str]
    client_order_id: Optional[str]
    symbol: str
    side: str
    type: str
    time_in_force: str
    qty: Decimal
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]
    filled_qty: Decimal
    filled_avg_price: Optional[Decimal]
    status: str
    submitted_at: Optional[datetime]
    filled_at: Optional[datetime]
    canceled_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class PositionResponse(BaseModel):
    id: UUID
    symbol: str
    side: str
    qty: Decimal
    avg_entry_price: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    unrealized_plpc: Decimal
    current_price: Decimal
    lastday_price: Decimal
    change_today: Decimal
    created_at: datetime
    updated_at: datetime


class AccountResponse(BaseModel):
    equity: Decimal
    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    daily_pl: Decimal
    daily_plpc: Decimal
    positions_count: int


class FillResponse(BaseModel):
    id: UUID
    order_id: UUID
    alpaca_trade_id: str
    symbol: str
    side: str
    qty: Decimal
    price: Decimal
    timestamp: datetime
    created_at: datetime


class GuardStatus(BaseModel):
    guard_type: str
    is_active: bool
    config: Optional[dict]
    triggered_at: Optional[datetime]
    trigger_count: int


class GuardUpdate(BaseModel):
    is_active: bool


class KillSwitchRequest(BaseModel):
    activate: bool


class QuoteData(BaseModel):
    symbol: str
    bid_price: Decimal
    bid_size: int
    ask_price: Decimal
    ask_size: int
    timestamp: datetime


class TradeData(BaseModel):
    symbol: str
    price: Decimal
    size: int
    timestamp: datetime
    exchange: str


class OHLCVResponse(BaseModel):
    time: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Optional[Decimal]
    trade_count: Optional[int]