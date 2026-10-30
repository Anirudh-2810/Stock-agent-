from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.feature_engine import feature_store

logger = logging.getLogger(__name__)


SIGNAL_WEIGHTS = {
    "sma_cross": 0.25,
    "rsi": 0.20,
    "macd": 0.20,
    "momentum": 0.15,
    "volume": 0.10,
    "trend": 0.10,
}


class SignalEngine:
    """Computes per-symbol technical signals and blends with an optional ML prediction."""

    def __init__(self):
        self.weights = SIGNAL_WEIGHTS

    @staticmethod
    def _last(df: pd.DataFrame, col: str) -> Optional[float]:
        if col not in df.columns:
            return None
        series = df[col]
        if series.empty:
            return None
        value = series.iloc[-1]
        if pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _prev(df: pd.DataFrame, col: str) -> Optional[float]:
        if col not in df.columns or len(df) < 2:
            return None
        value = df[col].iloc[-2]
        if pd.isna(value):
            return None
        return float(value)

    @staticmethod
    def _score_sma_cross(fast: Optional[float], slow: Optional[float],
                         prev_fast: Optional[float], prev_slow: Optional[float]) -> float:
        if fast is None or slow is None or prev_fast is None or prev_slow is None:
            return 0.0
        if prev_fast <= prev_slow and fast > slow:
            return 1.0
        if prev_fast >= prev_slow and fast < slow:
            return -1.0
        # No cross today; score by relative position
        spread = (fast - slow) / (slow + 1e-9)
        return float(np.clip(spread * 40, -0.8, 0.8))

    @staticmethod
    def _score_rsi(rsi: Optional[float]) -> float:
        if rsi is None:
            return 0.0
        if rsi <= 30:
            return 1.0
        if rsi >= 70:
            return -1.0
        return float(np.clip((50 - rsi) / 40, -1.0, 1.0))

    @staticmethod
    def _score_macd(macd: Optional[float], signal: Optional[float]) -> float:
        if macd is None or signal is None:
            return 0.0
        return float(np.clip((macd - signal) / (abs(signal) + 1e-9) * 2, -1, 1))

    @staticmethod
    def _score_momentum(closes: pd.Series, lookbacks=(4, 12, 24)) -> float:
        if len(closes) < max(lookbacks) + 1:
            return 0.0
        total = 0.0
        for lb in lookbacks:
            ratio = closes.iloc[-1] / closes.iloc[-lb - 1] - 1
            total += float(np.clip(ratio * 20, -1, 1))
        return total / len(lookbacks)

    @staticmethod
    def _score_volume(volume: pd.Series, closes: pd.Series, look: int = 20) -> float:
        if len(volume) < look + 2:
            return 0.0
        avg_vol = volume.iloc[-(look + 1):-1].mean()
        if not avg_vol or avg_vol <= 0:
            return 0.0
        vol_ratio = volume.iloc[-1] / avg_vol
        price_up = closes.iloc[-1] >= closes.iloc[-2] if len(closes) >= 2 else False
        direction = 1 if price_up else -1
        return float(np.clip((vol_ratio - 1) * 2, -1, 1)) * direction

    @staticmethod
    def _score_trend(closes: pd.Series, ema50: Optional[float]) -> float:
        if ema50 is None:
            return 0.0
        above = closes.iloc[-1] > ema50
        rising = closes.iloc[-1] > closes.iloc[-5] if len(closes) >= 5 else False
        score = (0.5 if above else -0.5) + (0.5 if rising else -0.5)
        return float(np.clip(score, -1, 1))

    def compute_signal(
        self,
        df: pd.DataFrame,
        ml_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Compute a composite -1..1 signal for a single symbol's OHLCV frame."""
        if df is None or df.empty or len(df) < 30:
            return {"action": "HOLD", "score": 0.0, "technical_score": 0.0, "ml_score": None,
                    "confidence": 0.0, "components": {}}

        closes = df["close"]
        volume = df["volume"] if "volume" in df.columns else pd.Series(index=df.index, dtype=float)

        components = {}

        components["sma_cross"] = self._score_sma_cross(
            self._last(df, "sma_20"), self._last(df, "sma_50"),
            self._prev(df, "sma_20"), self._prev(df, "sma_50"),
        )

        components["rsi"] = self._score_rsi(self._last(df, "rsi_14"))

        components["macd"] = self._score_macd(
            self._last(df, "macd"), self._last(df, "macd_signal"),
        )

        components["momentum"] = self._score_momentum(closes)

        components["volume"] = self._score_volume(volume, closes)

        components["trend"] = self._score_trend(closes, self._last(df, "ema_50"))

        tech_score = sum(
            self.weights.get(name, 0.0) * components.get(name, 0.0)
            for name in self.weights
        )

        final_score = tech_score
        if ml_score is not None:
            final_score = 0.6 * tech_score + 0.4 * float(ml_score)

        action = self._classify(final_score)
        confidence = self._confidence(final_score)

        return {
            "action": action,
            "score": round(float(final_score), 4),
            "technical_score": round(float(tech_score), 4),
            "ml_score": round(float(ml_score), 4) if ml_score is not None else None,
            "confidence": round(float(confidence), 4),
            "components": {k: round(float(v), 4) for k, v in components.items()},
        }

    @staticmethod
    def _confidence(score: float) -> float:
        """Confidence scaled by how far score is from neutral."""
        return float(np.clip(abs(score), 0.3, 1.0))

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 0.4:
            return "BUY"
        if score <= -0.4:
            return "SELL"
        return "HOLD"

    async def scan_universe(
        self,
        db: AsyncSession,
        symbols: List[str],
        days: int = 250,
        model_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        results = []
        for symbol in symbols:
            try:
                df = await feature_store.compute_features(db, symbol, days)
                if df.empty:
                    results.append({"symbol": symbol, "action": "HOLD", "score": 0.0,
                                    "technical_score": 0.0, "ml_score": None,
                                    "confidence": 0.0, "error": "no data"})
                    continue

                prediction_score = None
                if model_name:
                    prediction_score = await self._get_ml_score(db, model_name, symbol)

                signal = self.compute_signal(df, prediction_score)
                results.append({"symbol": symbol, **signal})
            except Exception as e:
                logger.error(f"Signal scan failed for {symbol}: {e}")
                results.append({"symbol": symbol, "action": "HOLD", "score": 0.0,
                                "technical_score": 0.0, "ml_score": None,
                                "confidence": 0.0, "error": str(e)})

        results.sort(key=lambda r: r.get("score", 0.0), reverse=True)
        return results

    async def _get_ml_score(self, db: AsyncSession, model_name: str, symbol: str) -> Optional[float]:
        """Pull the latest ML model prediction probability for a symbol, if a model is trained."""
        try:
            from app.services.ml_features import ml_feature_engine
            from app.services.model_registry import inference_service

            today = date.today()
            features_df = await ml_feature_engine.load_weekly_features(
                db, [symbol], today - timedelta(days=14), today
            )
            if features_df.empty:
                return None
            features_df = ml_feature_engine.add_derived_features(features_df)
            X, _, _ = ml_feature_engine.create_ml_dataset(features_df)
            if X.empty:
                return None
            proba = inference_service.predict(
                model_name, X.iloc[[-1]], return_proba=True
            )
            p = float(proba[0])
            return (p - 0.5) * 2
        except Exception as e:
            logger.warning(f"ML score unavailable for {symbol}: {e}")
            return None


signal_engine = SignalEngine()