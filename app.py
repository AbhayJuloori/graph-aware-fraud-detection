"""Live local dashboard: reads monitor status and can replay a drift scenario."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from fraud_lab.monitoring import monitor

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"

st.set_page_config(page_title="Fraud Signal Room", page_icon="◉", layout="wide")
st.title("Fraud Signal Room")
st.caption("PaySim replay · registered champion · 30-second status refresh")


@st.fragment(run_every="30s")
def live_status() -> None:
    status_path = ARTIFACTS / "monitor_status.json"
    if not status_path.exists():
        st.info("Run `fraud-lab monitor` to create the first monitoring snapshot.")
        return
    data = json.loads(status_path.read_text())
    color = "🔴" if data["status"] == "alert" else "🟢"
    st.subheader(f"{color} {data['status'].title()}")
    st.caption(f"Last check: {data['checked_at_utc']} · amount multiplier {data['amount_multiplier']}×")
    a, b, c = st.columns(3)
    a.metric("Amount KS", f"{data['amount_ks']['statistic']:.3f}")
    b.metric("Score KS", f"{data['score_ks']['statistic']:.3f}")
    c.metric("Alert threshold", f"{data['threshold']:.2f}")
    if data["status"] == "alert":
        job_path = ARTIFACTS / "retrain_request.json"
        if job_path.exists():
            job = json.loads(job_path.read_text())
            st.warning(f"Retrain job: {job['status'].replace('_', ' ')}")
    if data["evidently_report"] == "ok":
        st.download_button("Download Evidently report",
                           data=(ARTIFACTS / "drift_report.html").read_bytes(),
                           file_name="drift_report.html", mime="text/html")
    else:
        st.error(data["evidently_report"])


live_status()
st.divider()
left, right = st.columns([1, 2])
with left:
    multiplier = st.slider("Replay amount multiplier", 0.5, 4.0, 1.0, 0.1)
    if st.button("Run drift check", type="primary"):
        with st.spinner("Scoring replay and comparing distributions..."):
            result = monitor(ROOT, amount_multiplier=multiplier)
        st.success(f"Monitor finished: {result['status']}")
        st.rerun()
with right:
    reference_path = ARTIFACTS / "reference.parquet"
    current_path = ARTIFACTS / "monitored_current.parquet"
    if not current_path.exists():
        current_path = ARTIFACTS / "current.parquet"
    if reference_path.exists() and current_path.exists():
        reference = pd.read_parquet(reference_path, columns=["score"])
        current = pd.read_parquet(current_path, columns=["score"])
        high_reference = 100 * float((reference.score >= 0.8).mean())
        high_current = 100 * float((current.score >= 0.8).mean())
        st.metric("High-risk score share (≥0.8)", f"{high_current:.2f}%",
                  f"{high_current - high_reference:+.2f} pp vs reference")
        bins = np.linspace(0.8, 1, 11)
        reference_hist, _ = np.histogram(reference.score, bins=bins)
        current_hist, _ = np.histogram(current.score, bins=bins)
        chart = pd.DataFrame({"reference": 100 * reference_hist / len(reference),
                              "current": 100 * current_hist / len(current)},
                             index=[f"{left:.2f}" for left in bins[:-1]])
        st.caption("High-risk score tail · share of all transactions per bin (%)")
        st.bar_chart(chart, height=220)
    else:
        st.info("Train the model to populate reference and current windows.")
