# MLflow is optional
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    mlflow = None
    MLFLOW_AVAILABLE = False

import joblib
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import logging
import json

logger = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self, registry_path: str = "models/registry"):
        self.registry_path = Path(registry_path)
        self.registry_path.mkdir(parents=True, exist_ok=True)
        self._models: Dict[str, Any] = {}
        self._metadata: Dict[str, Dict] = {}
    
    def register_model(
        self,
        model,
        name: str,
        version: str,
        config: Dict,
        metrics: Dict,
        feature_names: List[str],
        mlflow_run_id: Optional[str] = None,
    ) -> str:
        model_dir = self.registry_path / name / version
        model_dir.mkdir(parents=True, exist_ok=True)
        
        model_path = model_dir / "model.pkl"
        joblib.dump(model, model_path)
        
        metadata = {
            "name": name,
            "version": version,
            "config": config,
            "metrics": metrics,
            "feature_names": feature_names,
            "mlflow_run_id": mlflow_run_id,
            "registered_at": datetime.utcnow().isoformat(),
            "model_path": str(model_path),
        }
        
        metadata_path = model_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        key = f"{name}:{version}"
        self._models[key] = model
        self._metadata[key] = metadata
        
        latest_link = self.registry_path / name / "latest"
        if latest_link.exists() or latest_link.is_symlink():
            latest_link.unlink()
        latest_link.symlink_to(version)
        
        logger.info(f"Model registered: {key}")
        return key
    
    def load_model(self, name: str, version: str = "latest") -> Any:
        key = f"{name}:{version}"
        
        if key in self._models:
            return self._models[key]
        
        model_dir = self.registry_path / name / version
        model_path = model_dir / "model.pkl"
        
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {key}")
        
        model = joblib.load(model_path)
        self._models[key] = model
        return model
    
    def get_metadata(self, name: str, version: str = "latest") -> Dict:
        key = f"{name}:{version}"
        
        if key in self._metadata:
            return self._metadata[key]
        
        metadata_path = self.registry_path / name / version / "metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found: {key}")
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        self._metadata[key] = metadata
        return metadata
    
    def list_models(self) -> List[Dict]:
        models = []
        for name_dir in self.registry_path.iterdir():
            if not name_dir.is_dir():
                continue
            for version_dir in name_dir.iterdir():
                if version_dir.name == "latest":
                    continue
                if not version_dir.is_dir():
                    continue
                metadata_path = version_dir / "metadata.json"
                if metadata_path.exists():
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    models.append(metadata)
        return sorted(models, key=lambda x: x.get("registered_at", ""), reverse=True)
    
    def promote_to_production(self, name: str, version: str) -> bool:
        prod_link = self.registry_path / name / "production"
        version_dir = self.registry_path / name / version
        
        if not version_dir.exists():
            return False
        
        if prod_link.exists() or prod_link.is_symlink():
            prod_link.unlink()
        prod_link.symlink_to(version)
        
        logger.info(f"Model promoted to production: {name}:{version}")
        return True
    
    def get_production_model(self, name: str):
        prod_link = self.registry_path / name / "production"
        if not prod_link.exists():
            raise FileNotFoundError(f"No production model for {name}")
        return self.load_model(name, prod_link.readlink().name)


class InferenceService:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self._loaded_models: Dict[str, Any] = {}
    
    def load_model(self, name: str, version: str = "production") -> Any:
        key = f"{name}:{version}"
        if key in self._loaded_models:
            return self._loaded_models[key]
        
        model = self.registry.get_production_model(name) if version == "production" else self.registry.load_model(name, version)
        self._loaded_models[key] = model
        return model
    
    def predict(
        self,
        name: str,
        features: pd.DataFrame,
        version: str = "production",
        return_proba: bool = False,
    ) -> np.ndarray:
        model = self.load_model(name, version)
        
        metadata = self.registry.get_metadata(name, version)
        expected_features = metadata.get("feature_names", [])
        
        if expected_features:
            missing = set(expected_features) - set(features.columns)
            if missing:
                logger.warning(f"Missing features: {missing}")
            extra = set(features.columns) - set(expected_features)
            if extra:
                logger.warning(f"Extra features (will be dropped): {extra}")
            
            features = features.reindex(columns=expected_features, fill_value=0)
        
        if hasattr(model, 'predict_proba') and return_proba:
            return model.predict_proba(features)[:, 1]
        
        return model.predict(features)
    
    def predict_batch(
        self,
        name: str,
        features_batch: List[pd.DataFrame],
        version: str = "production",
    ) -> List[np.ndarray]:
        return [self.predict(name, df, version) for df in features_batch]
    
    def get_model_info(self, name: str, version: str = "production") -> Dict:
        metadata = self.registry.get_metadata(name, version)
        return {
            "name": metadata.get("name"),
            "version": metadata.get("version"),
            "config": metadata.get("config"),
            "metrics": metadata.get("metrics"),
            "feature_count": len(metadata.get("feature_names", [])),
            "registered_at": metadata.get("registered_at"),
        }


model_registry = ModelRegistry()
inference_service = InferenceService(model_registry)