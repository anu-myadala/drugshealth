"""
scripts/03_data_mining.py
GLP-1 FAERS Study — Data Mining Engine

Technique 1: Apriori Association Rules
  - Market basket: drugs co-reported with GLP-1s
  - Goal: discover drug combos associated with hospitalization

Technique 2: K-Means Clustering
  - Cluster GLP-1 patients by age, weight, polypharmacy, time-to-onset
  - Goal: identify high-risk patient phenotypes

Technique 3: Logistic Regression (Baseline classifier)
  - Interpretable baseline — coefficient analysis

Technique 4: Random Forest (Primary classifier)
  - Target: severity_flag (1=serious: HO/LT/DE)
  - Focus on RECALL (minimize false negatives in medical risk)
"""

import warnings
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import joblib
from pathlib import Path
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import (train_test_split, cross_val_score,
                                      StratifiedKFold, GridSearchCV)
from sklearn.metrics import (classification_report, confusion_matrix,
                              ConfusionMatrixDisplay, roc_auc_score, roc_curve,
                              f1_score, recall_score, precision_score,
                              silhouette_score, davies_bouldin_score)
from sklearn.decomposition import PCA
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.cluster import DBSCAN
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", font_scale=1.0)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR  = PROJECT_ROOT / "data" / "processed"
FIG_DIR   = PROJECT_ROOT / "reports" / "figures"
MODEL_DIR = PROJECT_ROOT / "models"
FIG_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

C1 = "#1B6CA8"; C2 = "#CC4E2A"; C3 = "#2E7D32"; C4 = "#7B2D8B"


# ── Load & prepare data ────────────────────────────────────────────────────────
def load_and_prepare() -> tuple[pd.DataFrame, pd.DataFrame]:
    fact = pd.read_csv(DATA_DIR / "fact_adverse_event.csv", dtype={"primaryid": str})
    drug = pd.read_csv(DATA_DIR / "drug_records.csv",       dtype={"primaryid": str})
    return fact, drug


def encode_features(df: pd.DataFrame) -> pd.DataFrame:
    """Feature engineering for classification and clustering."""
    fe = df.copy()
    fe["age_bucket"]  = pd.cut(fe["age_yr"],
                                bins=[0, 40, 55, 65, 75, 200],
                                labels=["<40","40-54","55-64","65-74","75+"])
    fe["sex_bin"]     = (fe["sex_clean"] == "Female").astype(int)
    fe["is_us"]       = (fe["reporter_country"] == "US").astype(int)
    # Do not impute yet - handle outliers formally first (IQR method)
    fe["age_yr"]      = fe["age_yr"].fillna(fe["age_yr"].median())
    # leave wt_kg NaN for now if missing; outlier detection will set outliers to NaN
    fe["polypharmacy_count"] = fe["polypharmacy_count"].fillna(1).clip(1, 30)
    fe["time_to_onset_days"] = fe["time_to_onset_days"].fillna(
        fe["time_to_onset_days"].median()).clip(0, 3*365)
    fe["log_poly"]    = np.log1p(fe["polypharmacy_count"])
    fe["age_wt_interaction"] = fe["age_yr"] * fe["wt_kg"] / 1000  # scale
    return fe


def detect_and_handle_outliers(fe: pd.DataFrame, save_prefix: Path | str | None = None) -> pd.DataFrame:
    """Detect outliers using IQR for wt_kg and replace them with NaN; returns DataFrame.
    Saves a small histogram and boxplot to illustrate the IQR and outlier thresholds.
    """
    df = fe.copy()
    if "wt_kg" not in df.columns:
        return df
    series = df["wt_kg"].dropna()
    if series.empty:
        return df
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outlier_mask = (df["wt_kg"] < lower) | (df["wt_kg"] > upper)
    n_outliers = int(outlier_mask.sum())
    print(f"  Outlier detection (IQR) for wt_kg: Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}")
    print(f"    Thresholds: lower={lower:.2f}, upper={upper:.2f} -> {n_outliers} outliers marked as NaN")
    df.loc[outlier_mask, "wt_kg"] = np.nan

    # Save a diagnostic plot
    try:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].boxplot(series.dropna(), vert=False)
        axes[0].set_title("Weight Boxplot (pre-clean)")
        axes[1].hist(series.dropna(), bins=60, color=C2)
        axes[1].axvline(lower, color="red", ls="--")
        axes[1].axvline(upper, color="red", ls="--")
        axes[1].set_title("Weight Distribution (pre-clean)")
        plt.tight_layout()
        if save_prefix:
            plt.savefig(FIG_DIR / f"{save_prefix}_wt_outlier_diag.png", dpi=150, bbox_inches="tight")
        plt.close()
    except Exception:
        pass

    return df


# ─────────────────────────────────────────────────────────────────────────────
# TECHNIQUE 1: APRIORI ASSOCIATION RULES
# ─────────────────────────────────────────────────────────────────────────────
def run_apriori(fact: pd.DataFrame, drug: pd.DataFrame) -> pd.DataFrame:
    """
    Market basket: each patient = one transaction
    Items: drug names (top-50 most reported) + hospitalization flag

    Goal: find {DrugA, GLP-1} → {Hospitalization} rules with high lift
    """
    print("\n── Apriori Association Rules ──────────────────────────────")

    # Keep GLP-1 cohort only
    glp1_pids = set(fact.loc[fact["cohort"] == "glp1", "primaryid"])
    drug_glp1 = drug[drug["primaryid"].isin(glp1_pids)].copy()

    # Get top-N concurrent drugs
    drug_glp1["prod_ai_clean"] = (drug_glp1["prod_ai"].fillna("")
                                  .str.upper().str.strip()
                                  .str[:40])
    # Exclude the GLP-1 drugs themselves from basket
    glp1_names = ["SEMAGLUTIDE","LIRAGLUTIDE","DULAGLUTIDE","TIRZEPATIDE","EXENATIDE"]
    glp1_pat = "|".join(glp1_names)
    drug_glp1 = drug_glp1[~drug_glp1["prod_ai_clean"].str.contains(glp1_pat, na=False)]

    top_drugs = drug_glp1["prod_ai_clean"].value_counts().head(40).index.tolist()
    drug_glp1 = drug_glp1[drug_glp1["prod_ai_clean"].isin(top_drugs)]

    # Build transactions
    basket = drug_glp1.groupby("primaryid")["prod_ai_clean"].apply(list).reset_index()
    basket = basket.merge(
        fact[["primaryid", "severity_flag", "gi_severe_flag"]].drop_duplicates("primaryid"),
        on="primaryid", how="left"
    )
    # Add outcome items
    basket["items"] = basket.apply(
        lambda r: r["prod_ai_clean"] +
                  (["HOSPITALIZED"] if r["severity_flag"] == 1 else []) +
                  (["GI_SEVERE_EVENT"] if r["gi_severe_flag"] == 1 else []),
        axis=1
    )

    te = TransactionEncoder()
    te_array = te.fit_transform(basket["items"])
    te_df    = pd.DataFrame(np.asarray(te_array), columns=te.columns_)

    freq = apriori(te_df, min_support=0.02, use_colnames=True)
    print(f"  Frequent itemsets: {len(freq)}")
    rules = association_rules(freq, metric="confidence", min_threshold=0.4)
    rules = rules[rules["lift"] >= 1.3].sort_values("lift", ascending=False)
    print(f"  Rules (conf≥0.40, lift≥1.3): {len(rules)}")

    # Pretty-print top 15
    rules["antecedents_str"] = rules["antecedents"].apply(lambda x: " + ".join(sorted(x)))
    rules["consequents_str"] = rules["consequents"].apply(lambda x: " + ".join(sorted(x)))
    print("\n  Top 15 Rules by Lift:")
    for _, r in rules.head(15).iterrows():
        print(f"    {{{r['antecedents_str']}}} → {{{r['consequents_str']}}}  "
              f"sup={r['support']:.3f} conf={r['confidence']:.3f} lift={r['lift']:.2f}")

    rules.to_csv(DATA_DIR / "apriori_rules.csv", index=False)

    # Visualize top rules
    top = rules.head(15)
    fig, ax = plt.subplots(figsize=(11, 6))
    bars = ax.barh(range(len(top)), top["lift"].to_numpy()[::-1], color=C1, alpha=0.85)
    ax.set_yticks(range(len(top)))
    labels = [f"{r['antecedents_str']} → {r['consequents_str']}"[:70]
              for _, r in top.iterrows()]
    ax.set_yticklabels(labels[::-1], fontsize=8)
    ax.axvline(1.0, color="gray", lw=1, ls="--")
    ax.axvline(2.0, color="red",  lw=1, ls="--", label="Lift=2 (strong)")
    for b, v in zip(bars, top["lift"].values[::-1]):
        ax.text(b.get_width() + 0.03, b.get_y() + b.get_height()/2,
                f"{v:.2f}", va="center", fontsize=8)
    ax.set_xlabel("Lift", fontsize=11)
    ax.set_title(f"Top 15 Apriori Association Rules — GLP-1 Concurrent Medications\n"
                 f"min_support=0.02, min_confidence=0.40 · {len(rules)} rules found", fontsize=11)
    ax.legend(fontsize=10)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "apriori_rules.png", dpi=160, bbox_inches="tight")
    plt.close()

    return rules


# ─────────────────────────────────────────────────────────────────────────────
# TECHNIQUE 2: K-MEANS CLUSTERING
# ─────────────────────────────────────────────────────────────────────────────
def run_kmeans(fact: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Cluster GLP-1 patients to find high-risk phenotypes.
    Features: age, weight, polypharmacy count, concurrent opioid, time-to-onset
    """
    print("\n── K-Means Clustering ──────────────────────────────────────")

    glp1 = fact[fact["cohort"] == "glp1"].copy()
    glp1 = encode_features(glp1)
    glp1 = detect_and_handle_outliers(glp1, save_prefix="kmeans")

    cluster_feats = ["age_yr", "wt_kg", "polypharmacy_count",
                     "concurrent_opioid", "time_to_onset_days", "sex_bin"]
    X = glp1[cluster_feats].fillna(0)

    sc = StandardScaler()
    Xs = sc.fit_transform(X)
    # Elbow + silhouette with robustness for small / problematic data
    n_samples = Xs.shape[0]
    print(f"  GLP-1 cohort samples for clustering: {n_samples}")
    if n_samples < 4:
        # Not enough samples to run reliable KMeans+silhouette analysis
        print("  Not enough samples for K-Means clustering (need >=4). Skipping clustering.")
        glp1["cluster"] = 0
        glp1["cluster_name"] = "Insufficient data"
        return glp1, {"silhouette": np.nan, "davies_bouldin": np.nan,
                      "best_k": 1, "cluster_names": {0: "Insufficient data"},
                      "profile": {}}

    inertias, silhouettes = [], []
    K_RANGE = range(2, 9)
    # Use a small sample for evaluation; skip silhouette to avoid heavy pairwise computations
    SAMPLE_K = 2000
    if n_samples > SAMPLE_K:
        sample_idx = np.random.RandomState(42).choice(n_samples, size=SAMPLE_K, replace=False)
        Xs_eval = Xs[sample_idx]
    else:
        Xs_eval = Xs
    for k in K_RANGE:
        if k >= n_samples:
            # silhouette_score requires at least 2 clusters and fewer clusters than samples
            print(f"  Skipping k={k} because k >= n_samples ({n_samples})")
            continue
        try:
            km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=10, batch_size=2048)
            labels = km.fit_predict(Xs_eval)
            inertias.append(km.inertia_)
            silhouettes.append(np.nan)
        except Exception as e:
            print(f"  KMeans failed for k={k}: {e}")
            continue

    # Choose best_k using a fixed default to avoid expensive silhouette calculations
    best_k = 5 if n_samples >= 5 else max(2, n_samples - 1)
    print(f"  Using default k={best_k} (silhouette skipped for performance)")

    try:
        km_final = MiniBatchKMeans(n_clusters=best_k, random_state=42, n_init=10, batch_size=2048)
        glp1["cluster"] = km_final.fit_predict(Xs)
    except Exception as e:
        print(f"  Final KMeans fit failed for k={best_k}: {e}")
        glp1["cluster"] = 0
        glp1["cluster_name"] = "Clustering failed"
        return glp1, {"silhouette": np.nan, "davies_bouldin": np.nan,
                      "best_k": best_k, "cluster_names": {}, "profile": {}}

    labels_eval = km_final.predict(Xs_eval)
    sil  = float('nan')
    db   = davies_bouldin_score(Xs_eval, labels_eval)
    print(f"  Silhouette=NA  Davies-Bouldin={db:.4f}")

    # Profile clusters
    profile = glp1.groupby("cluster").agg(
        n=("primaryid","count"),
        age_mean=("age_yr","mean"),
        wt_mean=("wt_kg","mean"),
        poly_mean=("polypharmacy_count","mean"),
        opioid_pct=("concurrent_opioid","mean"),
        gi_severe_pct=("gi_severe_flag","mean"),
        severity_pct=("severity_flag","mean"),
        pct_female=("sex_bin","mean"),
        tto_mean=("time_to_onset_days","mean"),
    ).round(3)
    print("\n  Cluster Profiles:")
    print(profile.to_string())

    # Auto-label by severity
    severity_order = profile["severity_pct"].rank().astype(int)
    severity_dict = severity_order.to_dict()
    name_map_keys = sorted(severity_dict.keys(), key=lambda k: severity_dict.get(k, 0))
    tier_names = ["Low-Risk Stable", "Moderate-Risk Active", "High-Risk Vulnerable",
                  "Very High-Risk Complex", "Critical Risk"]
    cluster_names = {k: tier_names[min(i, len(tier_names)-1)] for i, k in enumerate(name_map_keys)}
    glp1["cluster_name"] = glp1["cluster"].map(cluster_names)
    print("\n  Cluster labels:", cluster_names)

    # Save cluster assignments
    glp1.to_csv(DATA_DIR / "glp1_clustered.csv", index=False)
    joblib.dump({"model": km_final, "scaler": sc, "features": cluster_feats,
                 "names": cluster_names, "profile": profile},
                MODEL_DIR / "kmeans_pipeline.pkl")

    # Figures
    # Elbow
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].plot(list(K_RANGE), inertias, "o-", color=C1, lw=2)
    axes[0].set_xlabel("k"); axes[0].set_ylabel("Inertia")
    axes[0].set_title("Elbow Method — K-Means on GLP-1 Patients")
    axes[1].plot(list(K_RANGE), silhouettes, "o-", color=C3, lw=2)
    axes[1].set_xlabel("k"); axes[1].set_ylabel("Silhouette Score")
    axes[1].set_title("Silhouette Scores by k")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "kmeans_elbow.png", dpi=160, bbox_inches="tight"); plt.close()

    # Cluster scatter in PCA-2D
    pca2 = PCA(n_components=2, random_state=42)
    coords = pca2.fit_transform(Xs)
    CMAP = [C1, C2, C3, C4, "#FF9F1C"]
    fig, ax = plt.subplots(figsize=(8, 6))
    for ci in sorted(glp1["cluster"].unique()):
        mask = glp1["cluster"] == ci
        name = cluster_names.get(ci, f"Cluster {ci}")
        ax.scatter(coords[mask, 0], coords[mask, 1], label=name,
                   s=6, alpha=0.5, color=CMAP[ci % len(CMAP)], rasterized=True)
    ax.set_xlabel(f"PC1 ({pca2.explained_variance_ratio_[0]*100:.1f}% var)", fontsize=11)
    ax.set_ylabel(f"PC2 ({pca2.explained_variance_ratio_[1]*100:.1f}% var)", fontsize=11)
    ax.set_title(f"K-Means Patient Phenotype Clusters (k={best_k})\n"
                 f"Silhouette={sil:.3f}  Davies-Bouldin={db:.3f}", fontsize=11)
    ax.legend(fontsize=8, markerscale=4, loc="upper right")
    plt.tight_layout()
    plt.savefig(FIG_DIR / "kmeans_clusters.png", dpi=160, bbox_inches="tight"); plt.close()

    # Cluster heatmap
    profile_z = (profile[["age_mean","wt_mean","poly_mean","opioid_pct",
                           "gi_severe_pct","severity_pct","pct_female"]]
                 - profile[["age_mean","wt_mean","poly_mean","opioid_pct",
                             "gi_severe_pct","severity_pct","pct_female"]].mean()) \
                 / profile[["age_mean","wt_mean","poly_mean","opioid_pct",
                             "gi_severe_pct","severity_pct","pct_female"]].std()
    profile_z.index = pd.Index([cluster_names.get(i, f"C{i}") for i in profile_z.index])
    profile_z.columns = ["Age","Weight","Polypharmacy","Opioid%","GI%","Severe%","Female%"]
    fig, ax = plt.subplots(figsize=(9, 4))
    sns.heatmap(profile_z, annot=True, fmt=".2f", cmap="RdBu_r", center=0,
                linewidths=0.5, ax=ax, annot_kws={"size": 10},
                cbar_kws={"label": "Z-score"})
    ax.set_title(f"Cluster Profile Heatmap — GLP-1 Patient Phenotypes\n"
                 f"K-Means k={best_k}, Silhouette={sil:.3f}", fontsize=11)
    ax.set_yticklabels(ax.get_yticklabels(), rotation=0, fontsize=10)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "kmeans_profile_heatmap.png", dpi=160, bbox_inches="tight"); plt.close()

    return glp1, {"silhouette": sil, "davies_bouldin": db,
                  "best_k": best_k, "cluster_names": cluster_names,
                  "profile": profile.to_dict()}


# ─────────────────────────────────────────────────────────────────────────────
# TECHNIQUES 3 & 4: LOGISTIC REGRESSION + RANDOM FOREST
# ─────────────────────────────────────────────────────────────────────────────
def run_classification(fact: pd.DataFrame) -> dict:
    """
    Target: severity_flag (1 = Hospitalization/Life-Threatening/Death)
    Key metric: RECALL (minimize false negatives — missing a high-risk patient is dangerous)
    """
    print("\n── Classification: LR + Random Forest ─────────────────────")

    glp1 = fact[fact["cohort"] == "glp1"].copy()
    glp1 = encode_features(glp1)
    glp1 = detect_and_handle_outliers(glp1, save_prefix="classification")

    # Encode drug name
    glp1["glp1_drug_enc"] = LabelEncoder().fit_transform(glp1["glp1_drug"].fillna("UNKNOWN"))

    feat_cols = ["age_yr", "wt_kg", "polypharmacy_count", "concurrent_opioid",
                 "sex_bin", "is_us", "gi_severe_flag", "glp1_drug_enc",
                 "time_to_onset_days", "log_poly", "age_wt_interaction"]
    target = "severity_flag"

    data_ml = glp1[feat_cols + [target]].dropna(subset=feat_cols[:6])
    X = data_ml[feat_cols]
    y = data_ml[target].astype(int)

    print(f"  Dataset: {len(X):,} samples | Class balance: {y.mean():.3f} (positive rate)")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    sc = StandardScaler()
    X_train_s = sc.fit_transform(X_train)
    X_test_s  = sc.transform(X_test)

    # ── Logistic Regression ────────────────────────────────────────────────
    lr = LogisticRegression(class_weight="balanced", max_iter=500, random_state=42, C=1.0)
    lr.fit(X_train_s, y_train)
    lr_pred  = lr.predict(X_test_s)
    lr_proba = lr.predict_proba(X_test_s)[:, 1]
    lr_auc   = roc_auc_score(y_test, lr_proba)
    lr_f1    = f1_score(y_test, lr_pred)
    lr_rec   = recall_score(y_test, lr_pred)
    lr_prec  = precision_score(y_test, lr_pred)
    print(f"\n  Logistic Regression: AUC={lr_auc:.4f} F1={lr_f1:.4f} Recall={lr_rec:.4f}")
    print(classification_report(y_test, lr_pred, target_names=["Non-Serious","Serious"]))

    # ── Random Forest ──────────────────────────────────────────────────────
    rf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                 random_state=42, n_jobs=-1, max_depth=12,
                                 min_samples_leaf=5)
    rf.fit(X_train, y_train)
    rf_pred  = rf.predict(X_test)
    rf_proba = rf.predict_proba(X_test)[:, 1]
    rf_auc   = roc_auc_score(y_test, rf_proba)
    rf_f1    = f1_score(y_test, rf_pred)
    rf_rec   = recall_score(y_test, rf_pred)
    rf_prec  = precision_score(y_test, rf_pred)

    # 5-fold CV on training set only (prevents test-set leakage)
    # Skip cross-validation to keep runtime manageable on large datasets
    cv_rf = np.array([np.nan])
    print(f"\n  Random Forest: AUC={rf_auc:.4f} F1={rf_f1:.4f} Recall={rf_rec:.4f}")
    print("  CV AUC: skipped (runtime optimization)")
    print(classification_report(y_test, rf_pred, target_names=["Non-Serious","Serious"]))

    # ── Figures ────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Confusion matrix (RF)
    cm_rf = confusion_matrix(y_test, rf_pred)
    ConfusionMatrixDisplay(cm_rf, display_labels=["Non-Serious","Serious"]).plot(
        ax=axes[0], colorbar=False, cmap="Blues")
    axes[0].set_title(f"RF Confusion Matrix\nF1={rf_f1:.3f}  Recall={rf_rec:.3f}  AUC={rf_auc:.3f}",
                      fontsize=11)
    for t in axes[0].texts: t.set_fontsize(14)

    # ROC curves
    for proba, label, color in [
        (lr_proba, f"Logistic Regression (AUC={lr_auc:.3f})", C2),
        (rf_proba, f"Random Forest (AUC={rf_auc:.3f})",       C1),
    ]:
        fpr, tpr, _ = roc_curve(y_test, proba)
        axes[1].plot(fpr, tpr, lw=2, label=label, color=color)
    axes[1].plot([0,1],[0,1],"k--",lw=0.8,alpha=0.5)
    axes[1].fill_between(*roc_curve(y_test, rf_proba)[:2], alpha=0.10, color=C1)
    axes[1].set_xlabel("FPR",fontsize=11); axes[1].set_ylabel("TPR",fontsize=11)
    axes[1].set_title("ROC Curves: LR vs Random Forest\n(GLP-1 Severity Prediction)", fontsize=11)
    axes[1].legend(fontsize=9)

    # Feature importance (RF)
    fi = pd.Series(rf.feature_importances_, index=feat_cols).sort_values().tail(10)
    fi.plot(kind="barh", ax=axes[2], color=C3, alpha=0.85)
    axes[2].set_title("RF Feature Importances\n(Top 10)", fontsize=11)
    axes[2].set_xlabel("Importance (Gini)", fontsize=11)
    axes[2].set_yticklabels([f.replace("_"," ").title() for f in fi.index], fontsize=10)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "classification_results.png", dpi=160, bbox_inches="tight")
    plt.close()

    # LR Coefficient plot
    coef_df = pd.DataFrame({"feature": feat_cols, "coef": lr.coef_[0]})
    coef_df["odds_ratio"] = np.exp(coef_df["coef"])
    coef_df = coef_df.sort_values("coef")
    fig, ax = plt.subplots(figsize=(8, 5.5))
    colors = [C2 if c > 0 else C3 for c in coef_df["coef"]]
    ax.barh(coef_df["feature"], coef_df["coef"], color=colors, alpha=0.85)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_xlabel("Coefficient (Log-Odds)", fontsize=11)
    ax.set_title("Logistic Regression Coefficients\n(Positive = increases hospitalization risk)",
                 fontsize=11)
    ax.set_yticklabels([f.replace("_"," ").title() for f in coef_df["feature"]], fontsize=10)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "lr_coefficients.png", dpi=160, bbox_inches="tight")
    plt.close()

    # Save models
    joblib.dump(rf, MODEL_DIR / "random_forest.pkl")
    joblib.dump(lr, MODEL_DIR / "logistic_regression.pkl")
    joblib.dump(sc, MODEL_DIR / "feature_scaler.pkl")
    json.dump(feat_cols, open(MODEL_DIR / "feature_columns.json", "w"), indent=2)

    return {
        "logistic_regression": {
            "auc": float(lr_auc), "f1": float(lr_f1),
            "recall": float(lr_rec), "precision": float(lr_prec),
            "confusion_matrix": confusion_matrix(y_test, lr_pred).tolist(),
        },
        "random_forest": {
            "auc": float(rf_auc), "f1": float(rf_f1),
            "recall": float(rf_rec), "precision": float(rf_prec),
            "cv_auc_mean": float(cv_rf.mean()), "cv_auc_std": float(cv_rf.std()),
            "confusion_matrix": cm_rf.tolist(),
        },
        "feature_columns": feat_cols,
        "n_train": len(X_train),
        "n_test":  len(X_test),
        "class_balance": float(y.mean()),
    }


def run_extended_mining(fact: pd.DataFrame, save_prefix: str = "extended") -> dict:
    """Run PCA, DBSCAN, Decision Tree, GaussianNB, and aggregate results and figures.
    Saves outputs under reports/figures and reports/<save_prefix>_mining_results.json.
    """
    print("\n── Extended Mining: PCA, DBSCAN, DecisionTree, GaussianNB ─────────────────")
    out = {}
    # Use GLP-1 cohort (severity prediction) for supervised models
    df_glp1 = fact[fact["cohort"] == "glp1"].copy()
    df_glp1 = encode_features(df_glp1)
    # Apply outlier detection for weight
    df_glp1 = detect_and_handle_outliers(df_glp1, save_prefix=save_prefix)

    # Define features for modeling (same as classification)
    feat_cols = ["age_yr", "wt_kg", "polypharmacy_count", "concurrent_opioid",
                 "sex_bin", "is_us", "gi_severe_flag", "time_to_onset_days",
                 "log_poly", "age_wt_interaction"]
    # Drop rows with missing essential numeric features (except wt_kg which may be NaN after outlier removal)
    data_ml = df_glp1[feat_cols + ["severity_flag"]].copy()

    # Numeric matrix for PCA (impute medians)
    Xnum = data_ml[feat_cols].select_dtypes(include=[np.number]).fillna(data_ml[feat_cols].median())
    if Xnum.shape[1] < 2:
        print("  Not enough numeric features for PCA/DBSCAN. Skipping extended mining.")
        return out

    # For memory safety, operate PCA/DBSCAN/classifiers on a random sample if dataset is large
    SAMPLE_SIZE = 50000
    if Xnum.shape[0] > SAMPLE_SIZE:
        use_sample = True
        sample_idx = np.random.RandomState(42).choice(Xnum.index, size=SAMPLE_SIZE, replace=False)
        Xnum_sample = Xnum.loc[sample_idx]
    else:
        use_sample = False
        sample_idx = Xnum.index
        Xnum_sample = Xnum

    # PCA (keep up to 10 components)
    n_comp = min(10, Xnum.shape[1])
    pca = PCA(n_components=n_comp, random_state=42)
    Xp = pca.fit_transform(Xnum_sample)
    evr = pca.explained_variance_ratio_
    out["pca_explained_variance_ratio"] = evr.tolist()
    out["pca_cumulative_variance"] = np.cumsum(evr).tolist()
    # scree plot
    try:
        plt.figure(figsize=(6, 4))
        plt.bar(range(1, len(evr)+1), evr*100, color=C1)
        plt.plot(range(1, len(evr)+1), np.cumsum(evr)*100, marker='o', color=C3)
        plt.xlabel('Principal Component')
        plt.ylabel('Explained Variance (%)')
        plt.title('PCA Scree Plot')
        plt.tight_layout()
        plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_pca_scree.png", dpi=150, bbox_inches='tight')
        plt.close()
    except Exception:
        pass

    # DBSCAN on first 3 PCs
    try:
        # DBSCAN can be costly; run on the sampled PCA coordinates and with single-thread
        # Increase min_samples to reduce micro-clusters and enforce larger density groups
        db = DBSCAN(eps=1.0, min_samples=100, n_jobs=1)
        labels = db.fit_predict(Xp[:, :3])
        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
        out['dbscan_n_clusters'] = int(n_clusters)
        # save counts
        pd.Series(labels).value_counts().to_csv(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_dbscan_cluster_counts.csv")
        # PC scatter
        plt.figure(figsize=(6,5))
        unique = np.unique(labels)
        cmap = plt.cm.get_cmap('tab20', len(unique))
        for i, lab in enumerate(unique):
            mask = labels == lab
            col = 'k' if lab == -1 else cmap(i)
            plt.scatter(Xp[mask,0], Xp[mask,1], s=6, c=[col], label=str(lab) if lab!=-1 else 'outlier')
        plt.xlabel('PC1'); plt.ylabel('PC2'); plt.title('DBSCAN clusters (PC1 vs PC2)')
        plt.legend(markerscale=3, fontsize=6)
        plt.tight_layout()
        plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_dbscan_pc12.png", dpi=150, bbox_inches='tight')
        plt.close()
    except Exception as e:
        print('  DBSCAN failed:', e)

    # Prepare labels for supervised models: predict severity_flag within GLP-1 cohort
    if 'severity_flag' not in df_glp1.columns:
        print('  severity_flag column missing; skipping supervised extended models')
        return out
    # Use the same sampling strategy for supervised training to limit memory
    train_idx = sample_idx if use_sample else Xnum.index
    X = Xnum.loc[train_idx].fillna(0)
    y = df_glp1.loc[train_idx, 'severity_flag'].astype(int)
    # Ensure both classes are present
    if y.nunique() < 2:
        print('  Only one class present in target after filtering; skipping supervised extended models')
        return out
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    # Decision Tree
    dt = DecisionTreeClassifier(max_depth=6, random_state=42, class_weight="balanced")
    dt.fit(X_train, y_train)
    y_pred_dt = dt.predict(X_test)
    proba_dt = dt.predict_proba(X_test) if hasattr(dt, 'predict_proba') else None
    if proba_dt is None:
        y_prob_dt = y_pred_dt
    else:
        pa = np.asarray(proba_dt)
        if pa.ndim == 1:
            y_prob_dt = pa
        elif pa.shape[1] == 1:
            y_prob_dt = pa[:, 0]
        else:
            y_prob_dt = pa[:, -1]
    dt_metrics = {
        'model': 'DecisionTree',
        'accuracy': accuracy_score(y_test, y_pred_dt),
        'precision': precision_score(y_test, y_pred_dt),
        'recall': recall_score(y_test, y_pred_dt),
        'f1': f1_score(y_test, y_pred_dt),
        'roc_auc': roc_auc_score(y_test, y_prob_dt)
    }
    out['decision_tree'] = dt_metrics
    ConfusionMatrixDisplay.from_predictions(y_test, y_pred_dt, cmap='Blues')
    plt.title('Decision Tree Confusion Matrix')
    plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_confusion_decision_tree.png", dpi=150, bbox_inches='tight')
    plt.close()

    # Gaussian Naive Bayes
    gnb = GaussianNB()
    gnb.fit(X_train, y_train)
    y_pred_nb = gnb.predict(X_test)
    pa_nb = np.asarray(gnb.predict_proba(X_test))
    if pa_nb.ndim == 1:
        y_prob_nb = pa_nb
    elif pa_nb.shape[1] == 1:
        y_prob_nb = pa_nb[:, 0]
    else:
        y_prob_nb = pa_nb[:, -1]
    nb_metrics = {
        'model': 'GaussianNB',
        'accuracy': accuracy_score(y_test, y_pred_nb),
        'precision': precision_score(y_test, y_pred_nb),
        'recall': recall_score(y_test, y_pred_nb),
        'f1': f1_score(y_test, y_pred_nb),
        'roc_auc': roc_auc_score(y_test, y_prob_nb)
    }
    out['gaussian_nb'] = nb_metrics
    ConfusionMatrixDisplay.from_predictions(y_test, y_pred_nb, cmap='Greens')
    plt.title('GaussianNB Confusion Matrix')
    plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_confusion_gaussiannb.png", dpi=150, bbox_inches='tight')
    plt.close()

    # RandomForest baseline for comparison
    try:
        # Use smaller RF for comparison to limit memory/CPU
        rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=1, class_weight="balanced")
        rf.fit(X_train, y_train)
        y_pred_rf = rf.predict(X_test)
        pa_rf = np.asarray(rf.predict_proba(X_test))
        if pa_rf.ndim == 1:
            y_prob_rf = pa_rf
        elif pa_rf.shape[1] == 1:
            y_prob_rf = pa_rf[:, 0]
        else:
            y_prob_rf = pa_rf[:, -1]
        rf_metrics = {
            'model': 'RandomForest',
            'accuracy': accuracy_score(y_test, y_pred_rf),
            'precision': precision_score(y_test, y_pred_rf),
            'recall': recall_score(y_test, y_pred_rf),
            'f1': f1_score(y_test, y_pred_rf),
            'roc_auc': roc_auc_score(y_test, y_prob_rf)
        }
        out['random_forest'] = rf_metrics

        # Feature importance plot (top 15)
        try:
            fi = pd.Series(rf.feature_importances_, index=feat_cols).sort_values()
            fi.tail(15).to_csv(PROJECT_ROOT / 'reports' / f"{save_prefix}_rf_feature_importances.csv")
            fi = fi.tail(15)
            plt.figure(figsize=(6, 5))
            fi.plot(kind='barh', color=C3, alpha=0.85)
            plt.xlabel('Importance (Gini)')
            plt.title('Random Forest Feature Importances (Top 15)')
            plt.tight_layout()
            plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_rf_feature_importances.png", dpi=150, bbox_inches='tight')
            plt.close()
        except Exception:
            pass
    except Exception:
        pass

    # Save model comparison table and ROC-AUC bar
    metrics_df = pd.DataFrame([v for v in out.values() if isinstance(v, dict)])
    if not metrics_df.empty:
        metrics_df = metrics_df.set_index('model')
        metrics_df.to_csv(PROJECT_ROOT / 'reports' / f"{save_prefix}_model_comparison.csv")
        try:
            plt.figure(figsize=(6,3))
            metrics_df['roc_auc'].plot(kind='bar', color=[C1, C2, C3][:len(metrics_df)])
            plt.ylim(0,1)
            plt.title('Model ROC-AUC Comparison')
            plt.tight_layout()
            plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_roc_auc_comparison.png", dpi=150, bbox_inches='tight')
            plt.close()
        except Exception:
            pass
        # Save a simple table image for reporting
        try:
            tbl = metrics_df.round(3)
            fig, ax = plt.subplots(figsize=(7, 2 + 0.4 * len(tbl)))
            ax.axis('off')
            table = ax.table(cellText=tbl.values.tolist(),
                             colLabels=list(tbl.columns),
                             rowLabels=list(tbl.index),
                             loc='center', cellLoc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1, 1.2)
            plt.title('Model Performance Comparison', pad=12)
            plt.tight_layout()
            plt.savefig(PROJECT_ROOT / 'reports' / 'figures' / f"{save_prefix}_model_comparison_table.png", dpi=150, bbox_inches='tight')
            plt.close()
        except Exception:
            pass

    # Save extended metrics JSON
    try:
        with open(PROJECT_ROOT / 'reports' / f"{save_prefix}_mining_results.json", 'w') as fh:
            json.dump(out, fh, indent=2)
    except Exception:
        pass

    return out


def run_data_mining() -> dict:
    fact, drug = load_and_prepare()
    apriori_rules   = run_apriori(fact, drug)
    glp1_clustered, cluster_metrics = run_kmeans(fact)
    clf_metrics      = run_classification(fact)

    # Extended mining: PCA, DBSCAN, DecisionTree, GaussianNB and model comparison
    try:
        from time import time
        t0 = time()
        ext_metrics = run_extended_mining(fact, save_prefix="extended")
        print(f"  Extended mining finished in {time()-t0:.1f}s")
    except Exception as e:
        print("Extended mining failed:", e)
        ext_metrics = {}

    all_metrics = {
        "clustering": cluster_metrics,
        "classification": clf_metrics,
        "extended": ext_metrics,
    }
    with open(PROJECT_ROOT / "reports" / "mining_results.json", "w") as fh:
        json.dump(all_metrics, fh, indent=2, default=str)
    print("\nData mining complete. All models and results saved.")
    return all_metrics


if __name__ == "__main__":
    run_data_mining()
