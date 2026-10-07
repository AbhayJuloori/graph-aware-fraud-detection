import json
import sys

from fraud_lab import cli


def test_queued_job_consumes_mature_labeled_file(tmp_path, monkeypatch, capsys):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    request = artifacts / "retrain_request.json"
    request.write_text(json.dumps({"status": "queued_awaiting_mature_labels", "model_version": 4}))
    labeled = tmp_path / "refreshed.csv"
    labeled.write_text("ready")
    calls = []

    def fake_train(path, root, fraction, seed):
        calls.append((path, root, fraction, seed))
        return {"registry": {"version": 5}}

    monkeypatch.setattr(cli, "train", fake_train)
    monkeypatch.setattr(sys, "argv", ["fraud-lab", "--root", str(tmp_path), "retrain",
                                      "--labeled-csv", str(labeled)])
    cli.main()
    assert calls == [(labeled, tmp_path, 0.10, 43)]
    assert json.loads(request.read_text())["status"] == "completed"
    assert json.loads(request.read_text())["registered_version"] == 5
    assert "version" in capsys.readouterr().out
