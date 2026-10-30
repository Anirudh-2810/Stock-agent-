import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class EventConfig:
    initial_cash: float = 1_000_000.0
    market: str = "us"
    order_value: float = 100_000.0
    max_positions: int = 8
    position_fraction: float = 0.12
    stop_atr_mult: float = 3.0  # 0 disables stops
    slippage_bps: float = 2.0
    min_qty: float = 1.0
    periods_per_year: int = 252


@dataclass
class _Pos:
    qty: float = 0.0
    entry_px: float = 0.0
    entry_date: Optional[pd.Timestamp] = None
    stop: float = 0.0


def compute_metrics_event(equity: pd.Series, cfg: EventConfig) -> Dict[str, float]:
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
        "total_return": float(total),
        "ann_return": float(ann_ret),
        "ann_vol": float(ann_vol),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "max_drawdown": max_dd,
        "calmar": float(calmar),
    }


def atr_df(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    """Wilder ATR on wide frames."""
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=0,
    )
    tr = tr.groupby(level=0).max()
    tr = tr.reindex(columns=close.columns)
    return tr.ewm(alpha=1.0 / n, min_periods=n).mean()


def run_event_backtest(
    open_px: pd.DataFrame,
    high: pd.DataFrame,
    low: pd.DataFrame,
    close: pd.DataFrame,
    target_signal: pd.DataFrame,
    cfg: EventConfig,
) -> Dict[str, object]:
    """Position-level long-only simulator.

    target_signal: bool DataFrame, decided at close of bar t, executed at open
    of bar t+1. Entry fills at next open + slippage; exit fills at next open -
    slippage when signal off; ATR stop exits intrabar at stop level (filled at
    open if the bar gaps through it). Costs via cost_model per side.
    """
    from app.services.cost_model import COST_MODELS

    cm = COST_MODELS.get(cfg.market)
    slip = cfg.slippage_bps / 10_000.0

    syms = list(close.columns)
    idx = close.index
    o = np.column_stack([open_px[s].values for s in syms])
    l = np.column_stack([low[s].values for s in syms])
    c = np.column_stack([close[s].values for s in syms])
    sig_next = target_signal.reindex(idx).fillna(False).shift(1).fillna(False).values

    use_stops = cfg.stop_atr_mult > 0
    atr = atr_df(high, low, close, 14) if use_stops else None

    positions: Dict[int, _Pos] = {}
    cash = cfg.initial_cash
    equity_vals: List[float] = []
    trades: List[dict] = []

    def _close_position(i: int, j: int, fill_raw: float, reason: str) -> None:
        nonlocal cash
        p = positions[j]
        s = syms[j]
        fill_px = fill_raw * (1 - slip)
        proceeds = p.qty * fill_px
        fee = cm.side_cost_fraction("sell", cfg.order_value) * proceeds if cm else 0.0
        cash += proceeds - fee
        pnl = proceeds - fee - p.qty * p.entry_px * (1 + slip)
        trades.append(
            {
                "symbol": s,
                "entry_date": p.entry_date,
                "exit_date": idx[i],
                "entry_px": p.entry_px,
                "exit_px": fill_px,
                "qty": p.qty,
                "pnl": pnl,
                "pnl_pct": pnl / (p.qty * p.entry_px) if p.qty * p.entry_px else 0.0,
                "exit_reason": reason,
            }
        )
        del positions[j]

    for i in range(len(idx)):
        # 1) stop exits: intrabar if stop breached, filled at open on gap-down
        for j in list(positions.keys()):
            p = positions[j]
            if use_stops and p.stop > 0 and l[i, j] <= p.stop:
                _close_position(i, j, min(o[i, j], p.stop), "stop")

        # 2) signal-off exits at next open
        for j in list(positions.keys()):
            if not sig_next[i, j]:
                _close_position(i, j, o[i, j], "signal")

        # 3) equity snapshot for sizing
        holdings = sum(positions[j].qty * c[i, j] for j in positions)
        equity = cash + holdings

        # 4) entries at next open
        if sig_next[i].sum() > 0:
            slots = cfg.max_positions - len(positions)
            if slots > 0:
                notional = equity * cfg.position_fraction
                for j, s in enumerate(syms):
                    if slots <= 0:
                        break
                    if j in positions or not sig_next[i, j]:
                        continue
                    fill_px = o[i, j] * (1 + slip)
                    if not np.isfinite(fill_px) or fill_px <= 0:
                        continue
                    qty = notional / fill_px
                    cost = qty * fill_px
                    fee = cm.side_cost_fraction("buy", cfg.order_value) * cost if cm else 0.0
                    if cost + fee > cash:
                        qty = (cash - fee) / fill_px
                    if qty < cfg.min_qty:
                        continue
                    cost = qty * fill_px
                    fee = cm.side_cost_fraction("buy", cfg.order_value) * cost if cm else 0.0
                    cash -= cost + fee
                    stop_level = 0.0
                    if use_stops:
                        a = atr[s].iloc[i]
                        stop_level = c[i, j] - cfg.stop_atr_mult * a if np.isfinite(a) else 0.0
                    positions[j] = _Pos(
                        qty=qty,
                        entry_px=fill_px,
                        entry_date=idx[i],
                        stop=stop_level,
                    )
                    trades.append(
                        {
                            "symbol": s,
                            "entry_date": idx[i],
                            "exit_date": None,
                            "entry_px": fill_px,
                            "exit_px": None,
                            "qty": qty,
                            "pnl": None,
                            "pnl_pct": None,
                            "exit_reason": "entry",
                        }
                    )
                    slots -= 1

        holdings = sum(positions[j].qty * c[i, j] for j in positions)
        equity_vals.append(cash + holdings)

    equity_curve = pd.Series(equity_vals, index=idx)
    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        closed = trades_df
    else:
        closed = trades_df[trades_df["exit_reason"].isin(["stop", "signal"])]
    losses = closed.loc[closed["pnl"] <= 0, "pnl"].sum() if not closed.empty else 0.0
    wins_sum = closed.loc[closed["pnl"] > 0, "pnl"].sum() if not closed.empty else 0.0
    pf = float("inf") if (not closed.empty and losses == 0 and wins_sum > 0) else (
        wins_sum / (-losses) if losses < 0 else 0.0
    )
    open_positions = trades_df[trades_df["exit_reason"] == "entry"] if not trades_df.empty else trades_df
    result = {
        **compute_metrics_event(equity_curve, cfg),
        "win_rate": float((closed["pnl"] > 0).mean()) if len(closed) else 0.0,
        "profit_factor": pf,
        "n_round_trips": int(len(closed)),
        "n_open_at_end": int(len(open_positions)),
        "avg_trade_pnl_pct": float(closed["pnl_pct"].mean()) if len(closed) else 0.0,
        "equity_curve": equity_curve,
        "trades": trades_df,
    }
    return result


def buy_and_hold_event(open_px: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, cfg: EventConfig) -> Dict[str, object]:
    sig = pd.DataFrame(True, index=close.index, columns=close.columns)
    return run_event_backtest(open_px, high, low, close, sig, cfg)
