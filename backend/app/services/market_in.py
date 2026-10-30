import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List

import httpx
import pandas as pd
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import FiiDiiFlow

logger = logging.getLogger(__name__)

NIFTY50 = [
    "RELIANCE.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "TCS.NS", "ITC.NS",
    "LT.NS", "BHARTIARTL.NS", "KOTAKBANK.NS", "SBIN.NS", "AXISBANK.NS", "M&M.NS",
    "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "HINDUNILVR.NS",
    "HINDALCO.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "ULTRACEMCO.NS", "GRASIM.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "BAJAJ-AUTO.NS",
    "EICHERMOT.NS", "HEROMOTOCO.NS", "NESTLEIND.NS", "POWERGRID.NS",
    "NTPC.NS", "TATAPOWER.NS", "ONGC.NS", "COALINDIA.NS", "IOC.NS", "BPCL.NS",
    "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS",
    "APOLLOHOSP.NS", "DLF.NS", "INDUSINDBK.NS", "SBILIFE.NS", "HDFCLIFE.NS", "LTIM.NS",
]

NSE_BASE = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/global-market-data",
}


class NSEClient:
    def fetch_fii_dii(self) -> List[Dict]:
        with httpx.Client(headers=NSE_HEADERS, timeout=15, follow_redirects=True) as c:
            c.get(f"{NSE_BASE}/global-market-data")
            r = c.get(f"{NSE_BASE}/api/fiidiiTradeReact")
            r.raise_for_status()
            return r.json()

    def fetch_bhavcopy_url(self, d: date) -> str:
        mm = d.strftime("%b").upper()
        return (
            f"{NSE_BASE.replace('www', 'archives')}/content/historical/EQUITIES/"
            f"{d.year}/{mm}/cm{d.strftime('%d')}{mm}{d.year}bhav.csv.zip"
        )


class MarketDataService:
    def __init__(self):
        self.nse = NSEClient()

    async def fetch_fii_dii(self) -> List[Dict]:
        return await asyncio.to_thread(self.nse.fetch_fii_dii)

    @staticmethod
    def _parse_nse_date(s: str) -> date:
        return datetime.strptime(s, "%d-%b-%Y").date()

    @staticmethod
    def _to_float(v) -> float:
        if v in (None, "", "-"):
            return 0.0
        return float(str(v).replace(",", ""))

    async def sync_fii_dii(self) -> Dict:
        raw = await self.fetch_fii_dii()
        inserted, updated, skipped = 0, 0, 0
        async with async_session_maker() as session:
            try:
                for row in raw:
                    fd = self._parse_nse_date(row.get("date", ""))
                    cat = row.get("category", "")
                    buy = self._to_float(row.get("buyValue"))
                    sell = self._to_float(row.get("sellValue"))
                    net = self._to_float(row.get("netValue"))

                    existing = (
                        await session.execute(
                            select(FiiDiiFlow).where(
                                FiiDiiFlow.flow_date == fd, FiiDiiFlow.category == cat
                            )
                        )
                    ).scalar_one_or_none()
                    if existing:
                        if (existing.buy_value_cr, existing.sell_value_cr, existing.net_value_cr) != (buy, sell, net):
                            existing.buy_value_cr = buy
                            existing.sell_value_cr = sell
                            existing.net_value_cr = net
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        session.add(
                            FiiDiiFlow(
                                flow_date=fd,
                                category=cat,
                                buy_value_cr=buy,
                                sell_value_cr=sell,
                                net_value_cr=net,
                            )
                        )
                        inserted += 1
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        logger.info(f"FII/DII sync: {inserted} inserted, {updated} updated, {skipped} unchanged")
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "rows": len(raw)}

    async def get_fii_dii_series(self, days: int = 60) -> List[Dict]:
        since = date.today() - timedelta(days=days)
        async with async_session_maker() as session:
            result = await session.execute(
                select(FiiDiiFlow)
                .where(FiiDiiFlow.flow_date >= since)
                .order_by(FiiDiiFlow.flow_date)
            )
            return [
                {
                    "date": r.flow_date.isoformat(),
                    "category": r.category,
                    "net_value_cr": float(r.net_value_cr or 0),
                }
                for r in result.scalars()
            ]

    async def fetch_nse_ohlcv(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        import yfinance as yf

        def _fetch():
            return yf.download(symbol, period=period, progress=False, auto_adjust=True)

        df = await asyncio.to_thread(_fetch)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df


market_data_service = MarketDataService()
