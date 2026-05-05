Methods & Validation — GLP-1 FAERS Study

Summary
-------
This document summarizes the ETL, analysis, and validation steps implemented for the GLP-1 FAERS adverse-event study (FAERS 2023Q1–2026Q1).

1) Data ingestion & ETL
- Source: FDA FAERS ASCII quarterly zip files (DEMO, DRUG, REAC, OUTC, THER).
- Input ordering: FAERS_ZIP_LIST environment variable or FAERS_DIR lookup.
- Per-quarter processing: read tables, normalize primaryid/caseid, deduplicate DEMO per-quarter (keep latest caseversion/fda_dt), tag GLP-1 & control drugs by active ingredient string matching, identify GI PTs using a conservative MedDRA term list.
- Global deduplication: after concatenating quarters, deduplicate by caseid keeping latest fda_dt (to avoid double-counted reports across quarters).
- Output: `data/processed/fact_adverse_event.csv`, `data/processed/drug_records.csv`, `data/processed/reaction_records.csv`.

2) Key preprocessing choices & rationale
- Drug matching: simple case-insensitive substring matching of `prod_ai` to identify GLP-1s and controls. This favors recall of brand/generic mentions in a noisy field.
- GI mapping: curated list of MedDRA PTs selected to reduce false positives in the PRR background. A `GI_BROAD` set is also available for sensitivity checks.
- Time-to-onset (TTO): computed from THER.start_dt parsed as YYYYMMDD when available; TTO filtered with bounds (TTO_MIN_DAYS, TTO_MAX_DAYS) to remove implausible intervals.
- Missing values: Median imputation for `age_yr` and `wt_kg` grouped by `sex_clean` × `cohort`, with fallback to global median. This preserves group medians and avoids model collapse due to NaNs.

3) EDA & statistical testing
- Descriptives: cohort counts, percent female, median age/weight, quarterly trends.
- Chi-Square test: 2×2 contingency (GLP-1 vs control × GI severe vs not). Cramér's V calculated for effect size.
- PRR: computed as (a/(a+b)) / (c/(c+d)) with Wald 95% CI on log(PRR). WHO-UMC signal criteria used: PRR ≥ 2, χ² ≥ 4, n ≥ 3.
- Mann–Whitney U: used for weight comparisons due to non-normal distribution.

4) Data mining & modeling
- Apriori: transaction = set of concurrent drugs (top-N) + outcome labels (HOSPITALIZED, GI_SEVERE_EVENT). Parameters: min_support=0.02, min_confidence=0.40, min_lift=1.3.
- K-Means: features scaled with StandardScaler; silhouette method used to choose k; cluster profiling via medians and rates.
- Classification: Logistic Regression (interpretable coefficients → ORs) and Random Forest (high recall). Feature engineering: log(polypharmacy), age×weight interaction, label encoding for `glp1_drug`. Primary metric: recall (sensitivity) to minimize missed severe outcomes. RF cross-validation: 5-fold CV for AUC reporting.

5) Validation & sensitivity checks
- 5-fold CV performed for Random Forest AUC; reported mean ± std in `reports/mining_results.json`.
- Sensitivity analyses: alternate GI term sets (broad vs conservative) and TTO bounds were tested; results compared to primary analysis — differences are reported in logs and can be reproduced via config.
- Limitations: FAERS is a spontaneous reporting system — reporting bias, missing denominator, and confounding by indication may affect estimates. PRR is a relative disproportionality metric, not an incidence rate.

6) Reproducibility
- Scripts: `01_etl.py`, `02_eda_stats.py`, `03_data_mining.py`, `06_star_schema_loader.py`.
- Environment: `requirements.txt` lists Python packages. A `.venv` can be created via `python3 -m venv .venv` followed by `source .venv/bin/activate` and `pip install -r requirements.txt`.
- Inputs: supply FAERS quarterly zip files and set `FAERS_ZIP_LIST` to a colon-separated list of absolute zip paths, OR place them under FAERS_DIR and leave FAERS_ZIP_LIST unset.

Contact
-------
For reproducibility questions or to request de-identified intermediate datasets, contact the study author and reference the GitHub repository.
