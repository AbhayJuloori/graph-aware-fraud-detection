"""Fraud Signal Room: live monitor, hand scorer, and model evidence. Run: streamlit run app.py"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import fraud_lab  # noqa: F401
except ModuleNotFoundError:  # running from a checkout without an installed package
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from fraud_lab.features import TYPES
from fraud_lab.monitoring import monitor

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
SUMMARY = ROOT / "docs" / "results" / "summary.json"
LIME, CORAL, CYAN, GREY = "#c6f432", "#ff5a36", "#5ad1ff", "#6b7079"
FEATURE_TEXT = {
    "amount_to_origin_balance": "amount ÷ sender balance",
    "amount_to_dest_balance": "amount ÷ receiver balance",
    "oldbalanceOrg": "sender balance (log)", "oldbalanceDest": "receiver balance (log)",
    "amount": "amount (log)", "hour_sin": "hour of day (sin)", "hour_cos": "hour of day (cos)",
    "dest_is_merchant": "receiver is a merchant",
}

st.set_page_config(page_title="Fraud Signal Room", page_icon="◉", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Mono:wght@400;600&display=swap');
    h1, h2, h3 { font-family: 'Instrument Serif', serif !important; font-weight: 400 !important; }
    h1 em { color: #c6f432; }
    [data-testid="stMetric"] { border: 1px solid #24272e; padding: 12px 14px; border-radius: 2px; }
    [data-testid="stMetricLabel"] p { text-transform: uppercase; letter-spacing: .06em; font-size: 11px; color: #6b7079; }
    .stTabs [data-baseweb="tab"] { text-transform: uppercase; letter-spacing: .06em; font-size: 12px; }
    .case { border-left: 2px solid #c6f432; padding: 4px 0 4px 14px; color: #a4a8b0; margin: 4px 0 14px; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown("# Fraud Signal <em>Room</em>", unsafe_allow_html=True)
st.caption("PaySim replay · MLflow @champion · synthetic data, not live fraud rates")


def ftext(name: str) -> str:
    return FEATURE_TEXT.get(name, name.replace("type_", "type is ").replace("_", " "))


@st.cache_data
def load_summary() -> dict | None:
    return json.loads(SUMMARY.read_text()) if SUMMARY.exists() else None


@st.cache_resource
def load_service():
    from fraud_lab.serving import FraudService

    return FraudService(ROOT)


with st.sidebar:
    st.markdown("### How to read this")
    st.markdown(
        "**Monitor** compares next month's transfers with the validation month and "
        "raises an alert when amounts or scores shift.\n\n"
        "**Score** sends one transfer through the registered champion and shows its "
        "top three reasons (TreeSHAP, log odds).\n\n"
        "**Evidence** shows why the simpler model won: graph features never cleared "
        "the +0.01 PR-AUC promotion gate."
    )
    st.divider()
    st.caption("Commands: `fraud-lab train` · `fraud-lab monitor` · `fraud-lab report`")

monitor_tab, score_tab, evidence_tab = st.tabs(["◉ Monitor", "⌁ Score a transfer", "▤ Evidence"])

# ---------------------------------------------------------------- Monitor
with monitor_tab:

    @st.fragment(run_every="30s")
    def live_status() -> None:
        status_path = ARTIFACTS / "monitor_status.json"
        if not status_path.exists():
            st.info("Run `fraud-lab monitor` to create the first monitoring snapshot.")
            return
        data = json.loads(status_path.read_text())
        alert = data["status"] == "alert"
        st.markdown(
            f"<div class='case'><b style='color:{CORAL if alert else LIME}'>"
            f"{'● DRIFT ALERT' if alert else '● HEALTHY'}</b> · last check "
            f"{data['checked_at_utc'][:19]} UTC · amount ×{data['amount_multiplier']} · "
            f"model v{data['model_version']}</div>",
            unsafe_allow_html=True,
        )
        a, b, c, d = st.columns(4)
        a.metric("Amount KS", f"{data['amount_ks']['statistic']:.3f}")
        b.metric("Score KS", f"{data['score_ks']['statistic']:.3f}")
        c.metric("Alert threshold", f"{data['threshold']:.2f}")
        job_path = ARTIFACTS / "retrain_request.json"
        job = json.loads(job_path.read_text())["status"] if alert and job_path.exists() else "none"
        d.metric("Retrain job", job.replace("_", " "))
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
        st.markdown("### Replay a shift")
        st.caption("Scales every replayed amount, rebuilds the amount features, and rescores "
                   "with the champion. Alert if KS ≥ 0.10 and p < 0.01.")
        multiplier = st.slider("Amount multiplier", 0.5, 4.0, 1.0, 0.25)
        if st.button("Run drift check", type="primary"):
            with st.spinner("Scoring replay and comparing distributions..."):
                result = monitor(ROOT, amount_multiplier=multiplier)
            st.toast(f"Monitor finished: {result['status']}")
            st.rerun()
    with right:
        reference_path = ARTIFACTS / "reference.parquet"
        current_path = ARTIFACTS / "monitored_current.parquet"
        if reference_path.exists() and current_path.exists():
            reference = pd.read_parquet(reference_path, columns=["raw_amount"])
            current = pd.read_parquet(current_path, columns=["raw_amount"])
            edges = np.linspace(0, 8, 41)

            def share(values: pd.Series) -> np.ndarray:
                counts, _ = np.histogram(np.log10(values.clip(lower=1)), bins=edges)
                return counts / len(values)

            frame = pd.concat([
                pd.DataFrame({"log10 amount": edges[:-1], "share": share(reference.raw_amount),
                              "window": "reference (validation)"}),
                pd.DataFrame({"log10 amount": edges[:-1], "share": share(current.raw_amount),
                              "window": "replay (monitored)"}),
            ])
            chart = alt.Chart(frame).mark_area(opacity=0.45, interpolate="monotone").encode(
                x=alt.X("log10 amount:Q", title="Transfer amount (log10 $)"),
                y=alt.Y("share:Q", title="Share of transfers", axis=alt.Axis(format="%"), stack=None),
                color=alt.Color("window:N", scale=alt.Scale(range=[GREY, LIME]),
                                legend=alt.Legend(orient="top", title=None)),
            ).properties(height=260)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("Train and run the monitor to populate the reference and replay windows.")

# ---------------------------------------------------------------- Score
with score_tab:
    st.markdown("### Score one transfer")
    st.caption("Only pre transaction fields. Post event balances and PaySim's own flag are "
               "never inputs.")
    form, out = st.columns([1, 1.3])
    with form, st.form("score"):
        kind = st.selectbox("Type", TYPES, index=TYPES.index("TRANSFER"))
        amount = st.number_input("Amount ($)", min_value=0.0, value=181_000.0, step=1000.0)
        sender_balance = st.number_input("Sender balance before ($)", min_value=0.0,
                                         value=181_000.0, step=1000.0)
        receiver_balance = st.number_input("Receiver balance before ($)", min_value=0.0,
                                           value=0.0, step=1000.0)
        step = st.slider("Hour step", 1, 743, 400)
        receiver_is_merchant = st.checkbox("Receiver is a merchant", value=False)
        submitted = st.form_submit_button("Score", type="primary")
    with out:
        if submitted:
            try:
                service = load_service()
            except Exception as exc:  # noqa: BLE001 - surface missing model to the user
                st.error(f"No champion model available ({exc}). Run `fraud-lab train` first.")
            else:
                frame = pd.DataFrame([{
                    "step": step, "type": kind, "amount": amount, "nameOrig": "C_DEMO_SENDER",
                    "oldbalanceOrg": sender_balance,
                    "nameDest": "M_DEMO" if receiver_is_merchant else "C_DEMO_RECEIVER",
                    "oldbalanceDest": receiver_balance,
                }])
                result = service.score(frame)[0]
                probability = result["fraud_probability"]
                summary = load_summary()
                threshold = (summary["models"][summary["champion"]]["validation"]["threshold"]
                             if summary else 0.5)
                flagged = probability >= threshold
                st.markdown(
                    f"<div class='case'><b style='color:{CORAL if flagged else LIME}'>"
                    f"{'● FLAG FOR REVIEW' if flagged else '● CLEAR'}</b> · fraud probability "
                    f"<b style='color:#f2f1ec'>{probability:.4f}</b> · model v{result['model_version']}"
                    f" · flag line {threshold:.5f}</div>",
                    unsafe_allow_html=True,
                )
                reasons = pd.DataFrame(result["reason_codes"])
                reasons["feature"] = reasons.feature.map(ftext)
                chart = alt.Chart(reasons).mark_bar().encode(
                    x=alt.X("shap_log_odds:Q", title="Contribution (log odds)"),
                    y=alt.Y("feature:N", sort=None, title=None, axis=alt.Axis(labelLimit=240)),
                    color=alt.condition(alt.datum.shap_log_odds > 0, alt.value(CORAL), alt.value(CYAN)),
                    tooltip=["feature", alt.Tooltip("shap_log_odds:Q", format=".2f")],
                ).properties(height=170)
                st.altair_chart(chart, use_container_width=True)
                st.caption("Coral pushes toward fraud, cyan toward legitimate. Try sending "
                           "less than the full balance and watch the top reason flip.")
        else:
            st.info("Fill the form and press Score. The default is the classic PaySim fraud "
                    "pattern: a transfer that empties the sender's account.")

# ---------------------------------------------------------------- Evidence
with evidence_tab:
    summary = load_summary()
    if summary is None:
        st.info("Run `fraud-lab report` to build the evidence summary.")
    else:
        labels = {"logistic_baseline": "Logistic regression",
                  "xgboost_baseline": "XGBoost, transaction only",
                  "xgboost_graph": "XGBoost + graph"}
        rows = [{
            "model": labels[name],
            "validation PR-AUC": m["validation"]["pr_auc"], "test PR-AUC": m["test"]["pr_auc"],
            "test recall @ val 1% FPR": m["test"]["recall_at_validation_1pct_fpr"],
            "test precision": m["test"]["tp"] / max(1, m["test"]["tp"] + m["test"]["fp"]),
            "champion": "★" if name == summary["champion"] else "",
        } for name, m in summary["models"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                     column_config={c: st.column_config.NumberColumn(format="%.4f") for c in
                                    ("validation PR-AUC", "test PR-AUC", "test recall @ val 1% FPR",
                                     "test precision")})
        left, right = st.columns(2)
        with left:
            st.markdown("### Graph lift never clears the gate")
            cohorts = pd.DataFrame(summary["cohorts"]).melt(
                id_vars=["id"], value_vars=["validation_lift", "test_lift"],
                var_name="window", value_name="lift")
            bars = alt.Chart(cohorts).mark_bar().encode(
                x=alt.X("id:N", title=None), xOffset="window:N",
                y=alt.Y("lift:Q", title="Graph PR-AUC lift"),
                color=alt.Color("window:N", scale=alt.Scale(range=[CORAL, LIME]),
                                legend=alt.Legend(orient="top", title=None)),
            )
            gate = alt.Chart(pd.DataFrame({"y": [summary["promotion_margin"]]})).mark_rule(
                strokeDash=[5, 4], color="#a4a8b0").encode(y="y:Q")
            st.altair_chart((bars + gate).properties(height=260), use_container_width=True)
        with right:
            st.markdown("### Graph features rarely fire")
            coverage = pd.DataFrame([{"feature": ftext(k), "share non-zero": v["share_nonzero_all"]}
                                     for k, v in summary["graph_coverage"].items()])
            st.altair_chart(alt.Chart(coverage).mark_bar(color=CORAL).encode(
                x=alt.X("share non-zero:Q", axis=alt.Axis(format="%")),
                y=alt.Y("feature:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
            ).properties(height=260), use_container_width=True)
        ds = summary["dataset"]
        st.markdown(
            f"<div class='case'>{ds['senders_seen_once_share']:.2%} of senders appear exactly once, "
            f"so sender history, shared counterparties and ring flags have nothing to link. "
            f"{ds['drain']['fraud_share']:.1%} of fraud empties the sender's balance, which one "
            f"ratio feature captures without any graph.</div>",
            unsafe_allow_html=True,
        )
