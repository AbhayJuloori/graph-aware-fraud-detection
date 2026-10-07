# Methodology

This project asks one question: **do leakage-safe graph features improve fraud ranking enough to justify serving a graph?** Everything else (registry, API, monitoring) exists so that the answer, whichever way it goes, ships safely.

## 1. Data and cohort

- **Source.** PaySim (`ealaxi/paysim1`), 6,362,620 synthetic mobile money transactions over 743 hourly steps, 8,213 fraud labels (0.129%). Fraud occurs only in `TRANSFER` (4,097) and `CASH_OUT` (4,116).
- **Columns used.** `step, type, amount, nameOrig, oldbalanceOrg, nameDest, oldbalanceDest`. `newbalanceOrig`, `newbalanceDest` and `isFlaggedFraud` are post-event or generator outputs and are never read.
- **Cohort.** A seeded uniform draw per row, independent of labels. The published run (E4) keeps draws in `[0.25, 0.50)`, which is disjoint from the exploratory E3 cohort `[0, 0.25)`.
- **Split.** Whole steps by quantile: train ≤ 281, validation 282 to 355, test > 355. Counts: 955,801 / 812 fraud, 323,099 / 208, 312,885 / 1,055.

## 2. Features

**Transaction (13).** Log amount and balances, `amount / (oldbalanceOrg + 1)` and `amount / (oldbalanceDest + 1)` capped at 10⁶, hour of day as sin/cos, merchant receiver flag, one-hot type.

**Graph (11), built by `TemporalGraph`.** Sender/receiver degree, PageRank, shared counterparties, `ring_flag` (shared counterparty > 0, a possible triangle), same weak component, component sizes, sender/receiver neighbor fraud rates.

Time rules:

1. Every row in step *t* is scored against the graph at the end of step *t − 1*; same-step rows cannot see each other or themselves.
2. Step *t*'s edges are added after scoring.
3. Labels update neighbor fraud rates only in the training window.
4. PageRank and components refresh every 168 steps (one simulated week); degrees are live.
5. A graph champion would serve from the snapshot frozen at the training cutoff.

Unit tests cover same-step isolation, label masking, unsorted input alignment, and the irrelevance of post-event columns.

## 3. Models and selection

| Candidate | Features | Notes |
|---|---|---|
| Logistic regression | transaction | standardized, `class_weight="balanced"` |
| XGBoost | transaction | 180 trees, depth 5, lr 0.08, `scale_pos_weight` = neg/pos (≈1,176) |
| XGBoost | transaction + graph | same hyperparameters |

- **Ranking metric:** PR-AUC (average precision). With 0.13% positives, ROC-AUC and accuracy are uninformative.
- **Operating point:** the smallest score with validation FPR ≤ 1%, reused unchanged on test.
- **Promotion gate:** the graph model is champion only if its validation PR-AUC beats the transaction XGBoost by ≥ 0.01 absolute. This gate was adopted after E3 (see the experiment log), so E4 on disjoint rows is the confirmatory run.

## 4. Results (E4, held-out test)

| Model | Val PR-AUC | Test PR-AUC | Test recall @ val 1% FPR | Test precision |
|---|---:|---:|---:|---:|
| Logistic | 0.0659 | 0.2251 | 61.7% | |
| XGBoost, transaction | 0.9367 | 0.9785 | 100% | 23.8% |
| XGBoost + graph | 0.9347 | 0.9789 | 100% | |

Graph lift: validation −0.0020, test +0.0004. Across cohorts the sign flips (E2 −0.0054 / −0.0021, E3 +0.0012 / −0.0038). Conclusion: **no demonstrated lift**; the transaction model is champion.

**Why the graph adds nothing here.** 99.85% of senders appear exactly once in the full dataset, so sender history, shared counterparties and ring flags are zero on essentially every held-out row (sender degree non-zero 0.1%, shared counterparties 0%). Only 0.5% of fraud receivers are reused and 0.2% ever send money, so mule chains cannot be traced. Meanwhile 97.8% of fraud drains the full origin balance, against 0.0002% of legitimate TRANSFER/CASH_OUT rows; the ratio feature carries a mean |SHAP| of 6.4 log odds, about 6× the next feature. This is a property of PaySim's fraud generator and does not transfer to live data.

**Operating tradeoff.** At the validation threshold the test window flags 4,427 transfers to catch all 1,055 frauds (precision 0.24). The test ROC curve shows that about 0.12% FPR still recovers 99.9% recall at roughly 0.73 precision; a production threshold should be chosen on validation with real review and loss costs, not on test.

## 5. Explanations

`/score` returns the champion's probability and the three largest signed TreeSHAP contributions (`pred_contribs`, log odds). `fraud-lab report` also stores global mean |SHAP| on a test sample that keeps every fraud row, and one worked example per outcome (caught fraud, false alarm, cleared transfer).

## 6. Monitoring

- **Reference:** validation-window features and champion scores. **Current:** the later test window, optionally with every amount scaled by a multiplier, amount features rebuilt, and **rescored** by the champion.
- **Alert:** two-sample KS on deterministic 20,000-row samples; alert if amount or score KS ≥ 0.10 with p < 0.01. Evidently writes an HTML drift report; report failures are recorded and do not block the alert.
- **Action:** an alert writes `retrain_request.json` with status `queued_awaiting_mature_labels`. `fraud-lab retrain --labeled-csv` reruns the full chronological evaluation, gate and registration, then marks the job completed.
- **Sweep:** alert at ≤ 0.75× and ≥ 1.5×; at 3×, KS 0.288 (amount) and 0.206 (score), and alerts per 100k rise from 1,415 to 5,737.
- **Window sensitivity:** daily checks on the unshifted replay cross the line on 5 of 17 days, including two near-empty tail days. Production alerting needs minimum-volume guards and window-specific thresholds.

## 7. Reproducibility

```bash
uv run fraud-lab train --sample-fraction 0.25 --sample-start 0.25   # ~70 s on a laptop
uv run fraud-lab monitor
uv run fraud-lab report                                             # site/data + docs/figures
```

Seeds are fixed through sampling, XGBoost and SHAP sampling; a from-scratch rerun reproduced every PR-AUC in `docs/results.json` to six decimals.

## 8. Limits

PaySim is synthetic and unusually separable; scores here are not live fraud estimates. The null graph result is specific to data without repeat actors. NetworkX is a bounded-experiment engine, not a serving graph. See [production-notes.md](production-notes.md).
