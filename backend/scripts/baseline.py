import sys
import pandas as pd
import yfinance as yf

sys.path.insert(0, "E:/Brain/stock-agent/backend")

from app.services.backtest_sim import (
    SimConfig,
    resample_close,
    simulate,
    sma_crossover_weights,
    rsi_mean_reversion_weights,
    buy_and_hold_weights,
)

US_SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "V", "JNJ"]
IN_SYMBOLS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS"]
START = "2022-01-01"


def fetch(symbols):
    df = yf.download(symbols, start=START, progress=False, auto_adjust=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(symbols[0])
    return df.dropna(axis=1, how="all")


def run_market(name, symbols, close):
    weekly = resample_close(close)
    rows = []
    buy = buy_and_hold_weights(weekly)
    rows.append(("buy_and_hold", simulate(weekly, buy)))
    for label, fn in [
        ("sma_cross 10/30", sma_crossover_weights),
        ("rsi_mr 14", rsi_mean_reversion_weights),
    ]:
        w = fn(weekly)
        rows.append((label, simulate(weekly, w)))
    print(f"\n=== {name} (weekly, cost 10bps/side, max weight 10%) ===")
    print(f"{'strategy':<15} {'total':>8} {'ann':>8} {'vol':>7} {'sharpe':>7} {'srt':>6} {'maxDD':>8} {'pf':>6} {'trades':>7}")
    for label, m in rows:
        pf = m["profit_factor"]
        print(
            f"{label:<15} {m['total_return']:>8.1%} {m['ann_return']:>8.1%} {m['ann_vol']:>7.1%} "
            f"{m['sharpe']:>7.2f} {m['sortino']:>6.2f} {m['max_drawdown']:>8.1%} "
            f"{pf if pf != float('inf') else 99:>6.1f} {m['total_trades']:>7d}"
        )


def main():
    us = fetch(US_SYMBOLS)
    ind = fetch(IN_SYMBOLS)
    print(f"US data: {us.index[0].date()} -> {us.index[-1].date()} ({len(us)} days)")
    print(f"IN data: {ind.index[0].date()} -> {ind.index[-1].date()} ({len(ind)} days)")
    run_market("S&P 500 sample", US_SYMBOLS, us)
    run_market("NSE sample", IN_SYMBOLS, ind)


if __name__ == "__main__":
    main()
