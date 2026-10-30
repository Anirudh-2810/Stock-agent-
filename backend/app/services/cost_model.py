from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class CostModel:
    market: str
    stt_pct: float = 0.0
    stamp_pct_buy: float = 0.0
    exchange_pct: float = 0.0
    sebi_pct: float = 0.0
    brokerage_max_pct: float = 0.0
    brokerage_min_per_order: float = 0.0
    dp_per_sell_order: float = 0.0
    gst_on_fees: float = 0.0
    slippage_pct: float = 0.0

    def side_cost_fraction(self, side: str, turnover: float) -> float:
        stt = self.stt_pct
        stamp = self.stamp_pct_buy if side == "buy" else 0.0
        sebi = self.sebi_pct
        exch = self.exchange_pct
        brokerage = min(
            self.brokerage_max_pct if turnover > 0 else 0.0,
            self.brokerage_min_per_order / turnover if turnover > 0 else 0.0,
        )
        dp = self.dp_per_sell_order / turnover if (side == "sell" and self.dp_per_sell_order > 0 and turnover > 0) else 0.0
        gst = self.gst_on_fees * (brokerage + exch + sebi)
        return stt + stamp + exch + sebi + brokerage + dp + gst + self.slippage_pct


COST_MODELS: Dict[str, CostModel] = {
    "in": CostModel(
        market="in",
        stt_pct=0.001,
        stamp_pct_buy=0.00015,
        exchange_pct=0.0000297,
        sebi_pct=0.000001,
        brokerage_max_pct=0.0003,
        brokerage_min_per_order=20.0,
        dp_per_sell_order=15.53,
        gst_on_fees=0.18,
        slippage_pct=0.0005,
    ),
    "us": CostModel(
        market="us",
        stt_pct=0.0,
        stamp_pct_buy=0.0,
        exchange_pct=0.000028,
        sebi_pct=0.0,
        brokerage_max_pct=0.0,
        brokerage_min_per_order=0.0,
        dp_per_sell_order=0.0,
        gst_on_fees=0.0,
        slippage_pct=0.0003,
    ),
}


def side_cost(market: str, side: str, turnover: float) -> float:
    return COST_MODELS[market].side_cost_fraction(side, turnover)


def summary(market: str, sample_order_value: float = 100_000.0) -> Dict[str, float]:
    m = COST_MODELS[market]
    return {
        "market": m.market,
        "buy_cost_pct": m.side_cost_fraction("buy", sample_order_value) * 100,
        "sell_cost_pct": m.side_cost_fraction("sell", sample_order_value) * 100,
        "round_trip_pct_on_sample": (
            m.side_cost_fraction("buy", sample_order_value)
            + m.side_cost_fraction("sell", sample_order_value)
        ) * 100,
    }
