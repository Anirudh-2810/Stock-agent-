from datetime import date, timedelta, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
import logging
import asyncio

from app.services.ml_features import ml_feature_engine
from app.services.xgboost_trainer import XGBoostTrainer, ModelConfig, WalkForwardValidator
from app.services.model_registry import model_registry
from app.services.backtest_engine import VectorBTBacktester, BacktestConfig
from app.core.database import async_session_maker

logger = logging.getLogger(__name__)


class MLTrainingPipeline:
    def __init__(
        self,
        symbols: List[str],
        train_start: date,
        train_end: date,
        target_horizon: int = 4,
    ):
        self.symbols = symbols
        self.train_start = train_start
        self.train_end = train_end
        self.target_horizon = target_horizon
    
    async def run_training(
        self,
        model_config: ModelConfig,
        run_walk_forward: bool = True,
        n_splits: int = 5,
    ) -> Dict:
        logger.info(f"Starting ML training pipeline for {len(self.symbols)} symbols")
        
        async with async_session_maker() as db:
            features_df = await ml_feature_engine.load_weekly_features(
                db, self.symbols, self.train_start, self.train_end
            )
            
            if features_df.empty:
                raise ValueError("No features found for training period")
            
            logger.info(f"Loaded features: {features_df.shape}")
            
            features_df = ml_feature_engine.add_derived_features(features_df)
            
            X, y_reg, y_clf = ml_feature_engine.create_ml_dataset(
                features_df, target_horizon=self.target_horizon
            )
            
            logger.info(f"Created dataset: X={X.shape}, y_reg={y_reg.shape}, y_clf={y_clf.shape}")
            
            dates = features_df.loc[X.index, 'as_of_date']
            
            if run_walk_forward:
                validator = WalkForwardValidator(
                    n_splits=n_splits,
                    test_size=52,
                    gap=4,
                    expanding=True,
                )
                
                task = model_config.task
                results = validator.validate(
                    XGBoostTrainer,
                    model_config,
                    X, y_clf if task == 'classification' else y_reg,
                    dates,
                )
                
                agg_metrics = validator.aggregate_results(results)
                logger.info(f"Walk-forward validation results: {agg_metrics}")
                
                best_fold = np.argmax([r.val_metrics.get('auc', r.val_metrics.get('r2', 0)) for r in results])
                best_result = results[best_fold]
                
                model_name = f"xgb_{task}_weekly_{self.target_horizon}w"
                version = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                model_key = model_registry.register_model(
                    model=best_result.model,
                    name=model_name,
                    version=version,
                    config=model_config.__dict__,
                    metrics={
                        "train": best_result.train_metrics,
                        "val": best_result.val_metrics,
                        "test": best_result.test_metrics,
                        "walk_forward": agg_metrics,
                    },
                    feature_names=list(best_result.feature_importance.keys()),
                    mlflow_run_id=best_result.mlflow_run_id,
                )
                
                return {
                    "model_key": model_key,
                    "walk_forward_results": agg_metrics,
                    "best_fold": int(best_fold),
                    "feature_importance": best_result.feature_importance,
                    "best_model_metrics": {
                        "train": best_result.train_metrics,
                        "val": best_result.val_metrics,
                        "test": best_result.test_metrics,
                    },
                }
            else:
                split_idx = int(len(X) * 0.7)
                val_split_idx = int(len(X) * 0.85)
                
                X_train, X_val, X_test = X[:split_idx], X[split_idx:val_split_idx], X[val_split_idx:]
                y_train = (y_clf if model_config.task == 'classification' else y_reg)[:split_idx]
                y_val = (y_clf if model_config.task == 'classification' else y_reg)[split_idx:val_split_idx]
                y_test = (y_clf if model_config.task == 'classification' else y_reg)[val_split_idx:]
                
                trainer = XGBoostTrainer(model_config)
                result = trainer.train(
                    X_train, y_train, X_val, y_val, X_test, y_test, log_to_mlflow=True
                )
                
                model_name = f"xgb_{model_config.task}_weekly_{self.target_horizon}w"
                version = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                
                model_key = model_registry.register_model(
                    model=result.model,
                    name=model_name,
                    version=version,
                    config=model_config.__dict__,
                    metrics={
                        "train": result.train_metrics,
                        "val": result.val_metrics,
                        "test": result.test_metrics,
                    },
                    feature_names=list(result.feature_importance.keys()),
                    mlflow_run_id=result.mlflow_run_id,
                )
                
                return {
                    "model_key": model_key,
                    "single_split_results": result.test_metrics,
                    "feature_importance": result.feature_importance,
                }
    
    async def run_backtest_validation(
        self,
        model_name: str,
        version: str = "production",
        backtest_start: Optional[date] = None,
        backtest_end: Optional[date] = None,
    ) -> Dict:
        logger.info(f"Running backtest validation for {model_name}:{version}")
        
        from app.services.model_registry import inference_service
        from app.core.database import async_session_maker
        
        if backtest_start is None:
            backtest_start = self.train_end + timedelta(weeks=1)
        if backtest_end is None:
            backtest_end = date.today()
        
        async with async_session_maker() as db:
            features_df = await ml_feature_engine.load_weekly_features(
                db, self.symbols, backtest_start, backtest_end
            )
            
            if features_df.empty:
                raise ValueError("No features for backtest period")
            
            features_df = ml_feature_engine.add_derived_features(features_df)
            
            X, _, _ = ml_feature_engine.create_ml_dataset(
                features_df, target_horizon=self.target_horizon
            )
            
            predictions = inference_service.predict(model_name, X, version)
            
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
            ).reindex(columns=self.symbols)
            
            ohlcv_query = """
                SELECT time, symbol, close FROM ohlcv
                WHERE symbol = ANY(:symbols) AND time BETWEEN :start AND :end
            """
            result = await db.execute(ohlcv_query, {
                "symbols": self.symbols,
                "start": backtest_start,
                "end": backtest_end,
            })
            ohlcv_rows = result.fetchall()
            
            if not ohlcv_rows:
                raise ValueError("No OHLCV data for backtest")
            
            ohlcv_df = pd.DataFrame(ohlcv_rows, columns=['time', 'symbol', 'close'])
            ohlcv_df['time'] = pd.to_datetime(ohlcv_df['time'])
            
            bt_config = BacktestConfig(
                symbols=self.symbols,
                start_date=backtest_start,
                end_date=backtest_end,
            )
            
            backtester = VectorBTBacktester(bt_config)
            backtester.load_price_data(ohlcv_df)
            
            bt_result = backtester.run_from_predictions(
                pred_df,
                threshold=0.0,
                position_sizing='equal',
            )
            
            return {
                "backtest_metrics": bt_result.metrics,
                "total_return": bt_result.total_return,
                "sharpe_ratio": bt_result.sharpe_ratio,
                "max_drawdown": bt_result.max_drawdown,
                "total_trades": bt_result.total_trades,
                "equity_curve": bt_result.equity_curve.to_dict(),
            }


class ScheduledModelRetrain:
    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.pipeline = None
    
    async def retrain_weekly(self):
        train_end = date.today() - timedelta(weeks=1)
        train_start = train_end - timedelta(weeks=104)
        
        self.pipeline = MLTrainingPipeline(
            symbols=self.symbols,
            train_start=train_start,
            train_end=train_end,
            target_horizon=4,
        )
        
        clf_config = ModelConfig(
            model_type='xgboost',
            task='classification',
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            eval_metric='auc',
        )
        
        reg_config = ModelConfig(
            model_type='xgboost',
            task='regression',
            n_estimators=300,
            max_depth=5,
            learning_rate=0.05,
            eval_metric='rmse',
        )
        
        clf_result = await self.pipeline.run_training(clf_config, run_walk_forward=True)
        reg_result = await self.pipeline.run_training(reg_config, run_walk_forward=True)
        
        logger.info(f"Weekly retrain complete: clf={clf_result['model_key']}, reg={reg_result['model_key']}")
        
        return {"classifier": clf_result, "regressor": reg_result}