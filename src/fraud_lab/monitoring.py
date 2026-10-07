"""Evidently report plus a deterministic alert and retrain-job queue."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from scipy.stats import ks_2samp

from fraud_lab.features import BASE_COLUMNS, GRAPH_COLUMNS
from fraud_lab.training import MODEL_NAME, tracking_uri


def _evidently_report(reference: pd.DataFrame, current: pd.DataFrame, path: Path) -> str:
    """Keep Evidently report failures visible; the alert rule still runs independently."""
    try:
        from evidently import Dataset, Report
        from evidently.presets import DataDriftPreset

        columns = ["amount", "score"]
        report = Report([DataDriftPreset(columns=columns)])
        snapshot = report.run(
            reference_data=Dataset.from_pandas(reference[columns]),
            current_data=Dataset.from_pandas(current[columns]),
        )
        snapshot.save_html(str(path))
        return "ok"
    except Exception as exc:  # noqa: BLE001 - report failure is recorded; alert still runs.
        return f"failed: {type(exc).__name__}: {exc}"


def _ks(reference: np.ndarray, current: np.ndarray) -> dict[str, float]:
    stat, p = ks_2samp(reference, current)
    return {"statistic": float(stat), "p_value": float(p)}


def monitor(project_root: str | Path, amount_multiplier: float = 1.0,
            drift_threshold: float = 0.10) -> dict:
    if amount_multiplier <= 0:
        raise ValueError("amount_multiplier must be positive")
    root = Path(project_root).resolve()
    artifacts = root / "artifacts"
    model_version = None
    results_path = artifacts / "results.json"
    if results_path.exists():
        model_version = json.loads(results_path.read_text())["registry"]["version"]
    reference = pd.read_parquet(artifacts / "reference.parquet")
    current = pd.read_parquet(artifacts / "current.parquet")
    if amount_multiplier != 1:
        mlflow.set_tracking_uri(tracking_uri(root))
        version = MlflowClient().get_model_version_by_alias(MODEL_NAME, "champion")
        model = mlflow.xgboost.load_model(f"models:/{MODEL_NAME}@champion")
        shifted = current.raw_amount.to_numpy() * amount_multiplier
        current["amount"] = np.log1p(shifted)
        current["amount_to_origin_balance"] = np.minimum(
            shifted / (np.expm1(current.oldbalanceOrg.to_numpy()) + 1), 1_000_000)
        current["amount_to_dest_balance"] = np.minimum(
            shifted / (np.expm1(current.oldbalanceDest.to_numpy()) + 1), 1_000_000)
        columns = BASE_COLUMNS + (GRAPH_COLUMNS if version.tags["feature_mode"] == "graph" else [])
        current["score"] = model.predict_proba(current[columns])[:, 1]
        current["raw_amount"] = shifted
    # Deterministic capped samples bound the cost of the report and KS check.
    ref_sample = reference.sample(n=min(20_000, len(reference)), random_state=42)
    cur_sample = current.sample(n=min(20_000, len(current)), random_state=42)
    amount_drift = _ks(ref_sample.raw_amount.to_numpy(), cur_sample.raw_amount.to_numpy())
    score_drift = _ks(ref_sample.score.to_numpy(), cur_sample.score.to_numpy())
    alert = any(d["statistic"] >= drift_threshold and d["p_value"] < 0.01
                for d in (amount_drift, score_drift))
    artifacts.mkdir(exist_ok=True)
    report_status = _evidently_report(
        pd.DataFrame({"amount": ref_sample.raw_amount, "score": ref_sample.score}),
        pd.DataFrame({"amount": cur_sample.raw_amount, "score": cur_sample.score}),
        artifacts / "drift_report.html",
    )
    result = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "status": "alert" if alert else "healthy",
        "amount_multiplier": amount_multiplier, "threshold": drift_threshold,
        "amount_ks": amount_drift, "score_ks": score_drift,
        "evidently_report": report_status,
        "reference_rows": len(reference), "current_rows": len(current),
        "model_version": model_version,
    }
    current[["raw_amount", "score"]].to_parquet(artifacts / "monitored_current.parquet", index=False)
    if alert:
        request = {
            "created_at_utc": result["checked_at_utc"],
            "status": "queued_awaiting_mature_labels",
            "reason": "feature_or_score_distribution_drift",
            "source": "monitoring.py",
            "model_version": model_version,
            "requires": "labeled post-alert transactions and fresh chronological holdout",
        }
        request_path = artifacts / "retrain_request.json"
        existing = json.loads(request_path.read_text()) if request_path.exists() else {}
        if existing.get("status") != request["status"] or existing.get("model_version") != model_version:
            request_path.write_text(json.dumps(request, indent=2) + "\n")
    (artifacts / "monitor_status.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
