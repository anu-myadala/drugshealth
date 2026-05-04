# Methods, Tests, and Significance — GLP-1 FAERS Study

This document explains the statistical tests and data-mining techniques used in the project, what they measure, assumptions, how they were applied to the FAERS dataset, and the key findings from the full 13-quarter run (2023Q1–2026Q1).

## Data provenance & preprocessing
- Source: FDA FAERS quarterly ASCII files (DEMO, DRUG, REAC, OUTC, THER) for 13 quarters.
- Deduplication: grouped by `caseid`, kept the record with the latest `fda_dt` per `caseid`.
- Cohorts: `glp1` (SEMAGLUTIDE, LIRAGLUTIDE, DULAGLUTIDE, TIRZEPATIDE, EXENATIDE) vs `control` (metformin-class drugs).
- Reaction filtering: MedDRA PTs filtered for GI-specific terms (gastroparesis, pancreatitis, ileus, intestinal/bowel obstruction, etc.).
- Key cleaning steps applied in the run:
  - Event and therapy dates parsed with `pandas.to_datetime` accepting YYYYMMDD formats.
  - `time_to_onset_days` computed as difference between event date and earliest drug start date per primaryid.
  - Implausible weights (<30 kg or >300 kg) were clipped to NA and median-imputed.

## Tests & techniques

### 1) Chi-Square Test of Independence
- Purpose: test whether GI severe event incidence is independent of drug cohort (GLP-1 vs control).
- Data shape: 2×2 contingency table: rows = cohort (glp1, control), columns = GI severe (1) or not (0).
- Assumptions: expected counts reasonably large (met with our sample sizes). Independent reports assumed (FAERS is spontaneous reporting — independence is approximate).
- Result (full run): χ² = 166.63, p ≈ 4.02e-38 — statistically significant. Cramér's V ≈ 0.021 (very small effect size); interpretation: cohort difference exists but effect magnitude is small.

### 2) Proportional Reporting Ratio (PRR)
- Purpose: pharmacovigilance measure comparing reporting proportions of a target event between exposed (glp1) and comparator (control) groups.
- Formula: PRR = (a/(a+b)) / (c/(c+d)), where a = #exposed with event, b = #exposed without, c = #control with event, d = #control without.
- Regulatory rule-of-thumb (WHO-UMC): PRR > 2, χ² > 4, and a ≥ 3 indicates a signal.
- Result (full run): PRR ≈ 1.363 (95% CI ~ 1.30–1.43); WHO-UMC signal criteria not met because PRR < 2.
- Note: PRR is a reporting ratio, not an incidence rate. FAERS is subject to reporting bias and cannot provide absolute risks.

### 3) Mann-Whitney U Test (Weight vs Severity)
- Purpose: compare median weights between patients with severe GI events and those without (non-parametric because weight distribution is skewed).
- Result (GLP-1 cohort): n_severe = 4,651; median weight severe = 93.0 kg; non-severe median = 86.6 kg; p ≈ 6.35e-54; effect size (rank-biserial) r ≈ -0.12 (small).
- Interpretation: statistically significant difference in weight, but effect is small in magnitude.

### 4) Apriori Association Rules
- Purpose: discover frequently co-reported drugs/items associated with outcomes (e.g., hospitalization, GI severe).
- Setup: each patient = transaction; items = top concurrent drugs + HOSPITALIZED/GI_SEVERE_EVENT flags.
- Parameters: min_support=0.02, min_confidence=0.40, filter by lift ≥ 1.3.
- Result: a small number of actionable rules (examples: {FUROSEMIDE}→{HOSPITALIZED}, {PANTOPRAZOLE}→{HOSPITALIZED}, etc.). These are hypothesis-generating signals.

### 5) K-Means Clustering
- Purpose: identify patient phenotypes (clusters) by age, weight, polypharmacy, opioid use, time-to-onset, sex.
- Normalization: StandardScaler applied before clustering.
- Cluster selection: silhouette scores across k ∈ [2..8] to pick optimal k.
- Result: k=2 chosen (silhouette ≈ 0.78). Profiles indicate a large majority cluster and a smaller higher-risk cluster; further data cleaning could refine these clusters.

### 6) Predictive models (Logistic Regression & Random Forest)
- Purpose: predict `severity_flag` (hospitalized/LT/Death) from demographic and simple derived features.
- Split: 80/20 train/test stratified by target; RF hyperparameters tuned manually for recall/robustness.
- Primary metric: Recall (false negatives are costly in surveillance). AUC used for overall discrimination.
- Results: LR AUC ≈ 0.82, Recall ≈ 0.65; RF AUC ≈ 0.85, Recall ≈ 0.77. RF improves recall substantially and is preferred for surveillance.

## Key takeaways from this run (13 quarters)
- The cohort comparison yields a statistically significant but small effect of GLP-1 exposure on GI severe reporting (PRR ≈ 1.36; χ² significant but small effect size).
- No WHO-UMC PRR signal (PRR<2), but APRiori and clustering highlight subgroups and co-medications (e.g., opioids) that merit further investigation.
- Random Forest is effective for flagging reports likely to be hospitalized; could be used to prioritize case review.

## Limitations
- FAERS is spontaneous reporting data — subject to reporting bias, underreporting, duplicate reporting (mitigated by deduplication), and missing data.
- PRR is a disproportionality measure and cannot estimate absolute incidence.
- Time-to-onset calculation depends on therapy start-dates reported in THER and the event date in DEMO; missing or malformed dates reduce accuracy.

## Recommended next steps
1. Replace approximate date-diff logic (done) and re-evaluate time-to-onset distributions.
2. Remove/inspect outliers in weight and therapy dates; rerun clustering and model training.
3. If a regulatory signal is suspected for specific MedDRA PTs, cross-validate findings with claims/EHR or compute Empirical Bayes metrics (EBGM) for more robust disproportionality.


*Generated by the reproducible pipeline — see `run_full_pipeline.sh` for commands to rerun.*
