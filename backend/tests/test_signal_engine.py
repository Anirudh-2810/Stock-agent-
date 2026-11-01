import pandas as pd

from app.services.signal_engine import SIGNAL_WEIGHTS, signal_engine


def test_signal_weights_sum_to_one():
    assert abs(sum(SIGNAL_WEIGHTS.values()) - 1.0) < 1e-9


def test_compute_signal_short_frame_is_hold():
    df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    result = signal_engine.compute_signal(df)
    assert result["action"] == "HOLD"
    assert result["score"] == 0.0
    assert result["confidence"] == 0.0


def test_classify_thresholds():
    assert signal_engine._classify(0.4) == "BUY"
    assert signal_engine._classify(-0.4) == "SELL"
    assert signal_engine._classify(0.39) == "HOLD"
    assert signal_engine._classify(-0.39) == "HOLD"
    assert signal_engine._classify(0.0) == "HOLD"


def test_confidence_is_clamped():
    assert signal_engine._confidence(0.9) == 0.9
    assert signal_engine._confidence(2.0) == 1.0
    assert signal_engine._confidence(-2.0) == 1.0
    assert signal_engine._confidence(0.1) == 0.3
