import numpy as np
import pandas as pd
from typing import Dict, Optional

from app.core.database import async_session_maker
from app.models import FiiDiiFlow
from sqlalchemy import select


def fii_flow_regime(fii_net_series: pd.Series, z_window: int = 90, crash_z: float = -2.0, hot_z: float = 1.0) -> pd.Series:
    s = fii_net_series.dropna().sort_index()
    if s.empty:
        return pd.Series(dtype=float)
    rolling = s.rolling(5).sum()
    mean = rolling.rolling(z_window, min_periods=21).mean()
    sd = rolling.rolling(z_window, min_periods=21).std()
    z = (rolling - mean) / sd.replace(0, np.nan)
    mult = pd.Series(np.where(z <= crash_z, 0.5, np.where(z >= hot_z, 1.0, 1.0)), index=z.index)
    return mult.fillna(1.0)


async def load_fii_series() -> pd.Series:
    async with async_session_maker() as session:
        result = await session.execute(
            select(FiiDiiFlow)
            .where(FiiDiiFlow.category == "FII/FPI")
            .order_by(FiiDiiFlow.flow_date)
        )
        rows = [
            (r.flow_date, float(r.net_value_cr or 0))
            for r in result.scalars()
        ]
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series(dict(rows))


async def india_alpha_factor(days: int = 120) -> Dict[str, float]:
    s = await load_fii_series()
    if len(s) < 10:
        return {"available": False, "reason": "insufficient FII history (TBC: needs historical backfill)"}
    mult = fii_flow_regime(s)
    return {
        "available": True,
        "current_multiplier": float(mult.iloc[-1]),
        "fii_net_5d_cr": float(s.rolling(5).sum().iloc[-1]),
        "fii_net_total_cr": float(s.sum()),
        "days_of_data": int(len(s)),
    }
