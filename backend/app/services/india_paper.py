import logging
import uuid
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models import Position, Order, Fill

logger = logging.getLogger(__name__)

PAPER_ONLY = True  # this engine can NEVER route to a live broker


class IndiaPaperEngine:
    """NSE paper-trading engine. Fills at last available close +/- slippage;
    tracks cash/positions in-memory and persists orders/fills/positions to DB
    (Order/Fill reuse; alpaca_order_id column carries a paper: prefix)."""

    def __init__(self):
        self.slippage_bps = 5.0
        self.cash: float = 1_000_000.0  # ₹10L demo pot
        self.positions: Dict[str, Dict] = {}  # symbol -> {qty, avg_px}
        self.initial_cash: float = self.cash
        self._touched = False

    # ---------- pricing ----------
    async def _last_price(self, symbol: str) -> Optional[float]:
        try:
            from app.services.market_in import market_data_service

            df = await market_data_service.fetch_nse_ohlcv(symbol, period="5d")
            if df.empty or "Close" not in df.columns:
                return None
            px = float(df["Close"].dropna().iloc[-1])
            return px if px > 0 else None
        except Exception as e:
            logger.warning(f"No price for {symbol}: {e}")
            return None

    def _fill_px(self, side: str, px: float) -> float:
        s = self.slippage_bps / 10_000
        return px * (1 + s) if side == "buy" else px * (1 - s)

    # ---------- account ----------
    def market_value(self, prices: Dict[str, float]) -> float:
        return sum(p["qty"] * prices.get(s, p["avg_px"]) for s, p in self.positions.items())

    def equity(self, prices: Dict[str, float]) -> float:
        return self.cash + self.market_value(prices)

    # ---------- actions ----------
    async def market_order(self, symbol: str, side: str, qty: float,
                           strategy: str = "manual", comment: str = "") -> Dict:
        if not PAPER_ONLY:
            raise RuntimeError("refusing live order")
        side = side.lower()
        if side not in ("buy", "sell"):
            return {"ok": False, "error": "side must be buy or sell"}
        qty = float(qty)
        if qty <= 0:
            return {"ok": False, "error": "qty must be positive"}

        px = await self._last_price(symbol)
        if px is None:
            return {"ok": False, "error": f"no price available for {symbol}"}
        fill_px = self._fill_px(side, px)
        notional = fill_px * qty

        pos = self.positions.setdefault(symbol, {"qty": 0.0, "avg_px": 0.0})
        if side == "buy":
            if notional > self.cash:
                return {"ok": False, "error": f"insufficient cash: need ₹{notional:.0f}, have ₹{self.cash:.0f}"}
            new_qty = pos["qty"] + qty
            pos["avg_px"] = (
                (pos["avg_px"] * pos["qty"] + fill_px * qty) / new_qty if new_qty else 0
            )
            pos["qty"] = new_qty
            self.cash -= notional
        else:
            if pos["qty"] <= 0:
                return {"ok": False, "error": f"no long position in {symbol} to sell"}
            sell_qty = min(qty, pos["qty"])
            realized = sell_qty * (fill_px - pos["avg_px"])
            pos["qty"] -= sell_qty
            self.cash += sell_qty * fill_px
            if pos["qty"] == 0:
                self.positions.pop(symbol, None)

        self._touched = True
        order_id = f"paper:{uuid.uuid4().hex[:20]}"
        await self._persist_order_fill(symbol, side, qty, fill_px, order_id, strategy, comment)
        return {
            "ok": True,
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "fill_price": round(fill_px, 2),
            "cash_after": round(self.cash, 2),
        }

    async def positions_snapshot(self) -> List[Dict]:
        out = []
        for s, p in self.positions.items():
            px = await self._last_price(s)
            cur = px if px else p["avg_px"]
            mv = p["qty"] * cur
            out.append(
                {
                    "symbol": s,
                    "qty": p["qty"],
                    "avg_px": round(p["avg_px"], 2),
                    "current_price": round(cur, 2),
                    "market_value": round(mv, 2),
                    "unrealized_pnl": round(mv - p["qty"] * p["avg_px"], 2),
                }
            )
        return out

    def account_summary(self, prices: Dict[str, float]) -> Dict:
        eq = self.equity(prices)
        return {
            "paper_only": PAPER_ONLY,
            "currency": "INR",
            "cash": round(self.cash, 2),
            "market_value": round(self.market_value(prices), 2),
            "equity": round(eq, 2),
            "return_on_initial": round(eq / self.initial_cash - 1, 4),
        }

    # ---------- persistence ----------
    async def _persist_order_fill(self, symbol: str, side: str, qty: float,
                                  fill_px: float, order_id: str,
                                  strategy: str, comment: str) -> None:
        try:
            async with async_session_maker() as session:
                o = Order(
                    alpaca_order_id=order_id,
                    client_order_id=strategy,
                    symbol=symbol[:20],
                    side=side,
                    type="market",
                    time_in_force="day",
                    qty=Decimal(str(qty)),
                    filled_qty=Decimal(str(qty)),
                    filled_avg_price=Decimal(str(round(fill_px, 4))),
                    status="filled",
                    submitted_at=datetime.utcnow(),
                    filled_at=datetime.utcnow(),
                )
                session.add(o)
                await session.flush()
                session.add(
                    Fill(
                        order_id=o.id,
                        alpaca_trade_id=f"{order_id}:fill",
                        symbol=symbol[:20],
                        side=side,
                        qty=Decimal(str(qty)),
                        price=Decimal(str(round(fill_px, 4))),
                        timestamp=datetime.utcnow(),
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"paper persistence failed: {e}")


india_paper = IndiaPaperEngine()
