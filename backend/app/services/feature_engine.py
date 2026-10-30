import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from sqlalchemy.dialects.postgresql import insert

from app.models import OHLCV
from app.core.database import get_db

logger = logging.getLogger(__name__)

# pandas_ta is optional - fallback to manual calculations if not available
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    ta = None
    PANDAS_TA_AVAILABLE = False
    logger.warning("pandas_ta not available - using fallback indicator calculations")


INDICATOR_CONFIG = {
    "rsi": {"length": 14},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bbands": {"length": 20, "std": 2},
    "atr": {"length": 14},
    "obv": {},
    "vwap": {},
    "adx": {"length": 14},
    "stoch": {"k": 14, "d": 3, "smooth_k": 3},
    "cci": {"length": 20},
    "mfi": {"length": 14},
    "willr": {"length": 14},
    "roc": {"length": 10},
    "mom": {"length": 10},
    "ema_9": {"length": 9, "talib": True},
    "ema_21": {"length": 21, "talib": True},
    "ema_50": {"length": 50, "talib": True},
    "ema_200": {"length": 200, "talib": True},
    "sma_20": {"length": 20, "talib": True},
    "sma_50": {"length": 50, "talib": True},
    "sma_200": {"length": 200, "talib": True},
}


class TechnicalIndicatorEngine:
    def __init__(self):
        self.config = INDICATOR_CONFIG
    
    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or len(df) < 200:
            logger.warning(f"Insufficient data for indicators: {len(df)} rows")
            return df
        
        df = df.copy()
        df = df.sort_index()
        
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        df["returns"] = df["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df["close"].shift(1))
        
        if PANDAS_TA_AVAILABLE:
            # Use pandas_ta for all indicators
            try:
                df.ta.rsi(length=self.config["rsi"]["length"], append=True)
            except Exception as e:
                logger.warning(f"RSI failed: {e}")
            
            try:
                df.ta.macd(
                    fast=self.config["macd"]["fast"],
                    slow=self.config["macd"]["slow"],
                    signal=self.config["macd"]["signal"],
                    append=True,
                )
            except Exception as e:
                logger.warning(f"MACD failed: {e}")
            
            try:
                df.ta.bbands(
                    length=self.config["bbands"]["length"],
                    std=self.config["bbands"]["std"],
                    append=True,
                )
            except Exception as e:
                logger.warning(f"Bollinger Bands failed: {e}")
            
            try:
                df.ta.atr(length=self.config["atr"]["length"], append=True)
            except Exception as e:
                logger.warning(f"ATR failed: {e}")
            
            try:
                df.ta.obv(append=True)
            except Exception as e:
                logger.warning(f"OBV failed: {e}")
            
            try:
                df.ta.vwap(append=True)
            except Exception as e:
                logger.warning(f"VWAP failed: {e}")
            
            try:
                df.ta.adx(length=self.config["adx"]["length"], append=True)
            except Exception as e:
                logger.warning(f"ADX failed: {e}")
            
            try:
                df.ta.stoch(
                    k=self.config["stoch"]["k"],
                    d=self.config["stoch"]["d"],
                    smooth_k=self.config["stoch"]["smooth_k"],
                    append=True,
                )
            except Exception as e:
                logger.warning(f"Stochastic failed: {e}")
            
            try:
                df.ta.cci(length=self.config["cci"]["length"], append=True)
            except Exception as e:
                logger.warning(f"CCI failed: {e}")
            
            try:
                df.ta.mfi(length=self.config["mfi"]["length"], append=True)
            except Exception as e:
                logger.warning(f"MFI failed: {e}")
            
            try:
                df.ta.willr(length=self.config["willr"]["length"], append=True)
            except Exception as e:
                logger.warning(f"Williams %R failed: {e}")
            
            try:
                df.ta.roc(length=self.config["roc"]["length"], append=True)
            except Exception as e:
                logger.warning(f"ROC failed: {e}")
            
            try:
                df.ta.mom(length=self.config["mom"]["length"], append=True)
            except Exception as e:
                logger.warning(f"MOM failed: {e}")
            
            for name, params in [
                ("ema_9", self.config["ema_9"]),
                ("ema_21", self.config["ema_21"]),
                ("ema_50", self.config["ema_50"]),
                ("ema_200", self.config["ema_200"]),
                ("sma_20", self.config["sma_20"]),
                ("sma_50", self.config["sma_50"]),
                ("sma_200", self.config["sma_200"]),
            ]:
                try:
                    length = params["length"]
                    df[name] = ta.sma(df["close"], length=length) if "sma" in name else ta.ema(df["close"], length=length)
                except Exception as e:
                    logger.warning(f"{name} failed: {e}")
        else:
            # Fallback manual indicator calculations
            self._compute_fallback_indicators(df)
        
        if {"BBL_20_2.0", "BBU_20_2.0", "BBM_20_2.0"}.issubset(df.columns):
            df["bb_pct"] = (df["close"] - df["BBL_20_2.0"]) / (df["BBU_20_2.0"] - df["BBL_20_2.0"].replace(0, np.nan))
            df["bb_width"] = (df["BBU_20_2.0"] - df["BBL_20_2.0"]) / df["BBM_20_2.0"].replace(0, np.nan)
        else:
            df["bb_pct"] = np.nan
            df["bb_width"] = np.nan
        
        df["rsi_14"] = df.get("RSI_14")
        df["macd"] = df.get("MACD_12_26_9")
        df["macd_signal"] = df.get("MACDs_12_26_9")
        df["macd_hist"] = df.get("MACDh_12_26_9")
        df["atr_14"] = df.get("ATRr_14")
        df["adx_14"] = df.get("ADX_14")
        
        df = df.replace([np.inf, -np.inf], np.nan)
        
        return df
    
    def _compute_fallback_indicators(self, df: pd.DataFrame):
        """Manual indicator calculations when pandas_ta is not available."""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df["RSI_14"] = 100 - (100 / (1 + rs))
        
        # MACD
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        df["MACD_12_26_9"] = ema_fast - ema_slow
        df["MACDs_12_26_9"] = df["MACD_12_26_9"].ewm(span=9, adjust=False).mean()
        df["MACDh_12_26_9"] = df["MACD_12_26_9"] - df["MACDs_12_26_9"]
        
        # Bollinger Bands
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        df["BBM_20_2.0"] = sma_20
        df["BBU_20_2.0"] = sma_20 + 2 * std_20
        df["BBL_20_2.0"] = sma_20 - 2 * std_20
        
        # ATR
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["ATRr_14"] = tr.rolling(14).mean()
        
        # ADX (simplified)
        plus_dm = high.diff()
        minus_dm = low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        tr_14 = tr.rolling(14).sum()
        plus_di = 100 * (plus_dm.rolling(14).sum() / tr_14)
        minus_di = 100 * (minus_dm.abs().rolling(14).sum() / tr_14)
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di) * 100
        df["ADX_14"] = dx.rolling(14).mean()
        
        # OBV
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        df["OBV"] = obv
        
        # VWAP
        df["VWAP_D"] = (close * volume).cumsum() / volume.cumsum()
        
        # Stochastic
        low_14 = low.rolling(14).min()
        high_14 = high.rolling(14).max()
        df["STOCHk_14_3_3"] = 100 * (close - low_14) / (high_14 - low_14)
        df["STOCHd_14_3_3"] = df["STOCHk_14_3_3"].rolling(3).mean()
        
        # CCI
        tp = (high + low + close) / 3
        sma_tp = tp.rolling(20).mean()
        mad = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())))
        df["CCI_20"] = (tp - sma_tp) / (0.015 * mad)
        
        # MFI (simplified - using RSI-like on volume-weighted price)
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        positive_flow = money_flow.where(close.diff() > 0, 0).rolling(14).sum()
        negative_flow = money_flow.where(close.diff() < 0, 0).rolling(14).sum()
        mfi_ratio = positive_flow / negative_flow
        df["MFI_14"] = 100 - (100 / (1 + mfi_ratio))
        
        # Williams %R
        highest_high = high.rolling(14).max()
        lowest_low = low.rolling(14).min()
        df["WILLR_14"] = -100 * (highest_high - close) / (highest_high - lowest_low)
        
        # ROC
        df["ROC_10"] = close.pct_change(10) * 100
        
        # MOM
        df["MOM_10"] = close.diff(10)
        
        # EMAs and SMAs
        for name, params in [
            ("ema_9", self.config["ema_9"]),
            ("ema_21", self.config["ema_21"]),
            ("ema_50", self.config["ema_50"]),
            ("ema_200", self.config["ema_200"]),
            ("sma_20", self.config["sma_20"]),
            ("sma_50", self.config["sma_50"]),
            ("sma_200", self.config["sma_200"]),
        ]:
            length = params["length"]
            df[name] = close.ewm(span=length, adjust=False).mean() if "ema" in name else close.rolling(length).mean()
    
    def get_feature_columns(self) -> List[str]:
        return [
            "returns", "log_returns",
            "rsi_14", "macd", "macd_signal", "macd_hist",
            "BBU_20_2.0", "BBM_20_2.0", "BBL_20_2.0",
            "bb_pct", "bb_width",
            "atr_14", "adx_14",
            "OBV", "VWAP_D",
            "STOCHk_14_3_3", "STOCHd_14_3_3",
            "CCI_20", "MFI_14", "WILLR_14",
            "ROC_10", "MOM_10",
            "ema_9", "ema_21", "ema_50", "ema_200",
            "sma_20", "sma_50", "sma_200",
        ]


class FeatureStore:
    def __init__(self):
        self.engine = TechnicalIndicatorEngine()
    
    async def load_ohlcv(self, db: AsyncSession, symbol: str, days: int = 500) -> pd.DataFrame:
        cutoff = datetime.utcnow() - pd.Timedelta(days=days)
        
        stmt = select(OHLCV).where(
            and_(
                OHLCV.symbol == symbol,
                OHLCV.time >= cutoff,
            )
        ).order_by(OHLCV.time)
        
        result = await db.execute(stmt)
        rows = result.scalars().all()
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame([{
            "time": r.time,
            "open": float(r.open),
            "high": float(r.high),
            "low": float(r.low),
            "close": float(r.close),
            "volume": float(r.volume),
        } for r in rows])
        
        df.set_index("time", inplace=True)
        return df
    
    async def compute_features(self, db: AsyncSession, symbol: str, days: int = 500) -> pd.DataFrame:
        df = await self.load_ohlcv(db, symbol, days)
        
        if df.empty:
            return pd.DataFrame()
        
        df = self.engine.compute_all(df)
        
        return df
    
    async def compute_for_universe(
        self, db: AsyncSession, symbols: List[str], days: int = 500
    ) -> Dict[str, pd.DataFrame]:
        results = {}
        
        for symbol in symbols:
            try:
                df = await self.compute_features(db, symbol, days)
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                logger.error(f"Feature computation failed for {symbol}: {e}")
                results[symbol] = pd.DataFrame()
        
        return results


feature_store = FeatureStore()
technical_engine = TechnicalIndicatorEngine()