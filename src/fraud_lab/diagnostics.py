"""Aggregate evaluation evidence for the report: curves, explanations, graph coverage.

Everything written here is an aggregate or a handful of synthetic example rows, so it is
safe to publish alongside the code.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import precision_recall_curve, roc_curve

from fraud_lab.features import GRAPH_COLUMNS, TYPES


def _downsample(points: dict[str, np.ndarray], keep: int = 160) -> list[dict[str, float]]:
    n = len(next(iter(points.values())))
    index = np.unique(np.linspace(0, n - 1, min(keep, n)).round().astype(int))
    return [{key: float(values[i]) for key, values in points.items()} for i in index]


def pr_curve(y: np.ndarray, scores: np.ndarray) -> list[dict[str, float]]:
    precision, recall, _ = precision_recall_curve(y, scores)
    # Reverse so recall rises left to right, then keep a readable number of points.
    return _downsample({"recall": recall[::-1], "precision": precision[::-1]})


def operating_curve(y: np.ndarray, scores: np.ndarray) -> list[dict[str, float]]:
    """Recall and alert volume at log-spaced false positive rates (threshold explorer)."""
    fpr, tpr, thresholds = roc_curve(y, scores)
    negatives, positives = int(np.sum(y == 0)), int(np.sum(y == 1))
    out = []
    for target in np.geomspace(1e-4, 0.2, 60):
        i = int(np.searchsorted(fpr, target, side="right") - 1)
        i = max(i, 0)
        tp, fp = tpr[i] * positives, fpr[i] * negatives
        out.append({
            "target_fpr": float(target), "fpr": float(fpr[i]), "recall": float(tpr[i]),
            "precision": float(tp / (tp + fp)) if tp + fp else 1.0,
            "threshold": float(min(thresholds[i], 1.0)),
            "alerts_per_100k": float((tp + fp) / len(y) * 100_000),
            "caught_per_100k": float(tp / len(y) * 100_000),
        })
    return out


def score_histogram(y: np.ndarray, scores: np.ndarray, bins: int = 40) -> dict:
    edges = np.linspace(0, 1, bins + 1)
    fraud, _ = np.histogram(scores[y == 1], bins=edges)
    legit, _ = np.histogram(scores[y == 0], bins=edges)
    return {"edges": edges.round(4).tolist(), "fraud": fraud.tolist(), "legit": legit.tolist()}


def shap_importance(model, features: pd.DataFrame, y: np.ndarray, seed: int,
                    max_rows: int = 30_000) -> list[dict]:
    """Mean |TreeSHAP| in log-odds, on a sample that keeps every fraud row."""
    rng = np.random.default_rng(seed)
    fraud_rows = np.flatnonzero(y == 1)
    legit_rows = np.flatnonzero(y == 0)
    take = min(len(legit_rows), max(0, max_rows - len(fraud_rows)))
    rows = np.concatenate([fraud_rows, rng.choice(legit_rows, size=take, replace=False)])
    sample = features.iloc[rows]
    contributions = model.get_booster().predict(xgb.DMatrix(sample), pred_contribs=True)[:, :-1]
    is_fraud = y[rows] == 1
    gain = model.get_booster().get_score(importance_type="gain")
    out = [{
        "feature": name,
        "mean_abs_shap": float(np.abs(contributions[:, j]).mean()),
        "mean_shap_fraud": float(contributions[is_fraud, j].mean()),
        "mean_shap_legit": float(contributions[~is_fraud, j].mean()),
        "gain": float(gain.get(name, 0.0)),
        "is_graph": name in GRAPH_COLUMNS,
    } for j, name in enumerate(sample.columns)]
    return sorted(out, key=lambda item: item["mean_abs_shap"], reverse=True)


def graph_coverage(features: pd.DataFrame, y: np.ndarray) -> dict:
    """How often graph features carry any signal at all on held-out rows."""
    fraud = y == 1
    nonzero = {}
    for column in GRAPH_COLUMNS:
        active = features[column].to_numpy() > 0
        nonzero[column] = {
            "share_nonzero_all": float(active.mean()),
            "share_nonzero_fraud": float(active[fraud].mean()),
            "share_nonzero_legit": float(active[~fraud].mean()),
            "mean_fraud": float(features.loc[fraud, column].mean()),
            "mean_legit": float(features.loc[~fraud, column].mean()),
        }
    return nonzero


def per_type(raw: pd.DataFrame, scores: np.ndarray, threshold: float) -> list[dict]:
    flagged = scores >= threshold
    y = raw.isFraud.to_numpy()
    out = []
    for kind in TYPES:
        mask = (raw.type == kind).to_numpy()
        if not mask.any():
            continue
        positives = int(y[mask].sum())
        out.append({
            "type": kind, "rows": int(mask.sum()), "fraud": positives,
            "flagged": int(flagged[mask].sum()),
            "caught": int((flagged & (y == 1))[mask].sum()),
            "false_alarms": int((flagged & (y == 0))[mask].sum()),
        })
    return out


def example_rows(raw: pd.DataFrame, features: pd.DataFrame, model, threshold: float,
                 seed: int) -> list[dict]:
    """One synthetic example per outcome, with the API's top-3 reason codes."""
    scores = model.predict_proba(features)[:, 1]
    y = raw.isFraud.to_numpy()
    flagged = scores >= threshold
    groups = {
        "caught_fraud": np.flatnonzero(flagged & (y == 1)),
        "missed_fraud": np.flatnonzero(~flagged & (y == 1)),
        "false_alarm": np.flatnonzero(flagged & (y == 0)),
        "cleared_legit": np.flatnonzero(~flagged & (y == 0) & raw.type.isin(["TRANSFER", "CASH_OUT"]).to_numpy()),
    }
    rng = np.random.default_rng(seed)
    out = []
    for outcome, rows in groups.items():
        if not len(rows):
            continue
        i = int(rng.choice(rows))
        contributions = model.get_booster().predict(
            xgb.DMatrix(features.iloc[[i]]), pred_contribs=True)[0]
        top = sorted(zip(features.columns, contributions[:-1]), key=lambda kv: abs(kv[1]),
                     reverse=True)[:3]
        record = raw.iloc[i]
        out.append({
            "outcome": outcome, "step": int(record.step), "type": str(record.type),
            "amount": float(record.amount), "oldbalanceOrg": float(record.oldbalanceOrg),
            "oldbalanceDest": float(record.oldbalanceDest), "is_fraud": int(record.isFraud),
            "fraud_probability": float(scores[i]), "threshold": float(threshold),
            "base_log_odds": float(contributions[-1]),
            "reason_codes": [{"feature": f, "shap_log_odds": float(v)} for f, v in top],
        })
    return out
