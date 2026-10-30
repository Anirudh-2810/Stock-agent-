import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert

from app.models import OHLCV, CorporateAction, Ticker
from app.core.database import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class OHLCVData:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    trade_count: Optional[int] = None


@dataclass
class CorporateActionData:
    symbol: str
    action_type: str
    ex_date: datetime
    announcement_date: datetime
    ratio: Optional[float] = None
    amount: Optional[float] = None
    pay_date: Optional[datetime] = None


class YFinanceIngester:
    def __init__(self, batch_size: int = 10, max_retries: int = 3):
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.session = None
    
    async def fetch_ohlcv(
        self,
        symbols: List[str],
        start: str,
        end: str = None,
        interval: str = "1d",
        auto_adjust: bool = True,
    ) -> Dict[str, List[OHLCVData]]:
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")
        
        results = {}
        
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i:i + self.batch_size]
            batch_results = await self._fetch_batch(batch, start, end, interval, auto_adjust)
            results.update(batch_results)
        
        return results
    
    async def _fetch_batch(
        self,
        symbols: List[str],
        start: str,
        end: str,
        interval: str,
        auto_adjust: bool,
    ) -> Dict[str, List[OHLCVData]]:
        results = {}
        
        for symbol in symbols:
            for attempt in range(self.max_retries):
                try:
                    ticker = yf.Ticker(symbol)
                    df = ticker.history(
                        start=start,
                        end=end,
                        interval=interval,
                        auto_adjust=auto_adjust,
                        actions=True,
                    )
                    
                    if df.empty:
                        logger.warning(f"No data for {symbol}")
                        results[symbol] = []
                        break
                    
                    ohlcv_list = []
                    for idx, row in df.iterrows():
                        ohlcv_list.append(OHLCVData(
                            symbol=symbol,
                            timestamp=idx.to_pydatetime(),
                            open=float(row["Open"]),
                            high=float(row["High"]),
                            low=float(row["Low"]),
                            close=float(row["Close"]),
                            volume=int(row["Volume"]),
                        ))
                    
                    results[symbol] = ohlcv_list
                    logger.info(f"Fetched {len(ohlcv_list)} bars for {symbol}")
                    break
                    
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {symbol}: {e}")
                    if attempt == self.max_retries - 1:
                        logger.error(f"All attempts failed for {symbol}")
                        results[symbol] = []
        
        return results
    
    async def fetch_corporate_actions(self, symbols: List[str]) -> Dict[str, List[CorporateActionData]]:
        results = {}
        
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                actions = ticker.actions
                
                if actions is None or actions.empty:
                    results[symbol] = []
                    continue
                
                ca_list = []
                for idx, row in actions.iterrows():
                    action_type = "unknown"
                    ratio = None
                    amount = None
                    
                    if "Stock Splits" in row and row["Stock Splits"] > 0:
                        action_type = "split"
                        ratio = float(row["Stock Splits"])
                    elif "Dividends" in row and row["Dividends"] > 0:
                        action_type = "dividend"
                        amount = float(row["Dividends"])
                    
                    if action_type != "unknown":
                        ca_list.append(CorporateActionData(
                            symbol=symbol,
                            action_type=action_type,
                            ratio=ratio,
                            amount=amount,
                            ex_date=idx.to_pydatetime(),
                            pay_date=None,
                            announcement_date=idx.to_pydatetime(),
                        ))
                
                results[symbol] = ca_list
                logger.info(f"Fetched {len(ca_list)} corporate actions for {symbol}")
                
            except Exception as e:
                logger.error(f"Failed to fetch corporate actions for {symbol}: {e}")
                results[symbol] = []
        
        return results
    
    async def upsert_ohlcv(self, db: AsyncSession, ohlcv_data: List[OHLCVData]) -> int:
        if not ohlcv_data:
            return 0
        
        stmt = insert(OHLCV).values([
            {
                "time": d.timestamp,
                "symbol": d.symbol,
                "open": d.open,
                "high": d.high,
                "low": d.low,
                "close": d.close,
                "volume": d.volume,
                "vwap": d.vwap,
                "trade_count": d.trade_count,
                "ingestion_timestamp": datetime.utcnow(),
            }
            for d in ohlcv_data
        ])
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["time", "symbol"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "vwap": stmt.excluded.vwap,
                "trade_count": stmt.excluded.trade_count,
                "ingestion_timestamp": stmt.excluded.ingestion_timestamp,
            },
        )
        
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount
    
    async def upsert_corporate_actions(
        self, db: AsyncSession, ca_data: List[CorporateActionData]
    ) -> int:
        if not ca_data:
            return 0
        
        stmt = insert(CorporateAction).values([
            {
                "symbol": d.symbol,
                "action_type": d.action_type,
                "ratio": d.ratio,
                "amount": d.amount,
                "ex_date": d.ex_date,
                "pay_date": d.pay_date,
                "announcement_date": d.announcement_date,
            }
            for d in ca_data
        ])
        
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "action_type", "ex_date"],
            set_={
                "ratio": stmt.excluded.ratio,
                "amount": stmt.excluded.amount,
                "pay_date": stmt.excluded.pay_date,
                "announcement_date": stmt.excluded.announcement_date,
            },
        )
        
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount
    
    async def run_daily_ingestion(self, symbols: List[str], days_back: int = 5) -> Dict:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        logger.info(f"Starting daily ingestion for {len(symbols)} symbols")
        
        ohlcv_results = await self.fetch_ohlcv(
            symbols, start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
        )
        
        ca_results = await self.fetch_corporate_actions(symbols)
        
        total_bars = 0
        total_actions = 0
        
        async for db in get_db():
            for symbol, bars in ohlcv_results.items():
                if bars:
                    count = await self.upsert_ohlcv(db, bars)
                    total_bars += count
            
            for symbol, actions in ca_results.items():
                if actions:
                    count = await self.upsert_corporate_actions(db, actions)
                    total_actions += count
        
        logger.info(f"Daily ingestion complete: {total_bars} bars, {total_actions} actions")
        return {"bars_upserted": total_bars, "actions_upserted": total_actions}


class CorporateActionAdjuster:
    @staticmethod
    def adjust_for_splits(df: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
        if actions.empty:
            return df
        
        splits = actions[actions["action_type"] == "split"].copy()
        if splits.empty:
            return df
        
        df = df.copy()
        df = df.sort_index()
        
        for _, split in splits.iterrows():
            ex_date = split["ex_date"]
            ratio = split["ratio"]
            
            mask = df.index < ex_date
            cols_to_adjust = ["open", "high", "low", "close"]
            df.loc[mask, cols_to_adjust] = df.loc[mask, cols_to_adjust] / ratio
            df.loc[mask, "volume"] = df.loc[mask, "volume"] * ratio
        
        return df
    
    @staticmethod
    def adjust_for_dividends(df: pd.DataFrame, actions: pd.DataFrame) -> pd.DataFrame:
        if actions.empty:
            return df
        
        dividends = actions[actions["action_type"] == "dividend"].copy()
        if dividends.empty:
            return df
        
        df = df.copy()
        df = df.sort_index()
        
        for _, div in dividends.iterrows():
            ex_date = div["ex_date"]
            amount = div["amount"]
            
            mask = df.index < ex_date
            cols_to_adjust = ["open", "high", "low", "close"]
            df.loc[mask, cols_to_adjust] = df.loc[mask, cols_to_adjust] - amount
        
        return df


yfinance_ingester = YFinanceIngester()
corporate_action_adjuster = CorporateActionAdjuster()