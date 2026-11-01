from datetime import date

import pandas as pd

from app.services.ml_features import ml_feature_engine


def test_ml_dataset_has_no_cross_symbol_leakage():
    df = pd.DataFrame({
        "symbol": ["AAPL", "AAPL", "AAPL", "MSFT", "MSFT", "MSFT"],
        "as_of_date": [date(2026, 1, 6), date(2026, 1, 13), date(2026, 1, 20),
                       date(2026, 1, 6), date(2026, 1, 13), date(2026, 1, 20)],
        "fwd_ret_4w": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
        "ret_1w": [0.005, 0.01, 0.015, float("nan"), 0.04, 0.05],
    })

    X, y_reg, y_clf = ml_feature_engine.create_ml_dataset(df, target_horizon=4)

    # MSFT's first ret_1w was NaN; after group-wise ffill + fillna(0) it must be the
    # neutral fill (0.0), NOT AAPL's last observed value (0.015).
    assert float(X.loc[3, "ret_1w"]) == 0.0
    assert float(X.loc[0, "ret_1w"]) == 0.005
    assert float(X.loc[2, "ret_1w"]) == 0.015
    assert float(X.loc[4, "ret_1w"]) == 0.04
    assert float(X.loc[5, "ret_1w"]) == 0.05
