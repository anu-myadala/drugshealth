"""
scripts/02_eda_stats.py
GLP-1 FAERS Study — Exploratory Data Analysis & Statistical Testing

Tests performed:
  1. Chi-Square Test of Independence: GLP-1 vs Control × GI Event incidence
  2. Proportional Reporting Ratio (PRR): Core pharmacovigilance signal metric
  3. Mann-Whitney U Test: Weight distribution — severe vs non-severe GI events
  4. Descriptive statistics: Age, weight, time-to-onset distributions
  5. Reporting Over Time: quarterly trend of GLP-1 GI reports
"""

import warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import seaborn as sns
from scipy import stats
from scipy.stats import chi2_contingency, mannwhitneyu
from pathlib import Path
import json

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", font_scale=1.0)

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR  = PROJECT_ROOT / "data" / "processed"
FIG_DIR   = PROJECT_ROOT / "reports" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── Color palette ──────────────────────────────────────────────────────────────
GLP1_COLOR = "#1B6CA8"
CTRL_COLOR = "#CC4E2A"
SEVERE_COLOR = "#8B1A1A"
MILD_COLOR   = "#2E7D32"
PALETTE = {"glp1": GLP1_COLOR, "control": CTRL_COLOR}


def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "fact_adverse_event.csv", dtype={"primaryid": str, "caseid": str})
    df["fda_dt_n"] = pd.to_numeric(df.get("fda_dt", pd.Series()), errors="coerce")
    return df


# ── 1. DESCRIPTIVE STATISTICS ─────────────────────────────────────────────────
def descriptive_stats(df: pd.DataFrame) -> dict:
    stats_out = {}
    for cohort in ["glp1", "control"]:
        sub = df[df["cohort"] == cohort]
        stats_out[cohort] = {
            "n": len(sub),
            "age_mean": round(sub["age_yr"].mean(), 2),
            "age_median": round(sub["age_yr"].median(), 2),
            "age_std": round(sub["age_yr"].std(), 2),
            "wt_mean_kg": round(sub["wt_kg"].mean(), 2),
            "wt_median_kg": round(sub["wt_kg"].median(), 2),
            "pct_female": round((sub["sex_clean"] == "Female").mean() * 100, 1),
            "pct_gi_severe": round(sub["gi_severe_flag"].mean() * 100, 2),
            "pct_severity_1": round(sub["severity_flag"].mean() * 100, 1),
            "pct_opioid": round(sub["concurrent_opioid"].mean() * 100, 1),
            "poly_median": round(sub["polypharmacy_count"].median(), 1),
        }
    return stats_out


# ── 2. CHI-SQUARE TEST ────────────────────────────────────────────────────────
def chi_square_gi_vs_cohort(df: pd.DataFrame) -> dict:
    """
    H0: GI adverse event incidence is independent of drug cohort (GLP-1 vs Control).
    Contingency table: [GI event, No GI event] × [GLP-1, Control]
    """
    sub = df[df["cohort"].isin(["glp1", "control"])]
    ct = pd.crosstab(sub["cohort"], sub["gi_severe_flag"])
    ct.columns = ["No GI Severe", "GI Severe"]

    chi2, p, dof, expected = chi2_contingency(ct)
    cramers_v = np.sqrt(chi2 / (sub.shape[0] * (min(ct.shape) - 1)))

    result = {
        "test": "Chi-Square Test of Independence",
        "h0": "GI event incidence is independent of GLP-1 vs Control drug use",
        "contingency_table": ct.to_dict(),
        "chi2_statistic": round(float(chi2), 4),
        "p_value": float(p),
        "degrees_of_freedom": int(dof),
        "cramers_v": round(float(cramers_v), 4),
        "reject_h0": p < 0.05,
        "interpretation": (
            f"χ²({dof}) = {chi2:.2f}, p {'< 0.001' if p < 0.001 else f'= {p:.4f}'}. "
            f"{'Strong' if p < 0.001 else 'No'} statistical evidence that GLP-1 use is "
            f"associated with higher GI event incidence. Cramér's V = {cramers_v:.3f} "
            f"({'small' if cramers_v < 0.1 else 'moderate' if cramers_v < 0.3 else 'large'} effect)."
        ),
    }
    print(f"\nChi-Square Test:")
    print(ct)
    print(f"  χ² = {chi2:.4f}, p = {p:.2e}, dof = {dof}, Cramér's V = {cramers_v:.4f}")
    return result


# ── 3. PROPORTIONAL REPORTING RATIO (PRR) ────────────────────────────────────
def calculate_prr(df: pd.DataFrame) -> dict:
    """
    PRR = (a / (a+b)) / (c / (c+d))
    Where:
      a = GLP-1 patients WITH target GI event
      b = GLP-1 patients WITHOUT target GI event
      c = Control patients WITH target GI event
      d = Control patients WITHOUT target GI event

    PRR > 2 with Chi² > 4 and n ≥ 3 = regulatory signal threshold (WHO-UMC criteria)

    Also compute Reporting Odds Ratio (ROR) = (a/b) / (c/d) with 95% CI
    """
    glp1   = df[df["cohort"] == "glp1"]
    ctrl   = df[df["cohort"] == "control"]

    a = int(glp1["gi_severe_flag"].sum())       # GLP-1 with GI event
    b = int((glp1["gi_severe_flag"] == 0).sum())# GLP-1 without GI event
    c = int(ctrl["gi_severe_flag"].sum())        # Control with GI event
    d = int((ctrl["gi_severe_flag"] == 0).sum()) # Control without GI event

    prr = (a / (a + b)) / (c / (c + d)) if c > 0 else float("inf")
    # 95% CI for PRR using log-normal approximation
    se_log_prr = np.sqrt(1/a - 1/(a+b) + 1/c - 1/(c+d)) if a > 0 and c > 0 else np.nan
    prr_lower  = np.exp(np.log(prr) - 1.96 * se_log_prr) if not np.isnan(se_log_prr) else np.nan
    prr_upper  = np.exp(np.log(prr) + 1.96 * se_log_prr) if not np.isnan(se_log_prr) else np.nan

    # Reporting Odds Ratio
    ror = (a * d) / (b * c) if b > 0 and c > 0 and d > 0 else float("inf")
    se_log_ror = np.sqrt(1/a + 1/b + 1/c + 1/d) if all(x > 0 for x in [a,b,c,d]) else np.nan
    ror_lower  = np.exp(np.log(ror) - 1.96 * se_log_ror) if not np.isnan(se_log_ror) else np.nan
    ror_upper  = np.exp(np.log(ror) + 1.96 * se_log_ror) if not np.isnan(se_log_ror) else np.nan

    # Chi² for PRR signal
    ct = np.array([[a, b], [c, d]])
    chi2, p, _, _ = chi2_contingency(ct)

    # PRR per individual GLP-1 drug
    per_drug_prr = {}
    for drug in ["SEMAGLUTIDE", "LIRAGLUTIDE", "DULAGLUTIDE", "TIRZEPATIDE", "EXENATIDE"]:
        drug_sub = df[df["glp1_drug"] == drug]
        a_d = int(drug_sub["gi_severe_flag"].sum())
        b_d = int((drug_sub["gi_severe_flag"] == 0).sum())
        if a_d + b_d > 0 and c > 0:
            prr_d = (a_d / (a_d + b_d)) / (c / (c + d))
            per_drug_prr[drug] = {"n": a_d + b_d, "gi_events": a_d, "prr": round(prr_d, 3)}

    result = {
        "test": "Proportional Reporting Ratio (PRR)",
        "contingency": {"a_glp1_gi": a, "b_glp1_no_gi": b, "c_ctrl_gi": c, "d_ctrl_no_gi": d},
        "prr": round(float(prr), 3),
        "prr_95ci": [round(float(prr_lower), 3), round(float(prr_upper), 3)],
        "ror": round(float(ror), 3),
        "ror_95ci": [round(float(ror_lower), 3), round(float(ror_upper), 3)],
        "chi2": round(float(chi2), 3),
        "p_value": float(p),
        "signal_threshold": {"prr_gt_2": prr > 2, "chi2_gt_4": chi2 > 4, "n_ge_3": a >= 3},
        "who_umc_signal": prr > 2 and chi2 > 4 and a >= 3,
        "per_drug_prr": per_drug_prr,
        "interpretation": (
            f"PRR = {prr:.2f} (95% CI {prr_lower:.2f}–{prr_upper:.2f}). "
            f"ROR = {ror:.2f} (95% CI {ror_lower:.2f}–{ror_upper:.2f}). "
            f"{'WHO-UMC regulatory signal detected (PRR>2, χ²>4, n≥3).' if prr>2 and chi2>4 and a>=3 else 'Signal below WHO-UMC threshold.'}"
        ),
    }
    print(f"\nPRR Analysis:")
    print(f"  GLP-1: {a} GI severe / {a+b} total  ({100*a/(a+b):.2f}%)")
    print(f"  Control: {c} GI severe / {c+d} total ({100*c/(c+d):.2f}%)")
    print(f"  PRR = {prr:.3f} (95% CI {prr_lower:.2f}–{prr_upper:.2f})")
    print(f"  ROR = {ror:.3f} (95% CI {ror_lower:.2f}–{ror_upper:.2f})")
    print(f"  WHO-UMC signal: {result['who_umc_signal']}")
    return result


# ── 4. MANN-WHITNEY U TEST ────────────────────────────────────────────────────
def mann_whitney_weight(df: pd.DataFrame) -> dict:
    """
    H0: The median weight of patients with severe GI events = median weight without.
    Non-parametric (weight distributions are non-normal in FAERS data).
    Effect size: rank-biserial correlation r = 1 - 2U/(n1*n2)
    """
    gi_sub    = df[(df["cohort"] == "glp1") & df["wt_kg"].notna()]
    severe    = gi_sub.loc[gi_sub["gi_severe_flag"] == 1, "wt_kg"]
    non_severe= gi_sub.loc[gi_sub["gi_severe_flag"] == 0, "wt_kg"]

    stat, p = mannwhitneyu(severe, non_severe, alternative="two-sided")
    n1, n2 = len(severe), len(non_severe)
    r = 1 - (2 * stat) / (n1 * n2)  # rank-biserial correlation

    result = {
        "test": "Mann-Whitney U Test (Weight: Severe GI vs Non-Severe GI, GLP-1 cohort)",
        "h0": "Median weight is equal in severe vs non-severe GI event patients",
        "n_severe": n1, "n_non_severe": n2,
        "median_severe_kg": round(float(severe.median()), 1),
        "median_non_severe_kg": round(float(non_severe.median()), 1),
        "u_statistic": float(stat),
        "p_value": float(p),
        "effect_size_r": round(float(r), 4),
        "reject_h0": p < 0.05,
        "interpretation": (
            f"U = {stat:.0f}, p {'< 0.001' if p < 0.001 else f'= {p:.4f}'}. "
            f"Median weight: severe = {severe.median():.1f} kg vs non-severe = {non_severe.median():.1f} kg. "
            f"Effect size r = {r:.3f} ({'negligible' if abs(r)<0.1 else 'small' if abs(r)<0.3 else 'moderate' if abs(r)<0.5 else 'large'}). "
            f"{'Statistically significant' if p < 0.05 else 'Not statistically significant'} difference."
        ),
    }
    print(f"\nMann-Whitney U Test (Weight):")
    print(f"  Severe GI: n={n1}, median={severe.median():.1f} kg")
    print(f"  Non-Severe: n={n2}, median={non_severe.median():.1f} kg")
    print(f"  U={stat:.0f}, p={p:.4e}, r={r:.4f}")
    return result


# ── VISUALIZATIONS ────────────────────────────────────────────────────────────
def plot_age_distribution(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, cohort, color, label in zip(
        axes,
        ["glp1", "control"],
        [GLP1_COLOR, CTRL_COLOR],
        ["GLP-1 Cohort", "Control Cohort"]
    ):
        sub = df[(df["cohort"] == cohort) & df["age_yr"].notna() & (df["age_yr"] < 120)]
        ax.hist(sub["age_yr"], bins=40, color=color, alpha=0.8, edgecolor="white", linewidth=0.4)
        ax.axvline(sub["age_yr"].median(), color="black", lw=2, ls="--",
                   label=f"Median: {sub['age_yr'].median():.0f} yr")
        ax.set_xlabel("Age (years)", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.set_title(f"Age Distribution — {label}\n(n={len(sub):,})", fontsize=11)
        ax.legend(fontsize=10)
    plt.suptitle("Patient Age Distribution: GLP-1 vs Control Cohort\nFDA FAERS 2023Q1–2026Q1",
                 fontsize=12, y=1.01)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "age_distribution.png", dpi=160, bbox_inches="tight")
    plt.close()


def plot_weight_boxplot(df: pd.DataFrame):
    plot_df = df[df["cohort"].isin(["glp1","control"]) & df["wt_kg"].notna() & (df["wt_kg"] < 300)].copy()
    plot_df["GI Event"] = plot_df["gi_severe_flag"].map({1: "GI Severe Event", 0: "No GI Event"})
    plot_df["Cohort"]   = plot_df["cohort"].map({"glp1": "GLP-1", "control": "Control"})

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sns.boxplot(data=plot_df, x="Cohort", y="wt_kg", hue="GI Event",
                palette={"GI Severe Event": SEVERE_COLOR, "No GI Event": MILD_COLOR},
                ax=axes[0], width=0.5, linewidth=1.2)
    axes[0].set_xlabel("Drug Cohort", fontsize=11)
    axes[0].set_ylabel("Weight (kg)", fontsize=11)
    axes[0].set_title("Weight Distribution by Cohort and GI Event Status\n(Mann-Whitney U Test)", fontsize=11)
    axes[0].legend(fontsize=9)

    # Violin plot of time-to-onset for GI severe events
    tto = df[(df["gi_severe_flag"] == 1) & df["time_to_onset_days"].notna()
             & (df["time_to_onset_days"] < 365*3)].copy()
    tto["Drug"] = tto["glp1_drug"].replace("CONTROL/OTHER", "Control")
    drug_order = tto.groupby("Drug")["time_to_onset_days"].median().sort_values().index.tolist()
    sns.boxplot(data=tto, x="Drug", y="time_to_onset_days", order=drug_order,
                palette="Set2", ax=axes[1], linewidth=1)
    axes[1].set_xlabel("Drug", fontsize=11)
    axes[1].set_ylabel("Time to GI Event Onset (days)", fontsize=11)
    axes[1].set_title("Time-to-Onset Distribution for GI Events\nby GLP-1 Drug", fontsize=11)
    axes[1].tick_params(axis="x", rotation=30)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "weight_timeonset_boxplot.png", dpi=160, bbox_inches="tight")
    plt.close()


def plot_quarterly_trends(df: pd.DataFrame):
    df["quarter_sort"] = df["quarter"].apply(
        lambda q: int(q.replace("Q", "")) if q[0].isdigit()
        else int(q[2:4]) * 10 + int(q[-1]))
    q_trend = (df[df["cohort"] == "glp1"]
               .groupby("quarter")
               .agg(total_reports=("primaryid","count"),
                    gi_severe=("gi_severe_flag","sum"),
                    hospitalized=("severity_flag","sum"))
               .reset_index())
    q_trend["gi_rate_pct"] = 100 * q_trend["gi_severe"] / q_trend["total_reports"]
    q_trend = q_trend.sort_values("quarter")

    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    axes[0].bar(range(len(q_trend)), q_trend["total_reports"], color=GLP1_COLOR, alpha=0.85,
                label="Total GLP-1 reports")
    axes[0].bar(range(len(q_trend)), q_trend["gi_severe"], color=SEVERE_COLOR, alpha=0.9,
                label="Severe GI events")
    axes[0].set_ylabel("Report Count", fontsize=11)
    axes[0].set_title("GLP-1 Adverse Event Reports by Quarter\nFDA FAERS 2023Q1–2026Q1", fontsize=11)
    axes[0].legend(fontsize=10)
    axes[0].set_xticks(range(len(q_trend)))
    axes[0].set_xticklabels(q_trend["quarter"], rotation=45, ha="right", fontsize=9)

    axes[1].plot(range(len(q_trend)), q_trend["gi_rate_pct"], "o-",
                 color=SEVERE_COLOR, lw=2, ms=8, label="GI Severe Rate (%)")
    axes[1].set_ylabel("GI Severe Rate (%)", fontsize=11)
    axes[1].set_title("GI Severe Event Rate Over Time (GLP-1 Cohort)", fontsize=11)
    axes[1].set_xticks(range(len(q_trend)))
    axes[1].set_xticklabels(q_trend["quarter"], rotation=45, ha="right", fontsize=9)
    axes[1].grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "quarterly_trends.png", dpi=160, bbox_inches="tight")
    plt.close()


def plot_prr_forest(prr_result: dict):
    """Forest plot showing PRR per GLP-1 drug."""
    drugs = list(prr_result["per_drug_prr"].keys())
    prrs  = [prr_result["per_drug_prr"][d]["prr"] for d in drugs]
    counts= [prr_result["per_drug_prr"][d]["gi_events"] for d in drugs]

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = [SEVERE_COLOR if p > 2 else GLP1_COLOR for p in prrs]
    bars = ax.barh(drugs, prrs, color=colors, alpha=0.85, height=0.5)
    ax.axvline(2.0, color="red", lw=1.5, ls="--", label="PRR=2 (Signal threshold)")
    ax.axvline(1.0, color="gray", lw=1, ls=":", label="PRR=1 (No association)")
    for bar, n in zip(bars, counts):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2,
                f"n={n:,}", va="center", fontsize=9)
    ax.set_xlabel("Proportional Reporting Ratio (PRR)", fontsize=11)
    ax.set_title(f"PRR by GLP-1 Drug vs Control (Metformin/Other)\n"
                 f"Overall PRR = {prr_result['prr']:.2f} "
                 f"(95% CI {prr_result['prr_95ci'][0]}–{prr_result['prr_95ci'][1]})", fontsize=11)
    ax.legend(fontsize=10)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "prr_forest_plot.png", dpi=160, bbox_inches="tight")
    plt.close()


def plot_reaction_heatmap(df: pd.DataFrame):
    """Heatmap of GI reaction type × GLP-1 drug."""
    gi_df = df[(df["cohort"] == "glp1") & (df["gi_severe_flag"] == 1)
               & (df["gi_reaction_term"] != "None")].copy()
    gi_df["gi_reaction_clean"] = gi_df["gi_reaction_term"].str.upper().str[:35]
    top_reactions = gi_df["gi_reaction_clean"].value_counts().head(10).index
    gi_df2 = gi_df[gi_df["gi_reaction_clean"].isin(top_reactions)]

    heat = pd.crosstab(gi_df2["gi_reaction_clean"], gi_df2["glp1_drug"])
    heat_pct = heat.div(heat.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.heatmap(heat_pct, annot=True, fmt=".1f", cmap="YlOrRd",
                linewidths=0.4, ax=ax, cbar_kws={"label": "% of row total"},
                annot_kws={"size": 9})
    ax.set_title("GI Reaction Type × GLP-1 Drug (% of each reaction's reports)\n"
                 "Top 10 GI Reaction Terms — FDA FAERS 2023–2026", fontsize=11)
    ax.set_xlabel("GLP-1 Drug", fontsize=11)
    ax.set_ylabel("MedDRA Preferred Term", fontsize=11)
    ax.tick_params(axis="x", rotation=30)
    ax.tick_params(axis="y", rotation=0)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "reaction_drug_heatmap.png", dpi=160, bbox_inches="tight")
    plt.close()


def plot_severity_pie(df: pd.DataFrame):
    glp1 = df[df["cohort"] == "glp1"]["severity_label"].value_counts()
    order = ["Death", "Life-Threatening", "Hospitalization", "Disability",
             "Required Intervention", "Congenital Anomaly", "Other"]
    glp1 = glp1.reindex([o for o in order if o in glp1.index])
    colors = ["#8B0000","#CC2900","#E85D04","#FF9F1C","#FFBF69","#CBF3F0","#C8E6C9"]
    fig, ax = plt.subplots(figsize=(7, 7))
    wedges, texts, autotexts = ax.pie(
        glp1.values, labels=glp1.index, autopct="%1.1f%%",
        colors=colors[:len(glp1)], startangle=140,
        pctdistance=0.8, wedgeprops={"linewidth": 0.5, "edgecolor": "white"})
    for t in autotexts: t.set_fontsize(9)
    ax.set_title("Outcome Severity Distribution — GLP-1 Cohort\n"
                 "FDA FAERS 2023Q1–2026Q1", fontsize=12)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "severity_pie.png", dpi=160, bbox_inches="tight")
    plt.close()


def plot_country_map_bar(df: pd.DataFrame):
    top_countries = (df[df["cohort"] == "glp1"]["reporter_country"]
                     .value_counts().head(15).reset_index())
    top_countries.columns = ["country", "count"]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.barh(top_countries["country"][::-1], top_countries["count"][::-1],
                   color=GLP1_COLOR, alpha=0.85)
    ax.set_xlabel("Number of Reports", fontsize=11)
    ax.set_title("Top 15 Reporting Countries — GLP-1 Adverse Events\nFDA FAERS 2023Q1–2026Q1", fontsize=11)
    for bar, val in zip(bars, top_countries["count"][::-1]):
        ax.text(bar.get_width() + 200, bar.get_y() + bar.get_height()/2,
                f"{val:,}", va="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "country_distribution.png", dpi=160, bbox_inches="tight")
    plt.close()


def run_eda() -> dict:
    df = load_data()
    print(f"Loaded {len(df):,} unique cases")
    print(f"GLP-1: {(df['cohort']=='glp1').sum():,} | Control: {(df['cohort']=='control').sum():,}")

    desc    = descriptive_stats(df)
    chi2_r  = chi_square_gi_vs_cohort(df)
    prr_r   = calculate_prr(df)
    mw_r    = mann_whitney_weight(df)

    print("\nGenerating EDA figures ...")
    plot_age_distribution(df)
    plot_weight_boxplot(df)
    plot_quarterly_trends(df)
    plot_prr_forest(prr_r)
    plot_reaction_heatmap(df)
    plot_severity_pie(df)
    plot_country_map_bar(df)
    print("All figures saved.")

    results = {
        "descriptive_stats": desc,
        "chi_square": chi2_r,
        "prr": prr_r,
        "mann_whitney": mw_r,
    }
    with open(PROJECT_ROOT / "reports" / "eda_results.json", "w") as fh:
        json.dump(results, fh, indent=2, default=str)
    print("\nEDA results saved to reports/eda_results.json")
    return results


if __name__ == "__main__":
    run_eda()
