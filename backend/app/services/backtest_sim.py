import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class SimConfig:
    initial_cash: float = 100_000.0
    cost_per_side: float = 0.001
    max_weight: float = 0.10
    periods_per_year: int = 52


def resample_close(close: pd.DataFrame, freq: str = "W-FRI") -> pd.DataFrame:
    return close.resample(freq).last().dropna(how="all")


def compute_metrics(equity: pd.Series, cfg: SimConfig) -> Dict[str, float]:
    ret = equity.pct_change().dropna()
    total = equity.iloc[-1] / equity.iloc[0] - 1
    n = len(equity)
    ann_ret = (1 + total) ** (cfg.periods_per_year / max(n - 1, 1)) - 1
    ann_vol = ret.std() * np.sqrt(cfg.periods_per_year)
    sharpe = ret.mean() / ret.std() * np.sqrt(cfg.periods_per_year) if ret.std() > 0 else 0.0
    downside = ret[ret < 0].std() * np.sqrt(cfg.periods_per_year)
    sortino = ret.mean() * cfg.periods_per_year / downside if downside > 0 else 0.0
    dd = equity / equity.cummax() - 1
    max_dd = float(dd.min())
    calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0.0
    return {
        "total_return": total,
        "ann_return": ann_ret,
        "ann_vol": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_dd,
        "calmar": calmar,
    }


def round_trip_stats(close: pd.DataFrame, weights: pd.DataFrame) -> Tuple[Dict[str, float], int]:
    profits: List[float] = []
    for sym in weights.columns:
        r = close[sym].pct_change().fillna(0.0)
        mask = (weights[sym] > 0).astype(bool)
        pos_ids = (mask != mask.shift(1, fill_value=False)).cumsum()[mask]
        if pos_ids.empty:
            continue
        for idx in pos_ids.groupby(pos_ids).groups.values():
            seg = (1 + r.loc[list(idx)]).prod() - 1
            profits.append(seg)
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    profit_factor = (
        sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else float("inf") if wins else 0.0
    )
    stats = {
        "profit_factor": profit_factor,
        "avg_trade_return": float(np.mean(profits)) if profits else 0.0,
        "cumulative_trade_profit": float(sum(profits)),
    }
    return stats, len(profits)


def simulate(
    close: pd.DataFrame,
    target_weights: pd.DataFrame,
    cfg: SimConfig = SimConfig(),
) -> Dict[str, object]:
    aligned = target_weights.reindex(close.index).ffill().fillna(0.0).clip(0, cfg.max_weight)
    shifted = aligned.shift(1).fillna(0.0)
    returns_wk = close.pct_change().fillna(0.0)
    turnover = (shifted - shifted.shift(1)).abs().sum(axis=1)
    gross = (shifted * returns_wk).sum(axis=1)
    net = gross - turnover * cfg.cost_per_side
    equity = (1 + net).cumprod() * cfg.initial_cash

    metrics = compute_metrics(equity, cfg)
    trade_stats, n_trades = round_trip_stats(close, aligned)
    return {
        **metrics,
        **trade_stats,
        "total_trades": n_trades,
        "equity_curve": equity,
    }


def sma_crossover_weights(close: pd.DataFrame, fast: int = 10, slow: int = 30) -> pd.DataFrame:
    f = close.rolling(fast).mean()
    s = close.rolling(slow).mean()
    in_pos = (f > s).astype(int).replace(0, np.nan).ffill().fillna(0)
    active = in_pos.sum(axis=1)
    weights = in_pos.div(active.where(active > 0, 1), axis=0).where(in_pos > 0, 0.0)
    return weights


def rsi_mean_reversion_weights(
    close: pd.DataFrame,
    rsi_period: int = 14,
    oversold: int = 30,
    overbought: int = 70,
) -> pd.DataFrame:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(rsi_period).mean()
    loss = (-delta.clip(upper=0)).rolling(rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    entry = (rsi < oversold) & (rsi.shift(1) >= oversold)
    exit_sig = (rsi > overbought) & (rsi.shift(1) <= overbought)
    in_pos = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for sym in close.columns:
        state = 0.0
        series = []
        for i in range(len(close)):
            if entry[sym].iloc[i] and state == 0.0:
                state = 1.0
            elif exit_sig[sym].iloc[i] and state == 1.0:
                state = 0.0
            series.append(state)
        in_pos[sym] = series
    active = in_pos.sum(axis=1)
    weights = in_pos.div(active.where(active > 0, 1), axis=0).where(in_pos > 0, 0.0)
    return weights


def buy_and_hold_weights(close: pd.DataFrame) -> pd.DataFrame:
    n = close.shape[1]
    return pd.DataFrame(1.0 / n, index=close.index, columns=close.columns)
