import logging
from datetime import datetime, date
from typing import Dict, List, Optional

import httpx

from app.services.market_in import NSE_BASE, NSE_HEADERS
from app.services.india_paper import PAPER_ONLY

logger = logging.getLogger(__name__)

# EXPERIMENTAL MODULE - paper-only, high-hook-rate premium-sell ideas.
# These signals are NOT reliable long-only edge; they are explicitly labelled
# experimental and must never be routed to a live broker. The loss caps below
# are execution-guard-style overlays for paper testing only.

PAPER_ONLY = True

STRADDLE_THRESHOLD_PCT = 2.0  # ATM straddle premium >= 2% of spot -> elevated IV
MIN_OPTIONOI_INFO = 0.4  # fraction of options rows with lastPrice > 0


class OptionChainClient:
    def fetch_nifty_chain(self, symbol: str = "NIFTY") -> Optional[Dict]:
        url = f"{NSE_BASE}/api/option-chain-indices?symbol={symbol}"
        try:
            with httpx.Client(headers=NSE_HEADERS, timeout=20, follow_redirects=True) as c:
                c.get(f"{NSE_BASE}/option-chain")
                r = c.get(url, headers={"Referer": f"{NSE_BASE}/option-chain"})
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.warning(f"option chain fetch failed for {symbol}: {e}")
            return None


def extract_atm_records(chain: Dict) -> Optional[Dict]:
    """Find records whose strike is nearest to underlying spot."""
    try:
        spot = chain["records"]["underlyingValue"]
        rows = chain["records"]["data"]
        if not rows:
            return None
        nearest = min(rows, key=lambda r: abs(r["strikePrice"] - spot))
        ce, pe = nearest.get("CE", {}), nearest.get("PE", {})
        ce_px = ce.get("lastPrice", 0) or 0
        pe_px = pe.get("lastPrice", 0) or 0
        straddle = ce_px + pe_px
        return {
            "spot": float(spot),
            "strike": int(nearest["strikePrice"]),
            "expiry": nearest.get("expiryDate"),
            "call_price": float(ce_px),
            "put_price": float(pe_px),
            "straddle_premium": float(straddle),
            "straddle_pct_of_spot": round(straddle / spot * 100, 2) if spot else None,
            "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"chain parse failed: {e}")
        return None


class OptionsPremiumModule:
    PAPER_ONLY = True  # class-level: enforced

    def __init__(self):
        self.client = OptionChainClient()
        self.history: List[Dict] = []  # in-memory; DB snapshot table later

    def straddle_wrap(self, symbol: str = "NIFTY") -> Dict:
        """EXPERIMENTAL high-hook-rate idea: paper short-straddle when ATM
        straddle premium is elevated vs spot. Returns an idea card, never an order."""
        if not PAPER_ONLY or not self.PAPER_ONLY:
            raise RuntimeError("refusing to run outside paper mode")
        chain = self.client.fetch_nifty_chain(symbol)
        if not chain:
            return {
                "available": False,
                "experimental": True,
                "reason": "NSE option-chain endpoint blocked for scripted access (as of 2026-10-30); FII/DII endpoint still works, so block is chain-specific",
                "fallback": "retry during off-peak windows or surface idea via browser-session dashboards",
            }
        atm = extract_atm_records(chain)
        if not atm:
            return {"available": False, "reason": "no ATM record parsed", "experimental": True}
        self.history.append(atm)
        pct = atm["straddle_pct_of_spot"]
        idea = None
        if pct is not None and pct >= STRADDLE_THRESHOLD_PCT:
            idea = {
                "type": "sell straddle (paper)",
                "symbol": symbol,
                "strike": atm["strike"],
                "expiry": atm["expiry"],
                "premium_collected": atm["straddle_premium"],
                "budget_cap": 100_000,  # ₹ paper loss cap, guard-style
                "stop_rule": "close straddle if NIFTY closes 2% beyond strike",
                "rationale": "premium elevated vs spot (experimental IV proxy)",
                "warnings": ["unbounded upside risk on short straddle", "paper-only, cut from live execution"],
            }
        return {
            "available": True,
            "experimental": True,
            "atm": atm,
            "threshold_pct": STRADDLE_THRESHOLD_PCT,
            "idea": idea,
        }

    def status(self) -> Dict:
        return {
            "module": "options_premium",
            "experimental": True,
            "paper_only": PAPER_ONLY,
            "snapshots_cached": len(self.history),
        }


options_premium = OptionsPremiumModule()
