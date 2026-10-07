# Experiment log

| ID | Purpose | Result | Decision |
|---|---|---|---|
| E0 | Inspect full PaySim source | 6,362,620 rows; 8,213 fraud labels; 6,353,307 distinct origin IDs. | Treat graph value as a hypothesis, not an assumed improvement. |
| E1 | 3% uniform sample, seed 42 | End-to-end ingestion, temporal graph, three models, MLflow registration, API. Only 91 fraud cases in train. | Keep as pipeline smoke test; do not publish its metrics as the project result. |
| E2 | 10% uniform sample, seed 42 | Train 381,946 rows / 330 fraud; validation 129,054 / 62; test 124,359 / 411. Graph PR-AUC lift on test: -0.0021. | Scale to 25% because validation positives are scarce. |
| E3 | First 25% uniform cohort, seed 42 | Train 956,058 rows / 809 fraud; validation 322,856 / 168; test 311,814 / 1,064. Graph validation lift +0.0012 but test lift -0.0038. The original highest-validation-PR-AUC rule registered the graph model. | Treat the tiny validation advantage as insufficient for added complexity; revise the promotion gate and confirm on disjoint rows. E3 test is now exploratory, not the final confirmation. |
| E4 | Disjoint next 25% cohort, seed 42 | See [results.json](results.json) for the revised rule and fresh held-out result. | Publish E4 as the confirmation run and retain E3's negative result. |
| M1 | E4 natural later-window replay | Amount KS 0.0335 and score KS 0.0104, below the 0.10 alert threshold. Evidently report saved. | Healthy. |
| M2 | E4 3× amount replay | Amount KS 0.2876 and score KS 0.2065. Evidently report saved; retrain request queued. | Alert; wait for post-alert labels before retraining. |
| R1 | Rerun E4 with diagnostics enabled | Every PR-AUC in results.json reproduced to 6 decimals; champion registered as a new version of the same transaction-only model. Diagnostics: sender degree non-zero on 0.1% of test rows, shared counterparties and ring flag on 0%; 97.8% of all fraud drains the full origin balance. | Explains the null graph result; publish via `fraud-lab report`. |
| M3 | Drift sweep, amount multipliers 0.5 to 4 | Alert at ≤0.75× and ≥1.5×; at 3×, alerts per 100k rise from 1,415 to 5,737. | Report the investigator-load cost of drift, not only the KS statistic. |
| M4 | Daily KS on the natural replay | 5 of 17 days cross the 0.10 line; days 16 and 17 hold 492 and 17 rows where PaySim's tail is mostly fraud. | A production monitor needs minimum-volume guards and per-window thresholds. |

The alert replay changes transaction amount and rescoring inputs. It does **not** simulate adversarial behavior or prove retraining would improve fraud outcomes.
