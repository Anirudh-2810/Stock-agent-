import sys
import pandas as pd
import yfinance as yf

sys.path.insert(0, "E:/Brain/stock-agent/backend")

from app.services.algorithms import (
    sma_cross_adx_weights,
    donchian_breakout_weights,
    momentum_weights,
    bollinger_zscore_weights,
    rsi2_weights,
)
from app.services.backtest_sim import (
    resample_close,
    simulate,
    buy_and_hold_weights,
)
from app.services.regime_engine import market_regime, apply_regime

US_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "V", "JNJ"]
IN_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS",
]
INDICES = {"US": "^GSPC", "IN": "^NSEI"}
START = "2022-01-01"

STRATEGIES = [
    ("sma_adx", sma_cross_adx_weights),
    ("donchian30", donchian_breakout_weights),
    ("momentum24", momentum_weights),
    ("boll_z", bollinger_zscore_weights),
    ("rsi2", rsi2_weights),
]

BEST_MONTHS_FRI = "W-FRI"


def fetch_panel(symbols):
    df = yf.download(symbols, start=START, progress=False, auto_adjust=True)
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    valid = [s for s in symbols if s in close.columns and close[s].notna().sum() > 200]
    return close[valid], high[valid], low[valid]


def fetch_index(market):
    t = INDICES[market]
    df = yf.download(t, start=START, progress=False, auto_adjust=True, interval="1d")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close


def to_weekly_high_low(high, low, close):
    wh = high.resample(BEST_MONTHS_FRI).max()
    wl = low.resample(BEST_MONTHS_FRI).min()
    return wh, wl


def run_market(market, symbols, close, high, low, index_close):
    weekly = resample_close(close)
    wh = high.resample(BEST_MONTHS_FRI).max().reindex(weekly.index)
    wl = low.resample(BEST_MONTHS_FRI).min().reindex(weekly.index)
    regime_daily = market_regime(index_close)
    regime_weekly = regime_daily.resample(BEST_MONTHS_FRI).last().reindex(weekly.index).ffill().fillna(0.0)

    rows = [(f"buy_and_hold", simulate(weekly, buy_and_hold_weights(weekly)))]
    for name, fn in STRATEGIES:
        try:
            if name == "sma_adx":
                w = fn(weekly, high=wh, low=wl)
            else:
                w = fn(weekly)
            rows.append((f"{name}", simulate(weekly, w)))
            rows.append((f"{name}+regime", simulate(weekly, apply_regime(w, regime_weekly))))
        except Exception as e:
            rows.append((f"{name} -- ERROR: {e}", None))

    print(f"\n=== {market} (weekly, 10bps/side, max 10%) regime@weekly ===")
    print(f"{'strategy':<16} {'total':>8} {'ann':>8} {'vol':>7} {'sharpe':>7} {'maxDD':>8} {'pf':>7} {'trades':>7}")
    for label, m in rows:
        if m is None:
            print(f"{label}")
            continue
        pf = m["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.1f}"
        print(
            f"{label:<16} {m['total_return']:>8.1%} {m['ann_return']:>8.1%} "
            f"{m['ann_vol']:>7.1%} {m['sharpe']:>7.2f} {m['max_drawdown']:>8.1%} "
            f"{pf_s:>7} {m['total_trades']:>7d}"
        )


def main():
    for market, symbols in [("US", US_SYMBOLS), ("IN", IN_SYMBOLS)]:
        close, high, low = fetch_panel(symbols)
        index_close = fetch_index(market)
        print(f"{market}: panel {close.shape}, index {index_close.index[0].date()} -> {index_close.index[-1].date()}")
        run_market(market, symbols, close, high, low, index_close)


if __name__ == "__main__":
    main()
