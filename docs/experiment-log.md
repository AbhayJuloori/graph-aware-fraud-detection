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

The alert replay changes transaction amount and rescoring inputs. It does **not** simulate adversarial behavior or prove retraining would improve fraud outcomes.
