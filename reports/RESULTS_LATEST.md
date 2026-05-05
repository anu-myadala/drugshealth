Results — Latest Run (FAERS 2023Q1 → 2026Q1)

Overview
--------
This file captures the key numeric results and figures from the latest end-to-end pipeline run (ETL → EDA → Data Mining) using FAERS quarterly ASCII files 2023Q1–2026Q1.

Dataset
-------
- Total unique cases after global deduplication: 367,883
- GLP-1 cohort (identified by active ingredient): 206,974
- Control cohort (metformin-class controls): 160,909
- Total severe GI events (across both cohorts): 7,303
- Total severity_flag=1 events (hospitalization / life-threatening / death): 98,131

Descriptive statistics (cohort-level)
------------------------------------
GLP-1 cohort (n=206,974):
- Mean age = 56.23 years (median = 56.0, SD = 11.63)
- Mean weight = 91.8 kg (median = 86.6)
- Female: 60.7%
- Severe GI event rate (GI severe): 2.25%
- Severity (severity_flag=1) rate: 11.2%
- Concurrent opioid reporting: 1.3%
- Polypharmacy median: 1.0

Control cohort (n=160,909):
- Mean age = 65.89 years (median = 68.0, SD = 12.27)
- Mean weight = 83.29 kg (median = 85.0)
- Female: 44.6%
- Severe GI event rate (GI severe): 1.65%
- Severity (severity_flag=1) rate: 46.6%
- Concurrent opioid reporting: 10.3%
- Polypharmacy median: 6.0

Statistical testing (key results)
---------------------------------
Chi-Square Test (cohort × GI severe):
- Contingency: control (No GI Severe=158,257; GI Severe=2,652), glp1 (No GI Severe=202,323; GI Severe=4,651)
- χ² = 166.634, df = 1, p = 4.02e-38 → reject H₀
- Cramér's V = 0.0213 (small effect size)

Proportional Reporting Ratio (PRR):
- PRR (GLP-1 vs Control) = 1.363 (95% CI 1.301–1.429)
- Reporting Odds Ratio (ROR) = 1.372 (95% CI 1.307–1.439)
- WHO-UMC signal criteria (PRR ≥ 2, χ² ≥ 4, n ≥ 3):
  - PRR ≥ 2: No
  - χ² ≥ 4: Yes
  - n ≥ 3: Yes
  - WHO-UMC signal: False (because PRR < 2)

Per-drug PRR (GLP-1 agents vs Metformin control):
- Semaglutide: n=61,976; GI events=2,621; PRR = 2.566
- Liraglutide: n=6,738; GI events=235; PRR = 2.116
- Dulaglutide: n=23,579; GI events=560; PRR = 1.441
- Tirzepatide: n=136,324; GI events=2,269; PRR = 1.010
- Exenatide: n=2,990; GI events=14; PRR = 0.284

Mann–Whitney U Test (weight difference within GLP-1 cohort)
- Severe GI: n=4,651, median weight = 95.0 kg
- Non-severe: n=202,323, median weight = 86.6 kg
- U = 526,204,080, p = 2.74e-52 → statistically significant (effect size r = -0.118)

Data Mining & Models
--------------------
Clustering (K-Means):
- k = 5 (default for performance; silhouette skipped on full dataset); Davies-Bouldin = 0.6964 (sampled)
- Cluster sizes (GLP-1 cohort):
  - Cluster 0 (Moderate-Risk Active): n = 76,791
  - Cluster 1 (Low-Risk Stable): n = 115,606
  - Cluster 2 (Critical Risk): n = 2,718
  - Cluster 3 (High-Risk Vulnerable): n = 4,543
  - Cluster 4 (Very High-Risk Complex): n = 7,316
- Representative cluster metrics: age_mean, wt_mean, polypharmacy_mean, opioid_pct, gi_severe_pct, severity_pct, pct_female, tto_mean (see `reports/mining_results.json` for full table)

Apriori Association Rules:
- Frequent itemsets: 68
- Rules satisfying conf≥0.40 & lift≥1.3: 6 (top rules include: GI_SEVERE_EVENT → HOSPITALIZED; INSULIN co-occurrence pairs)

Classification (severity prediction)
- Dataset: GLP-1 cohort samples used for classification (post-outlier handling): 198,742
- Class balance (positive=severity_flag=1): 9.90%
- Train/test split: n_train = 158,993; n_test = 39,749

Logistic Regression (interpretable):
- AUC = 0.8111
- F1 = 0.4276
- Recall = 0.6307
- Precision = 0.3234

Random Forest (surveillance-focused):
- AUC = 0.8438
- F1 = 0.4298
- Recall = 0.7334 (primary metric)
- Precision = 0.3039
- CV AUC: skipped (runtime optimization)

Extended modeling (feature reduction + alternative classifiers)
-------------------------------------------------------------
- PCA (scaled) explained variance: PC1 = 23.84%, PC2 = 23.05% (cumulative = 46.89%)
- DBSCAN clusters (PCA sample, tuned): 1
- Decision Tree (balanced, max_depth=5): Accuracy = 0.7911, Precision = 0.3074, Recall = 0.6902, F1 = 0.4253, ROC-AUC = 0.7879
- Gaussian Naive Bayes: Accuracy = 0.8662, Precision = 0.3910, Recall = 0.3491, F1 = 0.3689, ROC-AUC = 0.7742
- Random Forest (balanced_subsample): Accuracy = 0.8562, Precision = 0.3671, Recall = 0.3920, F1 = 0.3791, ROC-AUC = 0.6993

Artifacts generated
-------------------
- data/processed/fact_adverse_event.csv
- data/processed/glp1_clustered.csv
- reports/eda_results.json
- reports/mining_results.json
- reports/extended_mining_results.json
- reports/extended_model_comparison.csv
- reports/figures/extended_model_comparison_table.png
- reports/figures/extended_rf_feature_importances.png
- reports/figures/*.png (all EDA & model figures)

Figures and tables referenced in the results above are saved under `reports/figures/`.

Notes & interpretation
----------------------
- The combined dataset shows a statistically significant association between GLP-1 use and severe GI event reporting, but the overall PRR for the pooled GLP-1 group is below the conservative WHO-UMC threshold (PRR<2). However, some individual agents (Semaglutide and Liraglutide) exceed PRR ≥ 2 and may merit targeted follow-up.
- FAERS is a spontaneous reporting system: observed PRR/ROR values indicate disproportionality in reporting, not absolute incidence. Results should be validated against EHR or claims data.

For raw JSON outputs and exact numeric arrays, see `reports/eda_results.json` and `reports/mining_results.json`.
