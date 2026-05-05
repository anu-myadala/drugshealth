Project Full Summary — GLP-1 FAERS Adverse Event Study

Purpose & Research Question
---------------------------
This project investigates whether GLP-1 receptor agonists (a rapidly expanding class of medications used in diabetes and weight management) are disproportionately reported with severe gastrointestinal (GI) adverse events in the FDA FAERS spontaneous reporting system. The central research questions:

- Do GLP-1 agents show a pharmacovigilance signal for severe GI terms (gastroparesis, pancreatitis, ileus, bowel obstruction)?
- Which patient phenotypes (clusters) and medication combinations (Apriori rules) are associated with elevated severe GI reporting?
- Can we predict which adverse-event reports will escalate to hospitalization or life-threatening outcomes using patient-level features?

Why it matters
---------------
Rapid uptake of GLP-1s in clinical practice requires robust post-marketing safety monitoring for serious adverse events. FAERS provides a large, public dataset of spontaneous reports that can detect signals warranting further epidemiologic validation. Findings inform clinicians, regulators, and researchers about potential high-risk subgroups and drug combinations.

Data & Timeframe
-----------------
- FDA FAERS ASCII quarterly zip files (DEMO, DRUG, REAC, OUTC, THER)
- Study window: 2023Q1 → 2026Q1 (13 consecutive quarters)
- Scripts are in Python and use `pandas`, `scikit-learn`, `mlxtend`, `plotly`, and `python-pptx`.

Cohort definitions
------------------
- GLP-1 cohort: reports containing an active ingredient that matches the curated GLP-1 list (SEMAGLUTIDE, LIRAGLUTIDE, DULAGLUTIDE, TIRZEPATIDE, EXENATIDE).
- Control cohort: reports containing control drugs (METFORMIN, SITAGLIPTIN, EMPAGLIFLOZIN, DAPAGLIFLOZIN, GLIPIZIDE, GLIMEPIRIDE).

ETL pipeline (what & how)
-------------------------
1) Ingestion: read each quarterly FAERS zip; parse tables using dollar-delimited format.
2) Per-quarter processing:
   - Normalize `primaryid` and `caseid` to string.
   - Deduplicate `DEMO` per quarter by `caseid`, keeping the latest `caseversion`/`fda_dt`.
   - Tag drugs by case-insensitive substring matching on `prod_ai` (active ingredient).
   - Filter `REAC` for GI Preferred Terms (conservative curated PT list) and mark `is_gi_severe`.
   - Parse `THER.start_dt` for therapy start date and compute `time_to_onset_days` relative to `event_date`.
3) Global deduplication: after concatenating all quarters, deduplicate by `caseid` and keep the latest `fda_dt` to avoid double-counting.
4) Imputation & feature engineering:
   - Median imputation for `age_yr` and `wt_kg` grouped by `sex_clean` × `cohort`, fallback to global median.
   - Polypharmacy count = distinct `prod_ai` per `primaryid`.
   - Concurrent opioid flag from a curated opioid drug list.
   - Additional features: `log_poly`, `age_wt_interaction`.

Statistical methods
-------------------
- Chi-Square test of independence for cohort × GI severe (2×2 contingency table). Report χ² statistic, df, p-value, and Cramér's V for effect size.
- Proportional Reporting Ratio (PRR): PRR = (a/(a+b)) / (c/(c+d)) where a = GLP-1 GI reports, b = GLP-1 non-GI reports, c = control GI reports, d = control non-GI reports. 95% Wald CI computed on log(PRR). WHO-UMC signal criteria: PRR ≥ 2, χ² ≥ 4, n ≥ 3.
- Reporting Odds Ratio (ROR) also computed as (a/b) / (c/d) with 95% CI.
- Mann–Whitney U test for continuous comparisons (weight) due to non-normality.

Data mining & modeling
----------------------
- Apriori rules: market-basket items = concurrent medication names (top-40) + outcome flags. Parameters: min_support=0.02, min_confidence=0.40, min_lift=1.3.
- K-Means clustering: StandardScaler on numeric features, silhouette method for k selection, n_init=10, random_state set for reproducibility.
- Logistic Regression: interpretable coefficients, used for odds ratio communication.
- Random Forest: tuned for recall; 5-fold cross-validation to report CV AUC.

Metrics & validation
---------------------
- Classification: primary metric = recall (sensitivity). Also report ROC-AUC, F1, precision, and confusion matrices. Use 80/20 train/test split with CV for hyperparameter validation.
- Clustering: silhouette and Davies-Bouldin indices reported to justify k selection.
- PRR/ROR: 95% CI and WHO-UMC rule followed for signal detection.
- Sensitivity checks: alternate GI PT lists (broader vs conservative) and TTO plausibility bounds tested; results recorded in logs and can be reproduced by configuration.

Complete chronological steps performed in the project (reproducible script-order)
---------------------------------------------------------------------------------
1. `01_etl.py` — read FAERS zips, build `fact_adverse_event.csv` (includes cohort labeling, time-to-onset, polypharmacy, opioid flag, severity flag).
2. `02_eda_stats.py` — descriptive statistics, Chi-Square, PRR / ROR with 95% CI, Mann–Whitney U, and EDA figures saved to `reports/figures/` and `reports/eda_results.json`.
3. `03_data_mining.py` — Apriori rules extracted, K-Means clustering, LR/RF training and evaluation, saves `reports/mining_results.json` and model artifacts to `models/`.
4. `04_dashboard.py` — Plotly interactive dashboard generator (writes `reports/glp1_dashboard.html`).
5. `04_dashboard_enhanced.py` — Chart.js enhanced static dashboard generator (writes `reports/glp1_dashboard_enhanced.html`).
6. `04_dashboard_streamlit.py` — Streamlit app for interactive exploration and live RF risk calculator.
7. `05_presentation.py` — Auto-generate a 14-slide presentation with embedded figures and expanded speaker notes; saves `reports/GLP1_FAERS_Presentation.pptx`.

Key numeric results (from latest run)
-------------------------------------
- Unique cases after dedup: 367,883
- GLP-1 cohort: 206,974; Control: 160,909
- PRR (pooled GLP-1): 1.363 (95% CI 1.301–1.429) — WHO-UMC signal: NO
- Per-drug PRR: Semaglutide=2.566, Liraglutide=2.116, Dulaglutide=1.441, Tirzepatide=1.010, Exenatide=0.284
- Random Forest AUC = 0.8523, Recall = 0.7625 (primary surveillance metric)
- K-Means best k = 5 (silhouette = 0.5354)

Deliverables produced
---------------------
- All processed CSVs and model artifacts under `data/processed/` and `models/`.
- Reports: `reports/eda_results.json`, `reports/mining_results.json`, `reports/RESULTS_LATEST.md`, `reports/PROJECT_FULL_SUMMARY.md`.
- Dashboards: `reports/glp1_dashboard.html`, `reports/glp1_dashboard_enhanced.html`, Streamlit app code `04_dashboard_streamlit.py`.
- Presentation: `reports/GLP1_FAERS_Presentation.pptx` (14 slides) with expanded speaker notes.

How to reproduce the analysis
----------------------------
- Ensure Python 3.11+ and create virtualenv: `python3 -m venv .venv && source .venv/bin/activate`.
- Install dependencies: `pip install -r requirements.txt`.
- Place FAERS quarterly zip files and run ETL via:

```bash
FAERS_ZIP_LIST="/abs/path/faers_ascii_2023q1.zip:...:..." ./.venv/bin/python 01_etl.py
./.venv/bin/python 02_eda_stats.py
./.venv/bin/python 03_data_mining.py
./.venv/bin/python 04_dashboard_enhanced.py
./.venv/bin/python 04_dashboard.py
./.venv/bin/python 05_presentation.py
```

Limitations & ethical considerations
-----------------------------------
- FAERS reports are voluntary and subject to reporting bias. PRR detects disproportionality in reporting, not incidence or causality.
- Individual-level PHI must not be published. The repository should not include raw narratives or patient identifiers when shared publicly.
- All downstream uses of the models (e.g., risk calculator) should be considered research-use-only; not for clinical decision making without validation in structured clinical datasets.

Contact & provenance
--------------------
- Source code and artifacts are in this repository: `anu-myadala/drugshealth` on GitHub.
- For details about specific processing choices, see `reports/METHODS_VALIDATION.md` and the presentation speaker notes.

Appendix
--------
- Full machine-readable outputs: `reports/eda_results.json` and `reports/mining_results.json`.
- Figures and tables: `reports/figures/` (age distribution, PRR forest plot, kmeans profiles, ROC curves, apriori rules, heatmaps, etc.).
- For peer-reviewed write-up: suggested sections and figure/table assignments are included in the repository README and the presentation slide order.
