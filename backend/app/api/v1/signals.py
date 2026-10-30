from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Optional
from datetime import datetime
import pandas as pd
import logging

from app.core.database import get_db
from app.core.security import verify_api_key
from app.services.signal_engine import signal_engine
from app.services.feature_engine import feature_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"], dependencies=[Depends(verify_api_key)])

DEFAULT_SYMBOLS = ["AAPL", "NVDA", "SPY", "QQQ", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "JPM"]


@router.get("/scan")
async def scan_signals(
    symbols: str = Query(",".join(DEFAULT_SYMBOLS)),
    days: int = Query(250, ge=30, le=1000),
    model_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Score every symbol across the technical + optional ML signal blend."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="No symbols provided")

    try:
        results = await signal_engine.scan_universe(
            db, symbol_list, days=days, model_name=model_name
        )
    except Exception as e:
        logger.error(f"Signal scan failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    buys = [r for r in results if r.get("action") == "BUY"]
    sells = [r for r in results if r.get("action") == "SELL"]
    holds = [r for r in results if r.get("action") == "HOLD"]

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "counts": {"buy": len(buys), "sell": len(sells), "hold": len(holds)},
        "model_blend": bool(model_name),
        "signals": results,
    }


@router.get("/{symbol}")
async def get_symbol_signal(
    symbol: str,
    days: int = Query(250, ge=30, le=1000),
    model_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    symbol = symbol.upper()
    df = await feature_store.compute_features(db, symbol, days)

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    ml_score = None
    if model_name:
        ml_score = await signal_engine._get_ml_score(db, model_name, symbol)

    signal = signal_engine.compute_signal(df, ml_score)

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
    as_of = latest.name
    if hasattr(as_of, "tz_convert"):
        as_of = as_of.tz_convert("UTC").isoformat()
    else:
        as_of = str(as_of)

    return {
        "symbol": symbol,
        "signal": signal,
        "quote": {
            "close": round(float(latest["close"]), 4),
            "open": round(float(latest["open"]), 4),
            "high": round(float(latest["high"]), 4),
            "low": round(float(latest["low"]), 4),
            "volume": int(latest["volume"]) if "volume" in latest and pd.notna(latest["volume"]) else None,
            "change": round(float(latest["close"] - prev["close"]), 4),
            "change_pct": round(float((latest["close"] / prev["close"] - 1) * 100), 4),
            "as_of": as_of,
        },
        "indicators": {
            col: round(float(df[col].iloc[-1]), 4)
            for col in ["sma_20", "sma_50", "sma_200", "ema_50", "rsi_14", "macd", "macd_signal", "atr_14"]
            if col in df.columns and not pd.isna(df[col].iloc[-1])
        },
    }


@router.get("/portfolio/summary")
async def portfolio_signal_summary(
    symbols: str = Query(",".join(DEFAULT_SYMBOLS)),
    model_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="No symbols provided")

    results = await signal_engine.scan_universe(db, symbol_list, days=250, model_name=model_name)

    return {
        "total": len(results),
        "strong_buys": len([r for r in results if r.get("score", 0) >= 0.6]),
        "buys": len([r for r in results if r.get("action") == "BUY"]),
        "sells": len([r for r in results if r.get("action") == "SELL"]),
        "avg_score": round(sum(r.get("score", 0) for r in results) / max(len(results), 1), 4),
        "top_picks": results[:5],
        "worst_picks": results[-5:][::-1],
    }