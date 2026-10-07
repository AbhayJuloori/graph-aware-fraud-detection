"""Load the champion MLflow model and its training-cutoff graph snapshot."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import mlflow
import mlflow.xgboost
import pandas as pd
import xgboost as xgb
from mlflow.tracking import MlflowClient

from fraud_lab.features import BASE_COLUMNS, GRAPH_COLUMNS, base_features
from fraud_lab.training import MODEL_NAME, tracking_uri


class FraudService:
    def __init__(self, project_root: str | Path) -> None:
        root = Path(project_root).resolve()
        mlflow.set_tracking_uri(tracking_uri(root))
        client = MlflowClient()
        version = client.get_model_version_by_alias(MODEL_NAME, "champion")
        self.version = int(version.version)
        self.mode = version.tags["feature_mode"]
        self.model = mlflow.xgboost.load_model(f"models:/{MODEL_NAME}@champion")
        self.graph = None
        if self.mode == "graph":
            path = mlflow.artifacts.download_artifacts(
                run_id=version.run_id, artifact_path="graph_state.joblib"
            )
            self.graph = joblib.load(path)

    def features(self, data: pd.DataFrame) -> pd.DataFrame:
        features = base_features(data)
        if self.mode == "graph":
            features = pd.concat([features, self.graph.score_rows(data)], axis=1)
            return features[BASE_COLUMNS + GRAPH_COLUMNS]
        return features[BASE_COLUMNS]

    def score(self, data: pd.DataFrame) -> list[dict]:
        features = self.features(data)
        probabilities = self.model.predict_proba(features)[:, 1]
        contributions = self.model.get_booster().predict(
            xgb.DMatrix(features), pred_contribs=True
        )
        result = []
        for probability, row in zip(probabilities, contributions):
            top = sorted(zip(features.columns, row[:-1]), key=lambda item: abs(item[1]),
                         reverse=True)[:3]
            result.append({
                "fraud_probability": float(probability),
                "model_version": self.version,
                "reason_codes": [
                    {"feature": feature, "shap_log_odds": float(value),
                     "direction": "higher_risk" if value > 0 else "lower_risk"}
                    for feature, value in top
                ],
            })
        return result


@lru_cache(maxsize=1)
def get_service(project_root: str) -> FraudService:
    return FraudService(project_root)
