import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from app.services.algorithms import rsi, sma, ema, zscore, momentum, volatility, macd

logger = logging.getLogger(__name__)


@dataclass
class MLV2Config:
    horizon_days: int = 21
    train_size: int = 252
    test_size: int = 63
    step_size: int = 63
    purge_gap: int = 25
    n_estimators: int = 300
    learning_rate: float = 0.05
    max_depth: int = 4
    reg_lambda: float = 10.0
    subsample: float = 0.8
    colsample: float = 0.8
    model_dir: str = "models/ml_v2"


def build_features(close: pd.DataFrame, high: Optional[pd.DataFrame] = None, low: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    if high is None:
        high = close
    if low is None:
        low = close
    feats = []
    m = macd(close)
    bb_mid = sma(close, 20)
    bb_sd = close.rolling(20).std()
    bb_pctb = (close - (bb_mid - 2 * bb_sd)) / (4 * bb_sd)

    def add(meta: Dict[str, pd.DataFrame], prefix: str):
        for k, v in meta.items():
            feats.append(v.stack().rename(f"{prefix}_{k}"))

    add(
        {
            "ret5": close.pct_change(5),
            "mom21": momentum(close, 21),
            "mom63": momentum(close, 63),
            "vol21": volatility(close, 21),
            "rsi14": rsi(close, 14) / 100.0,
            "sma_gap": close / sma(close, 50) - 1,
            "bb_pctb": bb_pctb.clip(-0.5, 1.5),
            "z20": zscore(close, 20),
            "macd_norm": m["line"] / close,
            "macd_hist_norm": m["hist"] / close,
            "gap_high": close / high - 1,
            "gap_low": close / low - 1,
        },
        "f",
    )
    frame = pd.concat(feats, axis=1)

    m21 = momentum(close, 21)
    m63 = momentum(close, 63)
    vol_w = volatility(close, 21)
    rsi_w = rsi(close, 14)
    def xsec(meta: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        out = []
        for k, v in meta.items():
            out.append(v.rank(axis=1, pct=True).stack().rename(f"x_{k}"))
        return pd.concat(out, axis=1)

    xsec_frame = xsec(
        {
            "mom21": m21,
            "mom63": m63,
            "vol21": vol_w,
            "rsi14": rsi_w,
            "sma_gap": close / sma(close, 50) - 1,
        }
    )
    frame = pd.concat([frame, xsec_frame], axis=1)
    frame = frame.sort_index()
    return frame


def build_labels(close: pd.DataFrame, horizon: int) -> pd.Series:
    fwd = close.pct_change(horizon).shift(-horizon)
    y = (fwd > 0).astype(float)
    return y.stack()


def purged_walk_forward_splits(
    index: pd.DatetimeIndex, cfg: MLV2Config
) -> List[tuple]:
    """Splits by unique DAYS (stacked index is (date, symbol) rows)."""
    dates = index.get_level_values(0)
    first_pos = pd.Series(np.arange(len(index)), index=dates).groupby(level=0).first()
    day_first_row = first_pos.sort_index().values
    n_days = len(day_first_row)
    splits = []
    start = cfg.train_size
    while start + cfg.test_size <= n_days:
        tr_end_row = day_first_row[start - cfg.purge_gap]
        te_start_row = day_first_row[start]
        te_end_row = (
            day_first_row[start + cfg.test_size]
            if start + cfg.test_size < n_days
            else len(index)
        )
        splits.append((0, tr_end_row, te_start_row, te_end_row))
        start += cfg.step_size
    return splits


def isotonic_calibration(probs: np.ndarray, labels: np.ndarray) -> object:
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(probs, labels)
    return iso


def train_fold_cfg_models(cfg: MLV2Config, X_train, y_train):
    import xgboost as xgb
    import lightgbm as lgb

    xgb_model = xgb.XGBClassifier(
        n_estimators=cfg.n_estimators,
        learning_rate=cfg.learning_rate,
        max_depth=cfg.max_depth,
        reg_lambda=cfg.reg_lambda,
        subsample=cfg.subsample,
        colsample_bytree=cfg.colsample,
        eval_metric="logloss",
        tree_method="hist",
        verbosity=0,
        n_jobs=1,
    )
    lgb_model = lgb.LGBMClassifier(
        n_estimators=cfg.n_estimators,
        learning_rate=cfg.learning_rate,
        max_depth=cfg.max_depth,
        reg_lambda=cfg.reg_lambda,
        subsample=cfg.subsample,
        colsample_bytree=cfg.colsample,
        verbose=-1,
        n_jobs=1,
        deterministic=True,
    )
    xgb_model.fit(X_train, y_train)
    lgb_model.fit(X_train, y_train)
    return xgb_model, lgb_model


def run_walk_forward(
    close: pd.DataFrame,
    high: Optional[pd.DataFrame] = None,
    low: Optional[pd.DataFrame] = None,
    cfg: Optional[MLV2Config] = None,
) -> Dict[str, object]:
    from sklearn.metrics import roc_auc_score, brier_score_loss

    cfg = cfg or MLV2Config()
    feats = build_features(close, high, low)
    labels = build_labels(close, cfg.horizon_days)
    aligned = feats.join(labels.rename("label"), how="inner")

    aligned = aligned.replace([np.inf, -np.inf], np.nan).dropna()
    y = aligned["label"].values
    X = aligned.drop(columns=["label"])
    splits = purged_walk_forward_splits(aligned.index, cfg)

    results = []
    calibrators = []
    def _dt(ts):
        d, _ = ts if isinstance(ts, tuple) else (ts, None)
        return str(pd.Timestamp(d).date())
    for i, (tr_start, tr_end, te_start, te_end) in enumerate(splits):
        X_tr, y_tr = X.iloc[tr_start:tr_end], y[tr_start:tr_end]
        X_te, y_te = X.iloc[te_start:te_end], y[te_start:te_end]
        if len(X_te) == 0 or len(np.unique(y_te)) < 2:
            continue
        xgb_m, lgb_m = train_fold_cfg_models(cfg, X_tr, y_tr)
        p_xgb = xgb_m.predict_proba(X_te)[:, 1]
        p_lgb = lgb_m.predict_proba(X_te)[:, 1]
        proba = 0.5 * p_xgb + 0.5 * p_lgb
        auc = roc_auc_score(y_te, proba)
        brier = brier_score_loss(y_te, proba)
        high_dec = proba >= np.quantile(proba, 0.8)
        hit_rate = float(y_te[high_dec].mean()) if high_dec.sum() > 0 else 0.0
        base_rate = float(y_te.mean())
        results.append(
            {
                "fold": i,
                "train_range": (_dt(X.index[tr_start]), _dt(X.index[tr_end - 1])),
                "test_range": (_dt(X.index[te_start]), _dt(X.index[te_end - 1])),
                "auc": float(auc),
                "brier": float(brier),
                "top_decile_hit_rate": hit_rate,
                "base_rate": base_rate,
            }
        )
        cal = isotonic_calibration(proba, y_te)
        calibrators.append({"fold": i, "calib": cal,
                            "models": (xgb_m, lgb_m),
                            "feature_names": list(X.columns)})
        logger.info(f"Fold {i}: AUC {auc:.3f} hit@p80 {hit_rate:.1%} vs base {base_rate:.1%}")

    top_decile = [r["top_decile_hit_rate"] for r in results]
    base_rates = [r["base_rate"] for r in results]
    aucs = [r["auc"] for r in results]
    summary = {
        "horizon_days": cfg.horizon_days,
        "n_folds": len(results),
        "mean_auc": float(np.mean(aucs)) if aucs else None,
        "mean_top_decile_hit_rate": float(np.mean(top_decile)) if top_decile else None,
        "mean_base_rate": float(np.mean(base_rates)) if base_rates else None,
        "edge_top_decile": (
            float(np.mean(top_decile) - np.mean(base_rates)) if results else None
        ),
        "folds": results,
        "feature_names": list(X.columns),
    }
    return summary


def save_summary_dir(cfg: MLV2Config, summary: Dict[str, object], market: str) -> Path:
    d = Path(cfg.model_dir)
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"summary_{market}.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    return out
