from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest,
    GetOrdersRequest, ClosePositionRequest
)
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce, QueryOrderStatus
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
from app.core.config import settings
from app.schemas import OrderRequest, OrderResponse, PositionResponse, AccountResponse, QuoteData, TradeData
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
import asyncio


class AlpacaRESTService:
    def __init__(self):
        self.trading_client = TradingClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            paper=settings.alpaca_paper,
        )
        self.data_client = StockHistoricalDataClient(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
        )
    
    async def get_account(self) -> AccountResponse:
        account = self.trading_client.get_account()
        return AccountResponse(
            equity=Decimal(str(account.equity)),
            cash=Decimal(str(account.cash)),
            buying_power=Decimal(str(account.buying_power)),
            portfolio_value=Decimal(str(account.portfolio_value)),
            daily_pl=Decimal(str(account.unrealized_pl)),
            daily_plpc=Decimal(str(account.unrealized_plpc)),
            positions_count=len(self.trading_client.get_all_positions()),
        )
    
    async def get_positions(self) -> List[PositionResponse]:
        positions = self.trading_client.get_all_positions()
        result = []
        for pos in positions:
            result.append(PositionResponse(
                id=pos.asset_id,
                symbol=pos.symbol,
                side=pos.side.value,
                qty=Decimal(str(pos.qty)),
                avg_entry_price=Decimal(str(pos.avg_entry_price)),
                market_value=Decimal(str(pos.market_value)),
                unrealized_pl=Decimal(str(pos.unrealized_pl)),
                unrealized_plpc=Decimal(str(pos.unrealized_plpc)),
                current_price=Decimal(str(pos.current_price)),
                lastday_price=Decimal(str(pos.lastday_price)),
                change_today=Decimal(str(pos.change_today)),
                created_at=pos.created_at,
                updated_at=pos.updated_at,
            ))
        return result
    
    async def place_order(self, order: OrderRequest) -> OrderResponse:
        side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL
        tif = TimeInForce[order.time_in_force.upper()]
        
        if order.type == "market":
            req = MarketOrderRequest(
                symbol=order.symbol,
                qty=float(order.qty),
                side=side,
                time_in_force=tif,
                client_order_id=order.client_order_id,
            )
        elif order.type == "limit":
            req = LimitOrderRequest(
                symbol=order.symbol,
                qty=float(order.qty),
                side=side,
                time_in_force=tif,
                limit_price=float(order.limit_price),
                client_order_id=order.client_order_id,
            )
        elif order.type == "stop":
            req = StopOrderRequest(
                symbol=order.symbol,
                qty=float(order.qty),
                side=side,
                time_in_force=tif,
                stop_price=float(order.stop_price),
                client_order_id=order.client_order_id,
            )
        elif order.type == "stop_limit":
            req = StopLimitOrderRequest(
                symbol=order.symbol,
                qty=float(order.qty),
                side=side,
                time_in_force=tif,
                limit_price=float(order.limit_price),
                stop_price=float(order.stop_price),
                client_order_id=order.client_order_id,
            )
        
        alpaca_order = self.trading_client.submit_order(req)
        return self._map_order(alpaca_order)
    
    async def get_orders(self, status: Optional[str] = None, limit: int = 100) -> List[OrderResponse]:
        req = GetOrdersRequest(
            status=QueryOrderStatus(status) if status else None,
            limit=limit,
            nested=True,
        )
        orders = self.trading_client.get_orders(req)
        return [self._map_order(o) for o in orders]
    
    async def cancel_order(self, order_id: str) -> bool:
        try:
            self.trading_client.cancel_order_by_id(order_id)
            return True
        except Exception:
            return False
    
    async def close_position(self, symbol: str) -> bool:
        try:
            self.trading_client.close_position(symbol)
            return True
        except Exception:
            return False
    
    async def close_all_positions(self) -> bool:
        try:
            self.trading_client.close_all_positions()
            return True
        except Exception:
            return False
    
    async def get_latest_quotes(self, symbols: List[str]) -> List[QuoteData]:
        req = StockLatestQuoteRequest(symbol_or_symbols=symbols)
        quotes = self.data_client.get_stock_latest_quote(req)
        result = []
        for symbol, quote in quotes.items():
            result.append(QuoteData(
                symbol=symbol,
                bid_price=Decimal(str(quote.bid_price)),
                bid_size=quote.bid_size,
                ask_price=Decimal(str(quote.ask_price)),
                ask_size=quote.ask_size,
                timestamp=quote.timestamp,
            ))
        return result
    
    async def get_latest_trades(self, symbols: List[str]) -> List[TradeData]:
        req = StockLatestTradeRequest(symbol_or_symbols=symbols)
        trades = self.data_client.get_stock_latest_trade(req)
        result = []
        for symbol, trade in trades.items():
            result.append(TradeData(
                symbol=symbol,
                price=Decimal(str(trade.price)),
                size=trade.size,
                timestamp=trade.timestamp,
                exchange=trade.exchange,
            ))
        return result
    
    def _map_order(self, order) -> OrderResponse:
        return OrderResponse(
            id=order.id,
            alpaca_order_id=order.id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side.value,
            type=order.order_type.value,
            time_in_force=order.time_in_force.value,
            qty=Decimal(str(order.qty)),
            limit_price=Decimal(str(order.limit_price)) if order.limit_price else None,
            stop_price=Decimal(str(order.stop_price)) if order.stop_price else None,
            filled_qty=Decimal(str(order.filled_qty)),
            filled_avg_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
            status=order.status.value,
            submitted_at=order.submitted_at,
            filled_at=order.filled_at,
            canceled_at=order.canceled_at,
            created_at=order.created_at,
            updated_at=order.updated_at,
        )


alpaca_rest = AlpacaRESTService()