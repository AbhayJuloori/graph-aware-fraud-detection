import json

import numpy as np
import pandas as pd

from fraud_lab import monitoring
from fraud_lab.training import threshold_at_fpr


def test_threshold_bounds_validation_false_positives():
    labels = np.array([0] * 1000 + [1] * 20)
    scores = np.linspace(0, 1, len(labels))
    threshold = threshold_at_fpr(labels, scores)
    assert np.mean(scores[labels == 0] >= threshold) <= 0.01


def test_monitor_queues_retrain_when_drift_exceeds_threshold(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    reference = pd.DataFrame({"raw_amount": np.arange(1000), "score": np.linspace(0, 1, 1000)})
    current = pd.DataFrame({"raw_amount": np.arange(1000) + 10000,
                            "score": np.linspace(0, 1, 1000)})
    reference.to_parquet(artifacts / "reference.parquet")
    current.to_parquet(artifacts / "current.parquet")
    monkeypatch.setattr(monitoring, "_evidently_report", lambda *_: "ok")
    result = monitoring.monitor(tmp_path)
    assert result["status"] == "alert"
    request = json.loads((artifacts / "retrain_request.json").read_text())
    assert request["status"] == "queued_awaiting_mature_labels"
    pd.testing.assert_frame_equal(
        pd.read_parquet(artifacts / "monitored_current.parquet"), current[["raw_amount", "score"]]
    )
