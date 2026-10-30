import json
import logging
import sys

sys.path.insert(0, "E:/Brain/stock-agent/backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

import pandas as pd
import yfinance as yf

from app.services.ml_v2 import MLV2Config, run_walk_forward, save_summary_dir

US_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "V", "XOM", "UNH",
    "JNJ", "PG", "CVX", "HD", "ABBV", "BAC", "KO", "PFE", "DIS", "CSCO",
    "NFLX", "INTC", "WMT", "CRM", "MCD",
]
IN_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "ITC.NS", "LT.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS",
    "MARUTI.NS", "TATAMOTORS.NS", "TATASTEEL.NS", "SUNPHARMA.NS", "HINDUNILVR.NS",
    "BAJFINANCE.NS", "WIPRO.NS", "HCLTECH.NS", "ADANIENT.NS", "ONGC.NS",
    "NTPC.NS", "POWERGRID.NS", "M&M.NS", "TITAN.NS", "ASIANPAINT.NS",
    "ULTRACEMCO.NS", "NESTLEIND.NS", "TECHM.NS", "JSWSTEEL.NS",
]
START = "2019-01-01"


def fetch_panel(symbols):
    df = yf.download(symbols, start=START, progress=False, auto_adjust=True)
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    valid = [s for s in symbols if s in close.columns and close[s].notna().sum() > 500]
    return close[valid], high[valid], low[valid]


def main():
    cfg = MLV2Config(test_size=126, step_size=126, horizon_days=5, model_dir="models/ml_v2")
    for market, symbols in [("us", US_SYMBOLS), ("in", IN_SYMBOLS)]:
        close, high, low = fetch_panel(symbols)
        print(f"=== {market}: {close.shape[1]} symbols, {len(close)} days ===")
        summary = run_walk_forward(close, high, low, cfg)
        print(json.dumps({k: v for k, v in summary.items() if k not in ("folds", "feature_names")}, indent=2, default=str))
        path = save_summary_dir(cfg, summary, market)
        print(f"saved: {path}")


if __name__ == "__main__":
    main()
