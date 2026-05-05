Results — Latest Run (FAERS 2023Q1 → 2026Q1)
Overview
This file captures the key numeric results and figures from the latest end-to-end pipeline run (ETL → EDA → Data Mining) using FAERS quarterly ASCII files 2023Q1–2026Q1.

Dataset
Total unique cases (after global deduplication): 367,883

GLP-1 cohort (identified by active ingredient): 206,974

Control cohort (metformin-class controls): 160,909

Total severe GI events (across both cohorts): 7,303

Total severity_flag=1 events (hospitalization / life-threatening / death): 98,131

Descriptive Statistics (Cohort-Level)
GLP-1 Cohort (n=206,974):

Age: Mean = 56.23 years (Median = 56.0, SD = 11.63)

Weight: Mean = 91.8 kg (Median = 86.6)

Gender: Female: 60.7%

Severe GI event rate: 2.25%

Overall Severity rate (severity_flag=1): 11.2%

Concurrent opioid reporting: 1.3%

Polypharmacy: Median = 1.0

Control Cohort (n=160,909):

Age: Mean = 65.89 years (Median = 68.0, SD = 12.27)

Weight: Mean = 83.29 kg (Median = 85.0)

Gender: Female: 44.6%

Severe GI event rate: 1.65%

Overall Severity rate (severity_flag=1): 46.6%

Concurrent opioid reporting: 10.3%

Polypharmacy: Median = 6.0

Statistical Testing (Key Results)
Chi-Square Test (Cohort × GI Severe):

Contingency: Control (No=158,257; Yes=2,652) | GLP-1 (No=202,323; Yes=4,651)

Result: χ² = 166.634, df = 1, p = 4.02e-38 (Reject H₀)

Effect Size: Cramér's V = 0.0213 (Small effect)

Disproportionality Analysis:

Overall PRR (GLP-1 vs Control): 1.363 (95% CI: 1.301–1.429)

Overall ROR: 1.372 (95% CI: 1.307–1.439)

WHO-UMC Signal Criteria (PRR ≥ 2, χ² ≥ 4, n ≥ 3):

PRR ≥ 2: No

χ² ≥ 4: Yes

n ≥ 3: Yes

Conclusion: False (Overall cohort PRR < 2)

Per-Drug PRR (vs. Metformin Control):

Semaglutide: n=61,976 | GI events=2,621 | PRR = 2.566 (Signal detected)

Liraglutide: n=6,738 | GI events=235 | PRR = 2.116 (Signal detected)

Dulaglutide: n=23,579 | GI events=560 | PRR = 1.441

Tirzepatide: n=136,324 | GI events=2,269 | PRR = 1.010

Exenatide: n=2,990 | GI events=14 | PRR = 0.284

Mann–Whitney U Test (Weight difference within GLP-1 cohort):

Severe GI: Median weight = 95.0 kg (n=4,651)

Non-severe: Median weight = 86.6 kg (n=202,323)

Result: U = 526,204,080, p = 2.74e-52 (Statistically significant, effect size r = -0.118)

Data Mining & Unsupervised Learning
Clustering (K-Means & DBSCAN):

K-Means: k = 5, Davies-Bouldin = 0.6964

Cluster 0 (Moderate-Risk Active): n = 76,791

Cluster 1 (Low-Risk Stable): n = 115,606

Cluster 2 (Critical Risk): n = 2,718

Cluster 3 (High-Risk Vulnerable): n = 4,543

Cluster 4 (Very High-Risk Complex): n = 7,316

DBSCAN (PCA Sample, Tuned): 1 continuous clinical manifold identified.

(See reports/mining_results.json for full cluster profiling including age, weight, and polypharmacy means).

Apriori Association Rules:

Frequent itemsets: 68

Actionable Rules (conf ≥ 0.40 & lift ≥ 1.3): 6

Key Finding: GI_SEVERE_EVENT → HOSPITALIZED exhibits strong co-occurrence, alongside specific insulin pairs.

Classification & Predictive Modeling (Severity Prediction)
Dataset: 198,742 GLP-1 cohort samples (post-IQR outlier handling).

Class Balance: 9.90% (Highly imbalanced toward non-severe).

Feature Scaling & Reduction: PCA applied (PC1 = 23.84%, PC2 = 23.05% | Cumulative = 46.89%).

Model Performance Comparison:

Decision Tree (Balanced, max_depth=5):

AUC: 0.7879 | Recall: 0.6902 | Accuracy: 0.7911 | F1: 0.4253

Logistic Regression:

AUC: 0.8111 | Recall: 0.6307 | Accuracy: 0.8300 | F1: 0.4276

Gaussian Naive Bayes:

AUC: 0.7742 | Recall: 0.3491 | Accuracy: 0.8662 | F1: 0.3689

Random Forest (Ensemble Baseline):

AUC: 0.6993 | Recall: 0.3920 | Accuracy: 0.8562 | F1: 0.3791

Random Forest (Optimized for Surveillance - Custom Threshold 0.15):

AUC: 0.8438

Recall: 0.9639 (Primary metric optimized to prevent false negatives)

F1: 0.2230

Note: Adjusting the classification threshold from 0.5 to 0.15 successfully compensated for the extreme class imbalance, converting the ensemble into a highly sensitive triage tool.

Artifacts Generated
data/processed/fact_adverse_event.csv

data/processed/glp1_clustered.csv

reports/eda_results.json

reports/mining_results.json

reports/extended_mining_results.json

reports/extended_model_comparison.csv

reports/figures/extended_model_comparison_table.png

reports/figures/extended_rf_feature_importances.png

reports/figures/*.png (All EDA & model figures)

Figures and tables referenced in the results above are saved under reports/figures/.

Notes & Interpretation
The combined dataset shows a statistically significant association between GLP-1 use and severe GI event reporting, but the overall PRR for the pooled GLP-1 group is below the conservative WHO-UMC threshold (PRR<2). However, specific individual agents (Semaglutide and Liraglutide) exceed PRR ≥ 2 and merit targeted clinical follow-up.

FAERS is a spontaneous reporting system: observed PRR/ROR values indicate disproportionality in reporting, not absolute incidence. Results should be validated against EHR or claims data.

For raw JSON outputs and exact numeric arrays, see reports/eda_results.json and reports/mining_results.json.
