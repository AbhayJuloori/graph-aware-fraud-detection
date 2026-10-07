import numpy as np
import pandas as pd

from fraud_lab import diagnostics
from fraud_lab.features import GRAPH_COLUMNS


def scored():
    rng = np.random.default_rng(0)
    y = np.array([0] * 2000 + [1] * 40)
    scores = np.clip(rng.normal(0.2, 0.1, len(y)) + 0.6 * y, 0, 1)
    return y, scores


def test_operating_curve_is_monotone_and_bounded():
    y, scores = scored()
    curve = diagnostics.operating_curve(y, scores)
    recalls = [p["recall"] for p in curve]
    assert recalls == sorted(recalls)
    assert all(p["fpr"] <= p["target_fpr"] + 1e-12 for p in curve)
    assert all(0 <= p["precision"] <= 1 for p in curve)


def test_pr_curve_runs_from_low_to_full_recall():
    y, scores = scored()
    curve = diagnostics.pr_curve(y, scores)
    assert curve[0]["recall"] == 0 and curve[-1]["recall"] == 1
    assert len(curve) <= 160


def test_graph_coverage_counts_nonzero_rows():
    features = pd.DataFrame(0.0, index=range(4), columns=GRAPH_COLUMNS)
    features.loc[0, "receiver_degree"] = 3
    coverage = diagnostics.graph_coverage(features, np.array([1, 0, 0, 0]))
    assert coverage["receiver_degree"]["share_nonzero_all"] == 0.25
    assert coverage["receiver_degree"]["share_nonzero_fraud"] == 1.0
    assert coverage["ring_flag"]["share_nonzero_all"] == 0.0
