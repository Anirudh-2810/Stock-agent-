from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import List, Dict, Optional
from datetime import date, timedelta
import pandas as pd
import numpy as np
import logging

from app.core.database import get_db
from app.core.security import verify_api_key
from app.services.backtest_engine import (
    VectorBTBacktester, BacktestConfig, BacktestResult,
    create_sma_crossover_signals, create_rsi_mean_reversion_signals
)
from app.services.ml_features import ml_feature_engine
from app.services.ml_pipeline import MLTrainingPipeline, ScheduledModelRetrain
from app.services.model_registry import model_registry, inference_service
from app.services.xgboost_trainer import ModelConfig, WalkForwardValidator
from app.models import OHLCV
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"], dependencies=[Depends(verify_api_key)])


@router.post("/run")
async def run_backtest(
    background_tasks: BackgroundTasks,
    symbols: List[str] = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    strategy: str = Query("ml_predictions"),
    initial_cash: float = 100000,
    commission: float = 0.0005,
    slippage: float = 0.0005,
    model_name: Optional[str] = None,
    model_version: str = "production",
    threshold: float = 0.0,
    position_sizing: str = "equal",
    fast: int = Query(10),
    slow: int = Query(30),
    rsi_period: int = Query(14),
    oversold: int = Query(30),
    overbought: int = Query(70),
):
    async for db in get_db():
        ohlcv_query = text("""
            SELECT time, symbol, close FROM ohlcv
            WHERE symbol = ANY(:symbols) AND time BETWEEN :start AND :end
        """)
        result = await db.execute(ohlcv_query, {
            "symbols": symbols,
            "start": start_date,
            "end": end_date,
        })
        ohlcv_rows = result.fetchall()
        
        if not ohlcv_rows:
            raise HTTPException(status_code=404, detail="No OHLCV data for period")
        
        ohlcv_df = pd.DataFrame(ohlcv_rows, columns=['time', 'symbol', 'close'])
        ohlcv_df['time'] = pd.to_datetime(ohlcv_df['time'])
        
        bt_config = BacktestConfig(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            commission=commission,
            slippage=slippage,
        )
        
        backtester = VectorBTBacktester(bt_config)
        backtester.load_price_data(ohlcv_df)
        
        if strategy == "ml_predictions":
            if not model_name:
                raise HTTPException(status_code=400, detail="model_name required for ML strategy")
            
            features_df = await ml_feature_engine.load_weekly_features(
                db, symbols, start_date, end_date
            )
            
            if features_df.empty:
                raise HTTPException(status_code=404, detail="No features for period")
            
            features_df = ml_feature_engine.add_derived_features(features_df)
            
            X, _, _ = ml_feature_engine.create_ml_dataset(features_df)
            
            predictions = inference_service.predict(model_name, X, model_version)
            
            pred_df = pd.DataFrame({
                "prediction": predictions,
                "symbol": features_df.loc[X.index, "symbol"].values,
                "as_of_date": features_df.loc[X.index, "as_of_date"].values,
            })
            pred_df = pred_df.pivot_table(
                index="as_of_date",
                columns="symbol",
                values="prediction",
                aggfunc="last",
            ).reindex(columns=symbols)
            
            bt_result = backtester.run_from_predictions(
                pred_df,
                threshold=threshold,
                position_sizing=position_sizing,
            )
        
        elif strategy == "sma_crossover":
            signals = create_sma_crossover_signals(backtester.price_data, fast, slow)
            bt_result = backtester.run_long_only(
                entry_signals=signals['entries'],
                exit_signals=signals['exits'],
            )
        
        elif strategy == "rsi_mean_reversion":
            signals = create_rsi_mean_reversion_signals(
                backtester.price_data, rsi_period, oversold, overbought
            )
            bt_result = backtester.run_long_only(
                entry_signals=signals['entries'],
                exit_signals=signals['exits'],
            )
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy}")
        
        return {
            "config": bt_config.__dict__,
            "metrics": bt_result.metrics,
            "total_return": bt_result.total_return,
            "annualized_return": bt_result.annualized_return,
            "sharpe_ratio": bt_result.sharpe_ratio,
            "sortino_ratio": bt_result.sortino_ratio,
            "max_drawdown": bt_result.max_drawdown,
            "calmar_ratio": bt_result.calmar_ratio,
            "win_rate": bt_result.win_rate,
            "profit_factor": bt_result.profit_factor,
            "total_trades": bt_result.total_trades,
            "avg_trade_return": bt_result.avg_trade_return,
            "equity_curve": bt_result.equity_curve.to_dict(),
            "trades": bt_result.trades.to_dict('records') if not bt_result.trades.empty else [],
        }


@router.post("/parameter-sweep")
async def parameter_sweep(
    symbols: List[str] = Query(...),
    start_date: date = Query(...),
    end_date: date = Query(...),
    strategy: str = Query("sma_crossover"),
    param_grid: Optional[Dict] = Body(None),
    initial_cash: float = 100000,
    commission: float = 0.0005,
    slippage: float = 0.0005,
):
    async for db in get_db():
        ohlcv_query = text("""
            SELECT time, symbol, close FROM ohlcv
            WHERE symbol = ANY(:symbols) AND time BETWEEN :start AND :end
        """)
        result = await db.execute(ohlcv_query, {
            "symbols": symbols,
            "start": start_date,
            "end": end_date,
        })
        ohlcv_rows = result.fetchall()
        
        if not ohlcv_rows:
            raise HTTPException(status_code=404, detail="No OHLCV data")
        
        ohlcv_df = pd.DataFrame(ohlcv_rows, columns=['time', 'symbol', 'close'])
        ohlcv_df['time'] = pd.to_datetime(ohlcv_df['time'])
        
        bt_config = BacktestConfig(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_cash=initial_cash,
            commission=commission,
            slippage=slippage,
        )
        
        backtester = VectorBTBacktester(bt_config)
        backtester.load_price_data(ohlcv_df)
        
        if strategy == "sma_crossover":
            default_grid = {
                "fast_period": [5, 10, 15, 20],
                "slow_period": [20, 30, 40, 50, 60],
            }
            grid = param_grid or default_grid
            
            def signal_func(fast_period, slow_period):
                return create_sma_crossover_signals(backtester.price_data, fast_period, slow_period)
            
            results_df = backtester.parameter_sweep(grid, signal_func)
        
        elif strategy == "rsi_mean_reversion":
            default_grid = {
                "rsi_period": [10, 14, 21],
                "oversold": [20, 25, 30, 35],
                "overbought": [65, 70, 75, 80],
            }
            grid = param_grid or default_grid
            
            def signal_func(rsi_period, oversold, overbought):
                return create_rsi_mean_reversion_signals(backtester.price_data, rsi_period, oversold, overbought)
            
            results_df = backtester.parameter_sweep(grid, signal_func)
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy}")
        
        return {
            "results": results_df.to_dict('records'),
            "best_sharpe": results_df.loc[results_df['Sharpe Ratio'].idxmax()].to_dict() if not results_df.empty else None,
            "best_return": results_df.loc[results_df['Total Return [%]'].idxmax()].to_dict() if not results_df.empty else None,
        }


@router.post("/train")
async def train_model(
    background_tasks: BackgroundTasks,
    symbols: List[str] = Query(...),
    train_start: date = Query(...),
    train_end: date = Query(...),
    target_horizon: int = 4,
    task: str = "classification",
    model_type: str = "xgboost",
    n_estimators: int = 300,
    max_depth: int = 5,
    learning_rate: float = 0.05,
    run_walk_forward: bool = True,
    n_splits: int = 5,
):
    model_config = ModelConfig(
        model_type=model_type,
        task=task,
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        eval_metric='auc' if task == 'classification' else 'rmse',
    )
    
    pipeline = MLTrainingPipeline(
        symbols=symbols,
        train_start=train_start,
        train_end=train_end,
        target_horizon=target_horizon,
    )
    
    def run_training():
        import asyncio
        return asyncio.run(pipeline.run_training(model_config, run_walk_forward, n_splits))
    
    background_tasks.add_task(run_training)
    
    return {
        "message": "Training started in background",
        "config": model_config.__dict__,
        "symbols": symbols,
        "date_range": f"{train_start} to {train_end}",
    }


@router.get("/models")
async def list_models():
    return {"models": model_registry.list_models()}


@router.get("/models/{name}/{version}")
async def get_model_info(name: str, version: str = "production"):
    try:
        info = inference_service.get_model_info(name, version)
        return info
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Model not found")


@router.post("/models/{name}/{version}/promote")
async def promote_model(name: str, version: str):
    success = model_registry.promote_to_production(name, version)
    if not success:
        raise HTTPException(status_code=404, detail="Model version not found")
    return {"success": True, "message": f"Model {name}:{version} promoted to production"}


@router.post("/predict")
async def predict(
    model_name: str = Query(...),
    symbols: List[str] = Query(...),
    as_of_date: date = Query(...),
    model_version: str = "production",
    return_proba: bool = False,
):
    async for db in get_db():
        features_df = await ml_feature_engine.load_weekly_features(
            db, symbols, as_of_date, as_of_date
        )
        
        if features_df.empty:
            raise HTTPException(status_code=404, detail="No features for date")
        
        features_df = ml_feature_engine.add_derived_features(features_df)
        
        X, _, _ = ml_feature_engine.create_ml_dataset(features_df)
        
        predictions = inference_service.predict(
            model_name, X, model_version, return_proba=return_proba
        )
        
        return {
            "model": model_name,
            "version": model_version,
            "as_of_date": as_of_date.isoformat(),
            "predictions": dict(zip(symbols, predictions.tolist())),
        }


@router.post("/walk-forward")
async def run_walk_forward(
    symbols: List[str] = Query(...),
    train_start: date = Query(...),
    train_end: date = Query(...),
    target_horizon: int = 4,
    task: str = "classification",
    n_splits: int = 5,
    test_size: int = 52,
    gap: int = 4,
):
    model_config = ModelConfig(
        model_type='xgboost',
        task=task,
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
    )
    
    pipeline = MLTrainingPipeline(
        symbols=symbols,
        train_start=train_start,
        train_end=train_end,
        target_horizon=target_horizon,
    )
    
    async for db in get_db():
        features_df = await ml_feature_engine.load_weekly_features(
            db, symbols, train_start, train_end
        )
        
        if features_df.empty:
            raise HTTPException(status_code=404, detail="No features for period")
        
        features_df = ml_feature_engine.add_derived_features(features_df)
        
        X, y_reg, y_clf = ml_feature_engine.create_ml_dataset(
            features_df, target_horizon=target_horizon
        )
        
        dates = features_df.loc[X.index, 'as_of_date']
        y = y_clf if task == 'classification' else y_reg
        
        validator = WalkForwardValidator(
            n_splits=n_splits,
            test_size=test_size,
            gap=gap,
            expanding=True,
        )
        
        results = validator.validate(
            XGBoostTrainer,
            model_config,
            X, y, dates,
        )
        
        agg = validator.aggregate_results(results)
        
        return {
            "config": model_config.__dict__,
            "aggregated_metrics": agg,
            "fold_results": [
                {
                    "train_metrics": r.train_metrics,
                    "val_metrics": r.val_metrics,
                    "test_metrics": r.test_metrics,
                    "feature_importance": dict(list(r.feature_importance.items())[:20]),
                }
                for r in results
            ],
        }


@router.post("/retrain-weekly")
async def trigger_weekly_retrain(background_tasks: BackgroundTasks, symbols: List[str] = Query(...)):
    retrainer = ScheduledModelRetrain(symbols=symbols)
    
    def run_retrain():
        import asyncio
        return asyncio.run(retrainer.retrain_weekly())
    
    background_tasks.add_task(run_retrain)
    
    return {"message": "Weekly retrain triggered", "symbols": symbols}