"""Train three prespecified candidates; select on validation, report on held-out test."""

from __future__ import annotations

import json
import os
from pathlib import Path

import joblib
import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from fraud_lab import diagnostics
from fraud_lab.data import chronological_split, load_paysim
from fraud_lab.features import BASE_COLUMNS, GRAPH_COLUMNS, TemporalGraph, base_features

MODEL_NAME = "graph-aware-fraud-detector"
GRAPH_PROMOTION_MARGIN = 0.01


def tracking_uri(project_root: Path) -> str:
    state_dir = Path(os.environ.get("FRAUD_STATE_DIR", str(project_root)))
    state_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(state_dir / 'mlflow.db').resolve()}"


def evaluate(y: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, float | int]:
    predictions = scores >= threshold
    tn, fp, fn, tp = confusion_matrix(y, predictions, labels=[0, 1]).ravel()
    return {
        "pr_auc": float(average_precision_score(y, scores)),
        "recall_at_validation_1pct_fpr": float(tp / (tp + fn)),
        "realized_fpr": float(fp / (fp + tn)),
        "threshold": float(threshold),
        "positives": int(np.sum(y)),
        "rows": len(y),
        "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn),
    }


def threshold_at_fpr(y: np.ndarray, scores: np.ndarray, target_fpr: float = 0.01) -> float:
    negatives = np.sort(scores[y == 0])
    # Strictly above the 99th-percentile negative score to handle ties conservatively.
    index = max(0, int(np.floor((1 - target_fpr) * len(negatives))) - 1)
    return float(np.nextafter(negatives[index], np.inf))


def _xgb(y: np.ndarray, seed: int) -> XGBClassifier:
    positives = int(np.sum(y))
    return XGBClassifier(
        n_estimators=180, max_depth=5, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, min_child_weight=5,
        scale_pos_weight=(len(y) - positives) / positives,
        tree_method="hist", eval_metric="aucpr", random_state=seed, n_jobs=4,
    )


def train(
    raw_path: str | Path,
    project_root: str | Path,
    sample_fraction: float = 0.10,
    seed: int = 42,
    sample_start: float = 0.0,
) -> dict:
    root = Path(project_root).resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    data = load_paysim(raw_path, sample_fraction, seed, sample_start)
    train_data, val_data, test_data, split = chronological_split(data)
    train_base, val_base, test_base = map(base_features, (train_data, val_data, test_data))

    graph = TemporalGraph()
    train_graph = graph.transform(train_data, learn_labels=True)
    graph.refresh(int(train_data.step.max()) + 1)
    graph_snapshot = artifacts / "graph_state.joblib"
    joblib.dump(graph, graph_snapshot, compress=3)
    val_graph = graph.transform(val_data)
    test_graph = graph.transform(test_data)
    train_full = pd.concat([train_base, train_graph], axis=1)
    val_full = pd.concat([val_base, val_graph], axis=1)
    test_full = pd.concat([test_base, test_graph], axis=1)
    labels = {"train": train_data.isFraud.to_numpy(), "validation": val_data.isFraud.to_numpy(),
              "test": test_data.isFraud.to_numpy()}

    candidates = {
        "logistic_baseline": (make_pipeline(StandardScaler(), LogisticRegression(
            class_weight="balanced", max_iter=300, random_state=seed)), train_base, val_base, test_base),
        "xgboost_baseline": (_xgb(labels["train"], seed), train_base, val_base, test_base),
        "xgboost_graph": (_xgb(labels["train"], seed), train_full, val_full, test_full),
    }
    mlflow.set_tracking_uri(tracking_uri(root))
    mlflow.set_experiment("paysim-fraud-temporal")
    result: dict = {
        "dataset": "ealaxi/paysim1", "sample_fraction": sample_fraction,
        "sample_start": sample_start, "seed": seed,
        "sampling": "uniform random rows, independent of labels, then chronological split by whole step",
        "split": split,
        "counts": {part: {"rows": len(y), "fraud": int(np.sum(y))} for part, y in labels.items()},
        "excluded_columns": ["newbalanceOrig", "newbalanceDest", "isFlaggedFraud"],
        "models": {},
    }
    fitted = {}
    test_scores_by_model: dict[str, tuple[np.ndarray, float]] = {}
    for name, (model, x_train, x_val, x_test) in candidates.items():
        with mlflow.start_run(run_name=f"{name}-seed{seed}-sample{sample_fraction}") as run:
            model.fit(x_train, labels["train"])
            val_scores = model.predict_proba(x_val)[:, 1]
            test_scores = model.predict_proba(x_test)[:, 1]
            threshold = threshold_at_fpr(labels["validation"], val_scores)
            model_result = {
                "validation": evaluate(labels["validation"], val_scores, threshold),
                "test": evaluate(labels["test"], test_scores, threshold),
            }
            for split_name, metrics in model_result.items():
                mlflow.log_metrics({f"{split_name}_{k}": v for k, v in metrics.items()
                                    if k not in {"rows", "positives", "tp", "fp", "fn", "tn"}})
            mlflow.log_params({"candidate": name, "sample_fraction": sample_fraction,
                               "sample_start": sample_start,
                               "seed": seed, **split})
            result["models"][name] = {"run_id": run.info.run_id, **model_result}
            fitted[name] = model
            test_scores_by_model[name] = (test_scores, threshold)

    validation_lift = (result["models"]["xgboost_graph"]["validation"]["pr_auc"]
                       - result["models"]["xgboost_baseline"]["validation"]["pr_auc"])
    champion = ("xgboost_graph" if validation_lift >= GRAPH_PROMOTION_MARGIN
                else "xgboost_baseline")
    feature_mode = "graph" if champion == "xgboost_graph" else "base"
    with mlflow.start_run(run_name=f"registered-{champion}") as run:
        mlflow.log_params({"champion": champion, "feature_mode": feature_mode,
                           "sample_fraction": sample_fraction, "sample_start": sample_start,
                           "graph_promotion_margin": GRAPH_PROMOTION_MARGIN,
                           "seed": seed, **split})
        mlflow.log_artifact(str(graph_snapshot))
        model_info = mlflow.xgboost.log_model(
            fitted[champion], name="model", registered_model_name=MODEL_NAME,
        )
        client = MlflowClient()
        versions = client.search_model_versions(f"name='{MODEL_NAME}'")
        version = max((v for v in versions if v.run_id == run.info.run_id),
                      key=lambda v: int(v.version))
        client.set_model_version_tag(MODEL_NAME, version.version, "feature_mode", feature_mode)
        client.set_model_version_tag(MODEL_NAME, version.version, "source_sample_fraction",
                                     str(sample_fraction))
        client.set_registered_model_alias(MODEL_NAME, "champion", version.version)
        result["registry"] = {"name": MODEL_NAME, "version": int(version.version),
                              "run_id": run.info.run_id, "model_uri": model_info.model_uri,
                              "feature_mode": feature_mode}

    result["graph_pr_auc_lift_test"] = (
        result["models"]["xgboost_graph"]["test"]["pr_auc"]
        - result["models"]["xgboost_baseline"]["test"]["pr_auc"]
    )
    result["graph_pr_auc_lift_validation"] = validation_lift
    result["graph_promotion_margin"] = GRAPH_PROMOTION_MARGIN
    result["features"] = {"base": BASE_COLUMNS, "graph": GRAPH_COLUMNS}
    (artifacts / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    # Reference and current scores are precisely the registered model's scores.
    val_x = val_full if feature_mode == "graph" else val_base
    test_x = test_full if feature_mode == "graph" else test_base
    val_scores = fitted[champion].predict_proba(val_x)[:, 1]
    test_scores = fitted[champion].predict_proba(test_x)[:, 1]
    for name, raw, features, scores in (
        ("reference", val_data, val_x, val_scores),
        ("current", test_data, test_x, test_scores),
    ):
        replay = features.reset_index(drop=True).copy()
        replay.insert(0, "step", raw.step.to_numpy())
        replay.insert(1, "raw_amount", raw.amount.to_numpy())
        replay["score"] = scores
        replay.to_parquet(artifacts / f"{name}.parquet", index=False)

    y_test = labels["test"]
    diag = {
        "models": {
            name: {
                "pr_curve": diagnostics.pr_curve(y_test, scores),
                "operating_curve": diagnostics.operating_curve(y_test, scores),
                "score_histogram": diagnostics.score_histogram(y_test, scores),
                "per_type": diagnostics.per_type(test_data, scores, threshold),
            }
            for name, (scores, threshold) in test_scores_by_model.items()
        },
        "shap": {
            "xgboost_baseline": diagnostics.shap_importance(
                fitted["xgboost_baseline"], test_base, y_test, seed),
            "xgboost_graph": diagnostics.shap_importance(
                fitted["xgboost_graph"], test_full, y_test, seed),
        },
        "graph_coverage": diagnostics.graph_coverage(test_graph, y_test),
        "examples": diagnostics.example_rows(
            test_data, test_x, fitted[champion], test_scores_by_model[champion][1], seed),
        "champion": champion,
    }
    (artifacts / "diagnostics.json").write_text(json.dumps(diag, indent=2) + "\n")
    return result
