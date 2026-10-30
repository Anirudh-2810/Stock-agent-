import xgboost as xgb
import lightgbm as lgb
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import date
from dataclasses import dataclass, asdict
import json
import joblib
import logging
import warnings
import uuid

# MLflow is optional
try:
    import mlflow
    import mlflow.xgboost
    import mlflow.lightgbm
    MLFLOW_AVAILABLE = True
except ImportError:
    mlflow = None
    MLFLOW_AVAILABLE = False

from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, mean_squared_error, mean_absolute_error, r2_score
)
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)


@dataclass
class ModelConfig:
    model_type: str = 'xgboost'  # xgboost, lightgbm
    task: str = 'classification'  # classification, regression
    n_estimators: int = 200
    max_depth: int = 5
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0
    random_state: int = 42
    early_stopping_rounds: int = 20
    eval_metric: str = 'logloss'  # logloss, rmse, auc


@dataclass
class TrainingResult:
    model_config: ModelConfig
    train_metrics: Dict[str, float]
    val_metrics: Dict[str, float]
    test_metrics: Dict[str, float]
    feature_importance: Dict[str, float]
    model_path: str
    mlflow_run_id: Optional[str] = None


class XGBoostTrainer:
    def __init__(self, config: ModelConfig, experiment_name: str = "stock_agent"):
        self.config = config
        self.experiment_name = experiment_name
        self.model = None
        self.feature_names: List[str] = []
        
        if MLFLOW_AVAILABLE:
            mlflow.set_experiment(experiment_name)
    
    def _create_model(self):
        if self.config.model_type == 'xgboost':
            if self.config.task == 'classification':
                return xgb.XGBClassifier(
                    n_estimators=self.config.n_estimators,
                    max_depth=self.config.max_depth,
                    learning_rate=self.config.learning_rate,
                    subsample=self.config.subsample,
                    colsample_bytree=self.config.colsample_bytree,
                    reg_alpha=self.config.reg_alpha,
                    reg_lambda=self.config.reg_lambda,
                    random_state=self.config.random_state,
                    n_jobs=-1,
                    tree_method='hist',
                )
            else:
                return xgb.XGBRegressor(
                    n_estimators=self.config.n_estimators,
                    max_depth=self.config.max_depth,
                    learning_rate=self.config.learning_rate,
                    subsample=self.config.subsample,
                    colsample_bytree=self.config.colsample_bytree,
                    reg_alpha=self.config.reg_alpha,
                    reg_lambda=self.config.reg_lambda,
                    random_state=self.config.random_state,
                    n_jobs=-1,
                    tree_method='hist',
                )
        elif self.config.model_type == 'lightgbm':
            if self.config.task == 'classification':
                return lgb.LGBMClassifier(
                    n_estimators=self.config.n_estimators,
                    max_depth=self.config.max_depth,
                    learning_rate=self.config.learning_rate,
                    subsample=self.config.subsample,
                    colsample_bytree=self.config.colsample_bytree,
                    reg_alpha=self.config.reg_alpha,
                    reg_lambda=self.config.reg_lambda,
                    random_state=self.config.random_state,
                    n_jobs=-1,
                    verbose=-1,
                )
            else:
                return lgb.LGBMRegressor(
                    n_estimators=self.config.n_estimators,
                    max_depth=self.config.max_depth,
                    learning_rate=self.config.learning_rate,
                    subsample=self.config.subsample,
                    colsample_bytree=self.config.colsample_bytree,
                    reg_alpha=self.config.reg_alpha,
                    reg_lambda=self.config.reg_lambda,
                    random_state=self.config.random_state,
                    n_jobs=-1,
                    verbose=-1,
                )
        else:
            raise ValueError(f"Unknown model type: {self.config.model_type}")
    
    def train(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame,
        y_val: pd.Series,
        X_test: Optional[pd.DataFrame] = None,
        y_test: Optional[pd.Series] = None,
        log_to_mlflow: bool = True,
    ) -> TrainingResult:
        self.feature_names = list(X_train.columns)
        self.model = self._create_model()
        
        if MLFLOW_AVAILABLE and log_to_mlflow:
            mlflow.set_experiment(self.experiment_name)
            mlflow_context = mlflow.start_run()
            mlflow_context.__enter__()
            run_id = mlflow.active_run().info.run_id
        else:
            run_id = str(uuid.uuid4())
        
        try:
            if MLFLOW_AVAILABLE:
                mlflow.log_params(asdict(self.config))
                mlflow.log_param("n_features", len(self.feature_names))
                mlflow.log_param("train_samples", len(X_train))
                mlflow.log_param("val_samples", len(X_val))
            
            if self.config.model_type == 'xgboost':
                self.model.fit(
                    X_train, y_train,
                    eval_set=[(X_val, y_val)],
                    eval_metric=self.config.eval_metric,
                    early_stopping_rounds=self.config.early_stopping_rounds,
                    verbose=False,
                )
            else:
                self.model.fit(
                    X_train, y_train,
                    eval_set=[(X_val, y_val)],
                    callbacks=[lgb.early_stopping(self.config.early_stopping_rounds), lgb.log_evaluation(0)],
                )
            
            train_pred = self.model.predict(X_train)
            val_pred = self.model.predict(X_val)
            
            if self.config.task == 'classification':
                train_proba = self.model.predict_proba(X_train)[:, 1]
                val_proba = self.model.predict_proba(X_val)[:, 1]
                
                train_metrics = {
                    'accuracy': accuracy_score(y_train, train_pred),
                    'precision': precision_score(y_train, train_pred, zero_division=0),
                    'recall': recall_score(y_train, train_pred, zero_division=0),
                    'f1': f1_score(y_train, train_pred, zero_division=0),
                    'auc': roc_auc_score(y_train, train_proba),
                }
                val_metrics = {
                    'accuracy': accuracy_score(y_val, val_pred),
                    'precision': precision_score(y_val, val_pred, zero_division=0),
                    'recall': recall_score(y_val, val_pred, zero_division=0),
                    'f1': f1_score(y_val, val_pred, zero_division=0),
                    'auc': roc_auc_score(y_val, val_proba),
                }
            else:
                train_metrics = {
                    'mse': mean_squared_error(y_train, train_pred),
                    'rmse': np.sqrt(mean_squared_error(y_train, train_pred)),
                    'mae': mean_absolute_error(y_train, train_pred),
                    'r2': r2_score(y_train, train_pred),
                }
                val_metrics = {
                    'mse': mean_squared_error(y_val, val_pred),
                    'rmse': np.sqrt(mean_squared_error(y_val, val_pred)),
                    'mae': mean_absolute_error(y_val, val_pred),
                    'r2': r2_score(y_val, val_pred),
                }
            
            if MLFLOW_AVAILABLE:
                mlflow.log_metrics({f"train_{k}": v for k, v in train_metrics.items()})
                mlflow.log_metrics({f"val_{k}": v for k, v in val_metrics.items()})
            
            if self.config.model_type == 'xgboost':
                importance = self.model.feature_importances_
            else:
                importance = self.model.feature_importances_
            
            feature_importance = dict(zip(self.feature_names, importance.tolist()))
            feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
            
            if MLFLOW_AVAILABLE:
                mlflow.log_dict(feature_importance, "feature_importance.json")
            
            test_metrics = {}
            if X_test is not None and y_test is not None:
                test_pred = self.model.predict(X_test)
                
                if self.config.task == 'classification':
                    test_proba = self.model.predict_proba(X_test)[:, 1]
                    test_metrics = {
                        'accuracy': accuracy_score(y_test, test_pred),
                        'precision': precision_score(y_test, test_pred, zero_division=0),
                        'recall': recall_score(y_test, test_pred, zero_division=0),
                        'f1': f1_score(y_test, test_pred, zero_division=0),
                        'auc': roc_auc_score(y_test, test_proba),
                    }
                else:
                    test_metrics = {
                        'mse': mean_squared_error(y_test, test_pred),
                        'rmse': np.sqrt(mean_squared_error(y_test, test_pred)),
                        'mae': mean_absolute_error(y_test, test_pred),
                        'r2': r2_score(y_test, test_pred),
                    }
                
                if MLFLOW_AVAILABLE:
                    mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})
            
            if log_to_mlflow and MLFLOW_AVAILABLE:
                if self.config.model_type == 'xgboost':
                    mlflow.xgboost.log_model(self.model, "model")
                else:
                    mlflow.lightgbm.log_model(self.model, "model")
                
                mlflow.log_artifact(model_path)
            
            model_path = f"models/{self.config.model_type}_{self.config.task}_{run_id}.pkl"
            joblib.dump(self.model, model_path)
            if MLFLOW_AVAILABLE and log_to_mlflow:
                mlflow.log_artifact(model_path)
            
            logger.info(f"Training complete. Run ID: {run_id}")
            logger.info(f"Val metrics: {val_metrics}")
            
            return TrainingResult(
                model_config=self.config,
                train_metrics=train_metrics,
                val_metrics=val_metrics,
                test_metrics=test_metrics,
                feature_importance=feature_importance,
                model_path=model_path,
                mlflow_run_id=run_id if (log_to_mlflow and MLFLOW_AVAILABLE) else None,
            )
        finally:
            if MLFLOW_AVAILABLE and log_to_mlflow:
                try:
                    mlflow.end_run()
                except Exception:
                    pass
    
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not trained")
        return self.model.predict(X)
    
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if self.model is None:
            raise ValueError("Model not trained")
        if self.config.task != 'classification':
            raise ValueError("predict_proba only for classification")
        return self.model.predict_proba(X)[:, 1]
    
    def save(self, path: str):
        joblib.dump(self.model, path)
    
    @classmethod
    def load(cls, path: str, config: ModelConfig):
        trainer = cls(config)
        trainer.model = joblib.load(path)
        return trainer


class WalkForwardValidator:
    def __init__(
        self,
        n_splits: int = 5,
        test_size: int = 52,  # weeks
        gap: int = 4,  # weeks purge gap
        expanding: bool = True,
    ):
        self.n_splits = n_splits
        self.test_size = test_size
        self.gap = gap
        self.expanding = expanding
    
    def split(self, X: pd.DataFrame, y: pd.Series, dates: pd.Series) -> List[Tuple]:
        n_samples = len(X)
        indices = np.arange(n_samples)
        
        test_samples = self.test_size
        gap_samples = self.gap
        
        splits = []
        
        for i in range(self.n_splits):
            test_end = n_samples - i * test_samples
            test_start = test_end - test_samples
            train_end = test_start - gap_samples
            
            if train_end <= 0:
                break
            
            if self.expanding:
                train_start = 0
            else:
                train_start = max(0, train_end - test_samples * 3)
            
            train_idx = indices[train_start:train_end]
            test_idx = indices[test_start:test_end]
            
            if len(train_idx) < 50 or len(test_idx) < 10:
                continue
            
            splits.append((train_idx, test_idx))
        
        return splits
    
    def validate(
        self,
        trainer_class,
        config: ModelConfig,
        X: pd.DataFrame,
        y: pd.Series,
        dates: pd.Series,
        **trainer_kwargs,
    ) -> List[TrainingResult]:
        splits = self.split(X, y, dates)
        results = []
        
        for fold, (train_idx, test_idx) in enumerate(splits):
            logger.info(f"Fold {fold + 1}/{len(splits)}: train={len(train_idx)}, test={len(test_idx)}")
            
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            
            val_size = min(len(X_train) // 5, 52)
            X_train_fold, X_val = X_train[:-val_size], X_train[-val_size:]
            y_train_fold, y_val = y_train[:-val_size], y_train[-val_size:]
            
            trainer = trainer_class(config, experiment_name=f"{config.model_type}_{config.task}_fold_{fold}")
            result = trainer.train(
                X_train_fold, y_train_fold,
                X_val, y_val,
                X_test, y_test,
                log_to_mlflow=True,
            )
            results.append(result)
        
        return results
    
    def aggregate_results(self, results: List[TrainingResult]) -> Dict[str, float]:
        if not results:
            return {}
        
        metrics = {}
        for key in results[0].val_metrics.keys():
            values = [r.val_metrics[key] for r in results]
            metrics[f"val_{key}_mean"] = np.mean(values)
            metrics[f"val_{key}_std"] = np.std(values)
            metrics[f"val_{key}_min"] = np.min(values)
            metrics[f"val_{key}_max"] = np.max(values)
        
        for key in results[0].test_metrics.keys():
            values = [r.test_metrics[key] for r in results if key in r.test_metrics]
            if values:
                metrics[f"test_{key}_mean"] = np.mean(values)
                metrics[f"test_{key}_std"] = np.std(values)
        
        return metrics


xgboost_trainer = XGBoostTrainer
walk_forward_validator = WalkForwardValidator