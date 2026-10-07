"""Export only aggregate, portable evidence from a local MLflow run."""

from __future__ import annotations

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = json.loads((root / "artifacts/results.json").read_text())
summary = {key: source[key] for key in (
    "dataset", "sample_fraction", "sample_start", "seed", "sampling", "split", "counts",
    "excluded_columns", "graph_pr_auc_lift_validation", "graph_pr_auc_lift_test",
    "graph_promotion_margin", "features",
)}
summary["models"] = {
    name: {split: metrics for split, metrics in model.items() if split in {"validation", "test"}}
    for name, model in source["models"].items()
}
summary["selected_on_validation"] = source["registry"]["feature_mode"]
out = root / "docs/results.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(summary, indent=2) + "\n")
print(out)
