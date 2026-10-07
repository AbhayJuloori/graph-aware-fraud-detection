"""Build the publishable summary: dataset profile, model evidence, drift sweep, figures.

Reads the local PaySim CSV and training artifacts; writes only aggregates and a few
synthetic example rows to ``site/data/summary.json``, ``docs/results/summary.json``,
and ``docs/figures/*.png``.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from fraud_lab.data import DTYPES, RAW_COLUMNS
from fraud_lab.monitoring import drift_stats, load_champion, shift_amounts

MULTIPLIERS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
AMOUNT_BINS = np.linspace(0, 8, 41)  # log10 of amount, 1 to 100M

# Earlier cohorts, copied from the run logs preserved in docs/experiment-log.md.
COHORT_HISTORY = [
    {"id": "E2", "label": "10% cohort", "validation_fraud": 62, "test_fraud": 411,
     "validation_lift": -0.0054, "test_lift": -0.0021, "role": "scale-up"},
    {"id": "E3", "label": "First 25% cohort", "validation_fraud": 168, "test_fraud": 1064,
     "validation_lift": 0.0012, "test_lift": -0.0038, "role": "exploratory"},
]


def profile_dataset(raw_path: Path) -> dict:
    """Whole-dataset facts that explain why graph features have little to work with."""
    data = pd.read_csv(raw_path, usecols=RAW_COLUMNS, dtype=DTYPES)
    fraud = data.isFraud == 1
    by_type = data.groupby("type", observed=True).isFraud.agg(["size", "sum"]).reset_index()
    hour = data.step % 24
    by_hour = data.groupby(hour).isFraud.agg(["size", "sum"]).reset_index()
    by_step = data.groupby("step").isFraud.agg(["size", "sum"]).reset_index()
    sender_counts = data.nameOrig.value_counts()
    receiver_counts = data.nameDest.value_counts()
    customer_receivers = receiver_counts[~receiver_counts.index.str.startswith("M")]
    risky = data.type.isin(["TRANSFER", "CASH_OUT"])
    drains = (data.amount - data.oldbalanceOrg).abs() < 1
    fraud_receivers = data.loc[fraud, "nameDest"]
    fraud_receiver_counts = fraud_receivers.value_counts()
    senders = pd.Index(data.nameOrig.unique())

    def log_hist(values: pd.Series) -> list[int]:
        counts, _ = np.histogram(np.log10(values.clip(lower=1)), bins=AMOUNT_BINS)
        return counts.tolist()

    return {
        "rows": len(data), "fraud": int(fraud.sum()), "fraud_rate": float(fraud.mean()),
        "steps": int(data.step.max()), "unique_senders": len(sender_counts),
        "unique_receivers": len(receiver_counts),
        "senders_seen_once_share": float((sender_counts == 1).mean()),
        "sender_rows_from_repeat_senders": float(sender_counts[sender_counts > 1].sum() / len(data)),
        "receivers_seen_once_share": float((customer_receivers == 1).mean()),
        "receiver_median_rows": float(customer_receivers.median()),
        "receiver_p90_rows": float(customer_receivers.quantile(0.9)),
        "fraud_receivers_reused_share": float((fraud_receiver_counts > 1).mean()),
        "fraud_receivers_that_send_share": float(fraud_receivers.isin(senders).mean()),
        "by_type": [{"type": r.type, "rows": int(r["size"]), "fraud": int(r["sum"])}
                    for _, r in by_type.iterrows()],
        "by_hour": [{"hour": int(r.step), "rows": int(r["size"]), "fraud": int(r["sum"])}
                    for _, r in by_hour.iterrows()],
        "by_step": {"step": by_step.step.astype(int).tolist(),
                    "rows": by_step["size"].astype(int).tolist(),
                    "fraud": by_step["sum"].astype(int).tolist()},
        "drain": {
            "fraud_share": float(drains[fraud].mean()),
            "legit_risky_type_share": float(drains[~fraud & risky].mean()),
            "fraud_dest_zero_balance_share": float((data.oldbalanceDest[fraud] == 0).mean()),
            "legit_risky_dest_zero_balance_share": float(
                (data.oldbalanceDest[~fraud & risky] == 0).mean()),
        },
        "amount_hist": {"log10_edges": AMOUNT_BINS.tolist(),
                        "fraud": log_hist(data.amount[fraud]),
                        "legit": log_hist(data.amount[~fraud])},
    }


def drift_sweep(root: Path, threshold: float, drift_threshold: float = 0.10) -> dict:
    artifacts = root / "artifacts"
    reference = pd.read_parquet(artifacts / "reference.parquet")
    current = pd.read_parquet(artifacts / "current.parquet")
    model, mode = load_champion(root)
    ref_alert_rate = float((reference.score >= threshold).mean())

    def hist(values: np.ndarray) -> list[float]:
        counts, _ = np.histogram(np.log10(np.clip(values, 1, None)), bins=AMOUNT_BINS)
        return (counts / len(values)).round(5).tolist()

    sweep = []
    for multiplier in MULTIPLIERS:
        replay = current if multiplier == 1 else shift_amounts(current, multiplier, model, mode)
        stats = drift_stats(reference, replay, drift_threshold)
        sweep.append({
            "multiplier": multiplier,
            "amount_ks": stats["amount_ks"]["statistic"], "score_ks": stats["score_ks"]["statistic"],
            "alert": bool(stats["alert"]),
            "alerts_per_100k": float((replay.score >= threshold).mean() * 100_000),
            "amount_hist": hist(replay.raw_amount.to_numpy()),
        })
    # Natural replay, one simulated day at a time: does drift creep in over the test window?
    daily = []
    days = (current.step - current.step.min()) // 24
    for day, frame in current.groupby(days):
        stats = drift_stats(reference, frame, drift_threshold, sample=5_000)
        daily.append({"day": int(day) + 1, "rows": len(frame),
                      "first_step": int(frame.step.min()), "last_step": int(frame.step.max()),
                      "amount_ks": stats["amount_ks"]["statistic"],
                      "score_ks": stats["score_ks"]["statistic"], "alert": bool(stats["alert"])})
    return {"threshold": drift_threshold, "decision_threshold": threshold,
            "reference_alerts_per_100k": ref_alert_rate * 100_000,
            "reference_amount_hist": hist(reference.raw_amount.to_numpy()),
            "log10_edges": AMOUNT_BINS.tolist(), "sweep": sweep, "daily": daily}


def build_summary(root: Path, raw_path: Path) -> dict:
    artifacts = root / "artifacts"
    results = json.loads((artifacts / "results.json").read_text())
    diag = json.loads((artifacts / "diagnostics.json").read_text())
    champion = diag["champion"]
    threshold = results["models"][champion]["validation"]["threshold"]
    models = {
        name: {"validation": metrics["validation"], "test": metrics["test"], **diag["models"][name]}
        for name, metrics in results["models"].items()
    }
    cohorts = COHORT_HISTORY + [{
        "id": "E4", "label": "Disjoint 25% cohort (published)",
        "validation_fraud": results["counts"]["validation"]["fraud"],
        "test_fraud": results["counts"]["test"]["fraud"],
        "validation_lift": results["graph_pr_auc_lift_validation"],
        "test_lift": results["graph_pr_auc_lift_test"], "role": "confirmation",
    }]
    return {
        "dataset": profile_dataset(raw_path),
        "split": results["split"], "counts": results["counts"],
        "sample_fraction": results["sample_fraction"], "sample_start": results["sample_start"],
        "seed": results["seed"], "excluded_columns": results["excluded_columns"],
        "features": results["features"], "champion": champion,
        "promotion_margin": results["graph_promotion_margin"],
        "models": models, "shap": diag["shap"], "graph_coverage": diag["graph_coverage"],
        "examples": diag["examples"], "cohorts": cohorts,
        "drift": drift_sweep(root, threshold),
    }


def figures(summary: dict, out_dir: Path) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    colors = {"logistic_baseline": "#8a8984", "xgboost_baseline": "#2a78d6",
              "xgboost_graph": "#eb6834"}
    labels = {"logistic_baseline": "Logistic regression", "xgboost_baseline": "XGBoost, transaction only",
              "xgboost_graph": "XGBoost, transaction + graph"}
    paths = []

    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    for name, model in summary["models"].items():
        curve = model["pr_curve"]
        ax.plot([p["recall"] for p in curve], [p["precision"] for p in curve], color=colors[name],
                lw=2, label=f"{labels[name]} (PR-AUC {model['test']['pr_auc']:.3f})")
    ax.set(xlabel="Recall (share of fraud caught)", ylabel="Precision (share of alerts that are fraud)",
           title="Held-out test window: precision vs recall", ylim=(0, 1.02))
    ax.legend(frameon=False, loc="lower left")
    paths.append(out_dir / "pr_curves.png")
    fig.tight_layout(); fig.savefig(paths[-1], dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    cohorts = summary["cohorts"]
    x = np.arange(len(cohorts))
    ax.bar(x - 0.18, [c["validation_lift"] for c in cohorts], 0.36, color="#2a78d6", label="Validation")
    ax.bar(x + 0.18, [c["test_lift"] for c in cohorts], 0.36, color="#eb6834", label="Test")
    ax.axhline(summary["promotion_margin"], color="#52514e", ls="--", lw=1)
    ax.text(len(cohorts) - 0.5, summary["promotion_margin"] + 0.0004, "promotion gate +0.01",
            ha="right", color="#52514e", fontsize=9)
    ax.axhline(0, color="#0b0b0b", lw=0.8)
    ax.set_xticks(x, [f"{c['id']}\n{c['label']}" for c in cohorts], fontsize=8.5)
    ax.set(ylabel="Graph PR-AUC lift", title="Graph features never clear the gate")
    ax.legend(frameon=False)
    paths.append(out_dir / "graph_lift.png")
    fig.tight_layout(); fig.savefig(paths[-1], dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    shap = summary["shap"]["xgboost_graph"][:12][::-1]
    ax.barh([s["feature"] for s in shap], [s["mean_abs_shap"] for s in shap],
            color=["#eb6834" if s["is_graph"] else "#2a78d6" for s in shap])
    ax.set(xlabel="Mean |SHAP| (log-odds)", title="What drives the graph model (orange = graph feature)")
    paths.append(out_dir / "shap_importance.png")
    fig.tight_layout(); fig.savefig(paths[-1], dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    sweep = summary["drift"]["sweep"]
    m = [s["multiplier"] for s in sweep]
    ax.plot(m, [s["amount_ks"] for s in sweep], "o-", color="#2a78d6", label="Amount KS")
    ax.plot(m, [s["score_ks"] for s in sweep], "o-", color="#eb6834", label="Score KS")
    ax.axhline(summary["drift"]["threshold"], color="#52514e", ls="--", lw=1)
    ax.set(xlabel="Replay amount multiplier", ylabel="KS statistic vs reference",
           title="Replay drift as transaction amounts scale")
    ax.legend(frameon=False)
    paths.append(out_dir / "drift_sweep.png")
    fig.tight_layout(); fig.savefig(paths[-1], dpi=160); plt.close(fig)
    return paths


def write_report(root: str | Path, raw_path: str | Path) -> dict:
    root = Path(root).resolve()
    summary = build_summary(root, Path(raw_path))
    text = json.dumps(summary, indent=1) + "\n"
    for path in (root / "site/data/summary.json", root / "docs/results/summary.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    written = figures(summary, root / "docs/figures")
    return {"summary": str(root / "site/data/summary.json"), "figures": [str(p) for p in written],
            "drift_alert_from": next((s["multiplier"] for s in summary["drift"]["sweep"]
                                      if s["alert"] and s["multiplier"] > 1), None)}
