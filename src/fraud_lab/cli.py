"""Reproducible local commands for training, monitoring, and queued retraining."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fraud_lab.monitoring import monitor
from fraud_lab.training import train

DEFAULT_RAW = "data/raw/PS_20174392719_1491204439457_log.csv"


def main() -> None:
    parser = argparse.ArgumentParser(prog="fraud-lab")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    train_parser = sub.add_parser("train", help="chronological evaluation and MLflow registration")
    train_parser.add_argument("--raw", type=Path, default=Path(DEFAULT_RAW))
    train_parser.add_argument("--sample-fraction", type=float, default=0.10)
    train_parser.add_argument("--sample-start", type=float, default=0.0)
    train_parser.add_argument("--seed", type=int, default=42)
    monitor_parser = sub.add_parser("monitor", help="Evidently report and threshold alert")
    monitor_parser.add_argument("--amount-multiplier", type=float, default=1.0)
    monitor_parser.add_argument("--drift-threshold", type=float, default=0.10)
    retrain_parser = sub.add_parser("retrain", help="consume an alert after refreshed labels arrive")
    retrain_parser.add_argument("--labeled-csv", type=Path, required=True)
    retrain_parser.add_argument("--sample-fraction", type=float, default=0.10)
    retrain_parser.add_argument("--seed", type=int, default=43)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.command == "train":
        result = train(args.raw, root, args.sample_fraction, args.seed, args.sample_start)
    elif args.command == "monitor":
        result = monitor(root, args.amount_multiplier, args.drift_threshold)
    else:
        job_path = root / "artifacts/retrain_request.json"
        if not job_path.exists():
            parser.error("no queued retrain job; run monitor first")
        job = json.loads(job_path.read_text())
        if job["status"] != "queued_awaiting_mature_labels":
            parser.error(f"job status is {job['status']}")
        result = train(args.labeled_csv, root, args.sample_fraction, args.seed)
        job.update(status="completed", registered_version=result["registry"]["version"])
        job_path.write_text(json.dumps(job, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
