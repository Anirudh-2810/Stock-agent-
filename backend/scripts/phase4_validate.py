import logging
import sys

sys.path.insert(0, "E:/Brain/stock-agent/backend")
logging.basicConfig(level=logging.WARNING)

import pandas as pd
import yfinance as yf

from app.services.algorithms import sma
from app.services.regime_engine import market_regime, apply_regime
from app.services.event_backtest import EventConfig, run_event_backtest, buy_and_hold_event

SYM_US = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "V", "XOM", "UNH"]
SYM_IN = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
          "BHARTIARTL.NS", "ITC.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS"]
START = "2018-01-01"
KEYS = ("total_return", "ann_return", "ann_vol", "sharpe", "sortino", "max_drawdown", "n_round_trips", "win_rate")


def fetch(symbols):
    df = yf.download(symbols, start=START, progress=False, auto_adjust=True)
    valid = [s for s in symbols if s in df["Close"].columns and df["Close"][s].notna().sum() > 500]
    return df.loc[:, (slice(None), valid)]


def sma_cross_signal(close, fast=10, slow=50):
    f = sma(close, fast)
    s = sma(close, slow)
    long_ok = (f > s)
    return long_ok.where(long_ok.notna(), False).astype(bool)


def run_market(name, symbols, index_symbol, order_value):
    df = fetch(symbols)
    close = df["Close"]
    open_px = df["Open"]
    high = df["High"]
    low = df["Low"]

    bench = yf.download(index_symbol, start=START, progress=False, auto_adjust=True)["Close"]
    bench = bench.iloc[:, 0] if isinstance(bench, pd.DataFrame) else bench
    bench = bench.reindex(close.index).ffill()

    cfg = EventConfig(order_value=order_value, market=name, max_positions=8, position_fraction=0.12, stop_atr_mult=3.0)

    rows = []

    bh = buy_and_hold_event(open_px, high, low, close, cfg)
    rows.append({"strategy": "buy&hold", **{k: bh[k] for k in KEYS}})

    sig_raw = sma_cross_signal(close)
    ev = run_event_backtest(open_px, high, low, close, sig_raw, cfg)
    rows.append({"strategy": "sma10x50", **{k: ev[k] for k in KEYS}})

    regime_raw = market_regime(bench)
    if isinstance(regime_raw, pd.DataFrame):
        regime_raw = regime_raw.iloc[:, 0]
    regime = regime_raw.reindex(close.index).ffill().fillna(1.0)
    sig_gated = sig_raw & (regime > 0.0).values[:, None]
    evg = run_event_backtest(open_px, high, low, close, sig_gated, cfg)
    rows.append({"strategy": "sma10x50+regime", **{k: evg[k] for k in KEYS}})

    print(f"=== {name} (event-driven, daily, real costs+slippage+ATR stops) ===")
    print(pd.DataFrame(rows).round(3).to_string(index=False))


if __name__ == "__main__":
    run_market("us", SYM_US, "^GSPC", 50_000)
    run_market("in", SYM_IN, "^NSEI", 150_000)
