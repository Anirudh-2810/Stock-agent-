from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
import logging

from app.core.database import get_db
from app.core.security import verify_api_key
from app.models import OHLCV
from app.services.feature_engine import feature_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"], dependencies=[Depends(verify_api_key)])

INDEX_SYMBOLS = ["SPY", "QQQ", "DIA", "IWM"]
DEFAULT_UNIVERSE = ["AAPL", "NVDA", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "JPM", "SPY", "QQQ"]


@router.get("/overview")
async def market_overview(
    symbols: str = Query(",".join(DEFAULT_UNIVERSE)),
    days: int = Query(30, ge=5, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Market overview: index performance + best/worst movers over the window."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = select(
        OHLCV.symbol,
        func.max(OHLCV.time).label("latest_time"),
        func.min(OHLCV.time).label("first_time"),
    ).where(OHLCV.time >= cutoff).group_by(OHLCV.symbol)

    result = await db.execute(stmt)
    periods = {row.symbol: (row.latest_time, row.first_time) for row in result.all()}

    indexes = []
    movers = []
    for symbol in symbol_list:
        window = periods.get(symbol)
        if not window:
            continue
        latest_time, first_time = window
        if latest_time is None or first_time is None or first_time >= latest_time:
            continue

        closes = await _get_close_series(db, symbol, first_time, latest_time)
        if closes.empty:
            continue

        first_close = float(closes.iloc[0])
        last_close = float(closes.iloc[-1])
        change_pct = ((last_close / first_close) - 1) * 100 if first_close else 0.0

        entry = {
            "symbol": symbol,
            "close": round(last_close, 4),
            "change_pct": round(change_pct, 4),
            "window_start": first_time.isoformat(),
            "window_end": latest_time.isoformat(),
            "bars": len(closes),
        }
        if symbol in INDEX_SYMBOLS:
            indexes.append(entry)
        else:
            movers.append(entry)

    movers.sort(key=lambda m: m["change_pct"], reverse=True)

    return {
        "as_of": datetime.utcnow().isoformat(),
        "window_days": days,
        "indexes": indexes,
        "best": movers[:5],
        "worst": movers[-5:][::-1],
    }


@router.get("/symbol/{symbol}")
async def symbol_analysis(
    symbol: str,
    days: int = Query(250, ge=30, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Deep-dive for a single symbol: OHLCV history, technicals, and latest fundamentals."""
    symbol = symbol.upper()

    df = await feature_store.compute_features(db, symbol, days)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    history = []
    for idx, row in df.iterrows():
        entry = {
            "time": _iso(idx),
            "open": round(float(row.get("open", 0)), 4),
            "high": round(float(row.get("high", 0)), 4),
            "low": round(float(row.get("low", 0)), 4),
            "close": round(float(row.get("close", 0)), 4),
            "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume", 0)) else None,
        }
        history.append(entry)

    indicators = {}
    for col in ["sma_20", "sma_50", "sma_200", "ema_9", "ema_21", "ema_50", "ema_200",
                "rsi_14", "macd", "macd_signal", "macd_hist", "atr_14", "adx_14", "bb_pct"]:
        if col in df.columns and not df[col].dropna().empty:
            indicators[col] = round(float(df[col].iloc[-1]), 4)

    returns = df["close"].pct_change().dropna()
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2]) if len(df) >= 2 else last

    summary = {
        "close": round(last, 4),
        "change_pct": round(((last / prev) - 1) * 100, 4) if prev else 0.0,
        "day_range_high": round(float(df["high"].iloc[-1]), 4),
        "day_range_low": round(float(df["low"].iloc[-1]), 4),
        "period_return_pct": round(float(((last / df["close"].iloc[0]) - 1) * 100), 4),
        "volatility_annual": round(float(returns.std() * np.sqrt(252) * 100), 4) if len(returns) > 1 else 0.0,
        "avg_volume": round(float(df["volume"].mean()), 0) if "volume" in df.columns else 0.0,
    }

    fundamentals = await _latest_fundamentals(db, symbol)

    return {
        "symbol": symbol,
        "summary": summary,
        "indicators": indicators,
        "fundamentals": fundamentals,
        "history": history,
        "bars": len(history),
    }


@router.get("/compare")
async def compare_symbols(
    symbols: str = Query(...),
    days: int = Query(90, ge=5, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Normalized performance comparison across symbols (rebased to 100)."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if len(symbol_list) < 2:
        raise HTTPException(status_code=400, detail="Provide at least 2 symbols")

    cutoff = datetime.utcnow() - timedelta(days=days)
    result = {}
    for symbol in symbol_list:
        stmt = select(OHLCV.time, OHLCV.close).where(
            OHLCV.symbol == symbol, OHLCV.time >= cutoff
        ).order_by(OHLCV.time)
        rows = (await db.execute(stmt)).all()
        if not rows:
            result[symbol] = []
            continue
        base = float(rows[0].close)
        result[symbol] = [
            {"time": _iso(r.time), "value": round(float(r.close) / base * 100, 4)}
            for r in rows
        ]

    return {
        "symbols": symbol_list,
        "baseline": 100,
        "series": result,
    }


async def _get_close_series(
    db: AsyncSession, symbol: str, start: datetime, end: datetime
) -> pd.Series:
    stmt = select(OHLCV.time, OHLCV.close).where(
        OHLCV.symbol == symbol, OHLCV.time >= start, OHLCV.time <= end
    ).order_by(OHLCV.time)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([float(r.close) for r in rows])


async def _latest_fundamentals(db: AsyncSession, symbol: str) -> Optional[Dict]:
    try:
        from app.models import FundamentalsPointInTime
        stmt = select(FundamentalsPointInTime).where(
            FundamentalsPointInTime.symbol == symbol
        ).order_by(FundamentalsPointInTime.filing_date.desc()).limit(1)
        row = (await db.execute(stmt)).scalars().first()
        if not row:
            return None
        return {
            "filing_date": row.filing_date.isoformat() if row.filing_date else None,
            "period_end": row.period_end.isoformat() if row.period_end else None,
            "revenue": float(row.revenue) if row.revenue is not None else None,
            "net_income": float(row.net_income) if row.net_income is not None else None,
            "eps_basic": float(row.eps_basic) if row.eps_basic is not None else None,
            "total_assets": float(row.total_assets) if row.total_assets is not None else None,
            "stockholders_equity": float(row.stockholders_equity) if row.stockholders_equity is not None else None,
            "shares_outstanding": float(row.shares_outstanding) if row.shares_outstanding is not None else None,
            "pe_ratio": round(float(row.revenue / row.net_income), 4) if row.revenue and row.net_income and row.revenue > 0 and row.net_income != 0 else None,
            "tags_used": row.tags_used,
        }
    except Exception as e:
        logger.warning(f"Fundamentals lookup failed for {symbol}: {e}")
        return None


def _iso(value) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)