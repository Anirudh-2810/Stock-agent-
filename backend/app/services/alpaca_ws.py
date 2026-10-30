# Alpaca WebSocket - disabled on Python 3.14 due to websockets library compatibility issues
# (websockets library has Python 3.14 compatibility issues with 'extra_headers' parameter)
import sys
if sys.version_info >= (3, 14):
    ALPACA_WS_AVAILABLE = False
    StockDataStream = None
    DataFeed = None
    Quote = None
    Trade = None
else:
    try:
        from alpaca.data.live import StockDataStream
        from alpaca.data.enums import DataFeed
        from alpaca.data.models import Quote, Trade
        ALPACA_WS_AVAILABLE = True
    except ImportError:
        StockDataStream = None
        DataFeed = None
        Quote = None
        Trade = None
        ALPACA_WS_AVAILABLE = False

from app.core.config import settings
from app.core.redis import get_redis
from app.schemas import QuoteData, TradeData
from decimal import Decimal
from typing import Callable, List, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


class AlpacaWSService:
    def __init__(self, symbols: List[str]):
        if not ALPACA_WS_AVAILABLE:
            logger.warning("Alpaca WebSocket not available - running in mock mode")
            self.symbols = symbols
            self.stream = None
            self._running = False
            self._quote_callbacks: List[Callable] = []
            self._trade_callbacks: List[Callable] = []
            self._reconnect_task = None
            return
            
        self.symbols = symbols
        self.stream: Optional[StockDataStream] = None
        self._running = False
        self._quote_callbacks: List[Callable] = []
        self._trade_callbacks: List[Callable] = []
        self._reconnect_task: Optional[asyncio.Task] = None
    
    async def start(self):
        if not ALPACA_WS_AVAILABLE:
            logger.warning("Alpaca WS start() called but not available - mock mode")
            self._running = True
            return
        
        if self._running:
            return
        
        self.stream = StockDataStream(
            api_key=settings.alpaca_api_key,
            secret_key=settings.alpaca_secret_key,
            feed=DataFeed.IEX,
        )
        
        self.stream.subscribe_quotes(self._handle_quote, *self.symbols)
        self.stream.subscribe_trades(self._handle_trade, *self.symbols)
        
        self._running = True
        asyncio.create_task(self._run_stream())
        logger.info(f"Alpaca WS started for symbols: {self.symbols}")
    
    async def _run_stream(self):
        if not ALPACA_WS_AVAILABLE:
            return
        while self._running:
            try:
                await self.stream._run_forever()
            except Exception as e:
                logger.error(f"WS error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)
                if self._running:
                    await self.start()
    
    async def stop(self):
        self._running = False
        if self.stream:
            await self.stream.stop_ws()
        if self._reconnect_task:
            self._reconnect_task.cancel()
        logger.info("Alpaca WS stopped")
    
    def on_quote(self, callback: Callable[[QuoteData], None]):
        self._quote_callbacks.append(callback)
    
    def on_trade(self, callback: Callable[[TradeData], None]):
        self._trade_callbacks.append(callback)
    
    def remove_quote_callback(self, callback: Callable) -> bool:
        try:
            self._quote_callbacks.remove(callback)
            return True
        except ValueError:
            return False
    
    def remove_trade_callback(self, callback: Callable) -> bool:
        try:
            self._trade_callbacks.remove(callback)
            return True
        except ValueError:
            return False
    
    async def _handle_quote(self, quote):
        if not ALPACA_WS_AVAILABLE:
            return
        q = QuoteData(
            symbol=quote.symbol,
            bid_price=Decimal(str(quote.bid_price)),
            bid_size=quote.bid_size,
            ask_price=Decimal(str(quote.ask_price)),
            ask_size=quote.ask_size,
            timestamp=quote.timestamp,
        )
        await self._publish_to_redis("quotes", q)
        for cb in list(self._quote_callbacks):
            try:
                await cb(q)
            except Exception as e:
                logger.error(f"Quote callback error: {e}")
    
    async def _handle_trade(self, trade):
        if not ALPACA_WS_AVAILABLE:
            return
        t = TradeData(
            symbol=trade.symbol,
            price=Decimal(str(trade.price)),
            size=trade.size,
            timestamp=trade.timestamp,
            exchange=trade.exchange,
        )
        await self._publish_to_redis("trades", t)
        for cb in list(self._trade_callbacks):
            try:
                await cb(t)
            except Exception as e:
                logger.error(f"Trade callback error: {e}")
    
    async def _publish_to_redis(self, channel: str, data):
        try:
            redis = await get_redis()
            await redis.publish(f"alpaca:{channel}", data.model_dump_json())
        except Exception as e:
            logger.error(f"Redis publish error: {e}")


# Default instance for 10 liquid tickers
DEFAULT_SYMBOLS = ["AAPL", "NVDA", "SPY", "QQQ", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "JPM"]

alpaca_ws = AlpacaWSService(DEFAULT_SYMBOLS)