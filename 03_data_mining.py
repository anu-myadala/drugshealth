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
from sklearn.cluster import KMeans
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
def load_and_prepare() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
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
    fe["age_yr"]      = fe["age_yr"].fillna(fe["age_yr"].median())
    fe["wt_kg"]       = fe["wt_kg"].fillna(fe["wt_kg"].median())
    fe["polypharmacy_count"] = fe["polypharmacy_count"].fillna(1).clip(1, 30)
    fe["time_to_onset_days"] = fe["time_to_onset_days"].fillna(
        fe["time_to_onset_days"].median()).clip(0, 3*365)
    fe["log_poly"]    = np.log1p(fe["polypharmacy_count"])
    fe["age_wt_interaction"] = fe["age_yr"] * fe["wt_kg"] / 1000  # scale
    return fe


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
    te_df    = pd.DataFrame(te_array, columns=te.columns_)

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
    bars = ax.barh(range(len(top)), top["lift"].values[::-1], color=C1, alpha=0.85)
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
def run_kmeans(fact: pd.DataFrame) -> pd.DataFrame:
    """
    Cluster GLP-1 patients to find high-risk phenotypes.
    Features: age, weight, polypharmacy count, concurrent opioid, time-to-onset
    """
    print("\n── K-Means Clustering ──────────────────────────────────────")

    glp1 = fact[fact["cohort"] == "glp1"].copy()
    glp1 = encode_features(glp1)

    cluster_feats = ["age_yr", "wt_kg", "polypharmacy_count",
                     "concurrent_opioid", "time_to_onset_days", "sex_bin"]
    X = glp1[cluster_feats].fillna(0)

    sc = StandardScaler()
    Xs = sc.fit_transform(X)

    # Elbow + silhouette
    inertias, silhouettes = [], []
    K_RANGE = range(2, 9)
    for k in K_RANGE:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(Xs)
        inertias.append(km.inertia_)
        silhouettes.append(silhouette_score(Xs, labels))

    best_k = silhouettes.index(max(silhouettes)) + 2
    print(f"  Optimal k by silhouette: {best_k} (score={max(silhouettes):.4f})")

    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    glp1["cluster"] = km_final.fit_predict(Xs)

    sil  = silhouette_score(Xs, glp1["cluster"])
    db   = davies_bouldin_score(Xs, glp1["cluster"])
    print(f"  Silhouette={sil:.4f}  Davies-Bouldin={db:.4f}")

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
    name_map_keys  = sorted(severity_order.to_dict(), key=severity_order.to_dict().get)
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
    profile_z.index = [cluster_names.get(i, f"C{i}") for i in profile_z.index]
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

    # 5-fold CV
    cv_rf = cross_val_score(rf, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=42),
                             scoring="roc_auc", n_jobs=-1)
    print(f"\n  Random Forest: AUC={rf_auc:.4f} F1={rf_f1:.4f} Recall={rf_rec:.4f}")
    print(f"  5-fold CV AUC: {cv_rf.mean():.4f} ±{cv_rf.std():.4f}")
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


def run_data_mining() -> dict:
    fact, drug = load_and_prepare()
    apriori_rules   = run_apriori(fact, drug)
    glp1_clustered, cluster_metrics = run_kmeans(fact)
    clf_metrics      = run_classification(fact)

    all_metrics = {
        "clustering": cluster_metrics,
        "classification": clf_metrics,
    }
    with open(PROJECT_ROOT / "reports" / "mining_results.json", "w") as fh:
        json.dump(all_metrics, fh, indent=2, default=str)
    print("\nData mining complete. All models and results saved.")
    return all_metrics


if __name__ == "__main__":
    run_data_mining()
