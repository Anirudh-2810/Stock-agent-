import numpy as np
import pandas as pd
from typing import Dict, Optional


def sma(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return close.rolling(n).mean()


def ema(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return close.ewm(span=n, adjust=False).mean()


def rsi(close: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.DataFrame]:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False).mean()
    return {"line": line, "signal": sig, "hist": line - sig}


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    prev = close.shift(1)
    a = high - low
    b = (high - prev).abs()
    c = (low - prev).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def atr(
    high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14
) -> pd.DataFrame:
    tr = pd.DataFrame(
        {
            sym: true_range(high[sym], low[sym], close[sym])
            for sym in close.columns
        },
        index=close.index,
    )
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def adx(
    high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14
) -> pd.DataFrame:
    up = high.diff()
    down = -low.diff()
    plus_dm = up.clip(lower=0).where(up > down, 0.0)
    minus_dm = down.clip(lower=0).where(down > up, 0.0)
    tr_n = atr(high, low, close, n)
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr_n.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / tr_n.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def bollinger(close: pd.DataFrame, n: int = 20, k: float = 2.0) -> Dict[str, pd.DataFrame]:
    mid = sma(close, n)
    sd = close.rolling(n).std()
    upper = mid + k * sd
    lower = mid - k * sd
    pctb = (close - lower) / (upper - lower)
    return {"mid": mid, "upper": upper, "lower": lower, "pctb": pctb}


def zscore(close: pd.DataFrame, n: int) -> pd.DataFrame:
    mean = close.rolling(n).mean()
    sd = close.rolling(n).std()
    return (close - mean) / sd.where(sd > 0)


def momentum(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return close.pct_change(n)


def volatility(close: pd.DataFrame, n: int = 20, annualize: float = 252.0) -> pd.DataFrame:
    return close.pct_change().rolling(n).std() * np.sqrt(annualize)


def donchian(high: pd.DataFrame, low: pd.DataFrame, n: int) -> Dict[str, pd.DataFrame]:
    upper = high.rolling(n).max().shift(1)
    lower = low.rolling(n).min().shift(1)
    return {"upper": upper, "lower": lower}


def equal_split(positions: pd.DataFrame) -> pd.DataFrame:
    active = positions.sum(axis=1)
    return positions.div(active.where(active > 0, 1), axis=0).where(positions > 0, 0.0)


def _hold_state(entry: pd.DataFrame, exit_sig: pd.DataFrame) -> pd.DataFrame:
    state = pd.DataFrame(0.0, index=entry.index, columns=entry.columns)
    for sym in entry.columns:
        cur = 0.0
        states = []
        for i in range(len(entry)):
            if entry[sym].iloc[i]:
                cur = 1.0
            elif exit_sig[sym].iloc[i]:
                cur = 0.0
            states.append(cur)
        state[sym] = states
    return state


def sma_cross_adx_weights(
    close: pd.DataFrame,
    high: Optional[pd.DataFrame] = None,
    low: Optional[pd.DataFrame] = None,
    fast: int = 10,
    slow: int = 30,
    adx_n: int = 14,
    adx_min: float = 20.0,
) -> pd.DataFrame:
    if high is None:
        high = close
    if low is None:
        low = close
    f, s = sma(close, fast), sma(close, slow)
    trend_on = (adx(high, low, close, adx_n) >= adx_min) | (adx(high, low, close, adx_n).isna())
    positions = (f > s).astype(float) * trend_on.astype(float)
    return equal_split(positions)


def donchian_breakout_weights(
    close: pd.DataFrame,
    high: Optional[pd.DataFrame] = None,
    low: Optional[pd.DataFrame] = None,
    n: int = 30,
) -> pd.DataFrame:
    if high is None:
        high = close
    if low is None:
        low = close
    bands = donchian(high, low, n)
    entry = close >= bands["upper"]
    exit_sig = close <= bands["lower"]
    state = _hold_state(entry, exit_sig)
    return equal_split(state)


def momentum_weights(close: pd.DataFrame, lookback: int = 24, top_k: int = 3) -> pd.DataFrame:
    mom = close.pct_change(lookback)
    ranks = mom.rank(axis=1, ascending=False)
    positions = (ranks <= top_k).astype(float)
    positions = positions.where(mom.notna(), 0.0)
    return equal_split(positions)


def bollinger_zscore_weights(
    close: pd.DataFrame, n: int = 20, entry: float = -2.0, exit_z: float = 0.0
) -> pd.DataFrame:
    z = zscore(close, n)
    entry = (z <= entry) & (z.shift(1) > entry)
    exit_sig = (z >= exit_z) & (z.shift(1) < exit_z)
    return equal_split(_hold_state(entry.fillna(False), exit_sig.fillna(False)))


def rsi2_weights(close: pd.DataFrame, oversold: float = 10.0, exit_level: float = 65.0) -> pd.DataFrame:
    r = rsi(close, 2)
    entry = (r <= oversold) & (r.shift(1) > oversold)
    exit_sig = (r >= exit_level) & (r.shift(1) < exit_level)
    return equal_split(_hold_state(entry.fillna(False), exit_sig.fillna(False)))
