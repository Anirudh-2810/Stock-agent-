import numpy as np
import pandas as pd
from typing import Dict, Optional

from app.services.algorithms import sma, volatility


def market_regime(index_close: pd.Series, vol_lookback: int = 20, vol_percentile_window: int = 252) -> pd.Series:
    index_close = index_close.dropna()
    sma50 = sma(index_close.to_frame(), 50).iloc[:, 0]
    sma200 = sma(index_close.to_frame(), 200).iloc[:, 0]
    vol = (index_close.pct_change().rolling(vol_lookback).std() * np.sqrt(252))
    vol_pct = vol.rolling(vol_percentile_window, min_periods=63).rank(pct=True)

    score = (
        (index_close > sma200).astype(float)
        + (sma50 > sma200).astype(float)
        + (vol_pct < 0.8).astype(float)
    )
    regime = pd.Series(np.where(score >= 3, 1.0, np.where(score >= 2, 0.5, 0.0)), index=index_close.index)
    return regime


def apply_regime(weights: pd.DataFrame, regime: pd.Series) -> pd.DataFrame:
    aligned = regime.reindex(weights.index).ffill().fillna(0.0)
    return weights.mul(aligned, axis=0)


def regohm_signal(index_close: pd.Series) -> pd.Series:
    sma10 = sma(index_close.to_frame(), 10).iloc[:, 0]
    return (index_close > sma10).astype(float)


def regime_dashboard(index_close: pd.Series) -> Dict[str, float]:
    r = market_regime(index_close)
    last = r.iloc[-1]
    vol = (index_close.pct_change().rolling(20).std() * np.sqrt(252)).iloc[-1]
    sma50 = sma(index_close.to_frame(), 50).iloc[:, 0].iloc[-1]
    sma200 = sma(index_close.to_frame(), 200).iloc[:, 0].iloc[-1]
    return {
        "regime_multiplier": float(last),
        "realized_vol_annual": float(vol),
        "above_sma50_200": bool(sma50 > sma200),
        "regime_history_on_ratio": float((r == 1.0).mean()),
    }
