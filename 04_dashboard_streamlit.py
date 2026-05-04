"""
scripts/04_dashboard_streamlit.py
GLP-1 FAERS Study — Interactive Streamlit Dashboard

Run with:
    streamlit run 04_dashboard_streamlit.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import joblib
import json
from pathlib import Path

# ── Setup & Config ────────────────────────────────────────────────────────
st.set_page_config(page_title="GLP-1 Adverse Events", layout="wide", page_icon="⚕️")

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
MODEL_DIR = PROJECT_ROOT / "models"
REPORT_DIR = PROJECT_ROOT / "reports"

# ── Color Palette ─────────────────────────────────────────────────────────
TEAL, CORAL, YELLOW, NAVY, MUTED = "#02C39A", "#F96167", "#F9C74F", "#065A82", "#9ABCD1"

DRUG_COLORS = {
    "SEMAGLUTIDE": TEAL,
    "TIRZEPATIDE": YELLOW,
    "LIRAGLUTIDE": CORAL,
    "DULAGLUTIDE": "#A78BFA",
    "EXENATIDE": "#60A5FA",
    "CONTROL/OTHER": "#64748B",
}

# ── Data Loading (Cached for Performance) ─────────────────────────────────
@st.cache_data
def load_data():
    fact = pd.read_csv(DATA_DIR / "fact_adverse_event.csv", dtype={"primaryid": str})

    # Pre-process for UI
    fact["quarter"] = fact["quarter"].fillna("Unknown")
    fact["reporter_country"] = fact["reporter_country"].fillna("Other")
    fact["glp1_drug"] = fact["glp1_drug"].fillna("UNKNOWN")

    glp1_df = fact[fact["cohort"] == "glp1"].copy()
    ctrl_df = fact[fact["cohort"] == "control"].copy()

    return glp1_df, ctrl_df


@st.cache_resource
def load_models():
    rf_path = MODEL_DIR / "random_forest.pkl"
    if rf_path.exists():
        return joblib.load(rf_path)
    return None


glp1_df, ctrl_df = load_data()
rf_model = load_models()

# ── Sidebar: Cross-Filtering Engine ───────────────────────────────────────
st.sidebar.title("🔍 FAERS Filters")
st.sidebar.markdown("Filters automatically propagate to all visuals.")

sel_drug = st.sidebar.selectbox(
    "GLP-1 Drug",
    ["ALL"] + sorted(glp1_df["glp1_drug"].unique().tolist()),
)
sel_country = st.sidebar.selectbox("Reporter Country", ["ALL", "US", "Other"])
sel_quarter = st.sidebar.selectbox(
    "Quarter",
    ["ALL"] + sorted(glp1_df["quarter"].unique().tolist()),
)

# Apply filters to GLP-1 cohort dynamically
filtered_glp1 = glp1_df.copy()
if sel_drug != "ALL":
    filtered_glp1 = filtered_glp1[filtered_glp1["glp1_drug"] == sel_drug]
if sel_country != "ALL":
    if sel_country == "US":
        filtered_glp1 = filtered_glp1[filtered_glp1["reporter_country"] == "US"]
    else:
        filtered_glp1 = filtered_glp1[filtered_glp1["reporter_country"] != "US"]
if sel_quarter != "ALL":
    filtered_glp1 = filtered_glp1[filtered_glp1["quarter"] == sel_quarter]

# ── Dynamic Metric Calculations ───────────────────────────────────────────
total_reports = len(filtered_glp1)
gi_events = int(filtered_glp1["gi_severe_flag"].sum())
gi_rate = (gi_events / total_reports * 100) if total_reports > 0 else 0
hosp_rate = (
    filtered_glp1["severity_flag"].sum() / total_reports * 100
) if total_reports > 0 else 0

# Dynamic PRR calculation against the standard Control group
a = gi_events
b = total_reports - a
c = int(ctrl_df["gi_severe_flag"].sum())
d = len(ctrl_df) - c

if (a + b) > 0 and (c + d) > 0 and c > 0:
    prr = (a / (a + b)) / (c / (c + d))
else:
    prr = None

# ── Layout: Header & KPIs ─────────────────────────────────────────────────
st.title("⚕️ GLP-1 Gastrointestinal Adverse Events Dashboard")
st.markdown("**FDA FAERS 2023Q1 – 2026Q1** | CMPE 255 Data Mining")

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total GLP-1 Reports", f"{total_reports:,}")
col2.metric("Severe GI Events", f"{gi_events:,}")
col3.metric("GI Event Rate", f"{gi_rate:.1f}%")
col4.metric("Hospitalization Rate", f"{hosp_rate:.1f}%")
col5.metric(
    "Dynamic PRR vs Control",
    f"{prr:.2f}" if prr is not None else "N/A",
    delta="WHO Signal Threshold: ≥2.0",
    delta_color="inverse" if prr is not None and prr > 2 else "normal",
)

st.divider()

# ── Row 1: Quarterly Trend + Age Distribution ─────────────────────────────
row1_col1, row1_col2 = st.columns(2)

with row1_col1:
    st.subheader("Quarterly Reporting Trend")
    qt = (
        filtered_glp1.groupby("quarter")
        .agg(total=("primaryid", "count"), gi_severe=("gi_severe_flag", "sum"))
        .reset_index()
    )
    qt["gi_rate"] = (qt["gi_severe"] / qt["total"] * 100).fillna(0)

    fig_trend = make_subplots(specs=[[{"secondary_y": True}]])
    fig_trend.add_trace(
        go.Bar(x=qt["quarter"], y=qt["total"], name="Total Reports", marker_color=NAVY),
        secondary_y=False,
    )
    fig_trend.add_trace(
        go.Bar(x=qt["quarter"], y=qt["gi_severe"], name="Severe GI", marker_color=CORAL),
        secondary_y=False,
    )
    fig_trend.add_trace(
        go.Scatter(
            x=qt["quarter"],
            y=qt["gi_rate"],
            name="GI Rate (%)",
            line=dict(color=YELLOW, width=3),
        ),
        secondary_y=True,
    )
    fig_trend.update_layout(
        barmode="overlay",
        margin=dict(l=0, r=0, t=30, b=0),
        height=400,
        yaxis2=dict(title="GI Severe Rate (%)"),
    )
    st.plotly_chart(fig_trend, use_container_width=True)

with row1_col2:
    st.subheader("Age Distribution (Filtered GLP-1 vs Control)")
    fig_age = go.Figure()
    fig_age.add_trace(
        go.Histogram(
            x=filtered_glp1["age_yr"].dropna(),
            name="Filtered GLP-1",
            marker_color=TEAL,
            opacity=0.75,
            nbinsx=40,
        )
    )
    fig_age.add_trace(
        go.Histogram(
            x=ctrl_df["age_yr"].dropna(),
            name="Metformin Control",
            marker_color=CORAL,
            opacity=0.5,
            nbinsx=40,
        )
    )
    fig_age.update_layout(
        barmode="overlay",
        margin=dict(l=0, r=0, t=30, b=0),
        height=400,
        xaxis_title="Age (years)",
        yaxis_title="Count",
    )
    st.plotly_chart(fig_age, use_container_width=True)

st.divider()

# ── Row 2: GI Reaction Heatmap + Severity Sunburst ────────────────────────
row2_col1, row2_col2 = st.columns(2)

with row2_col1:
    st.subheader("GI Reaction × GLP-1 Drug")
    gi_df = filtered_glp1[
        (filtered_glp1["gi_severe_flag"] == 1)
        & (filtered_glp1["gi_reaction_term"].notna())
        & (filtered_glp1["gi_reaction_term"] != "None")
    ].copy()
    if not gi_df.empty:
        gi_df["reaction_clean"] = gi_df["gi_reaction_term"].str.upper().str[:35]
        top_rxns = gi_df["reaction_clean"].value_counts().head(10).index
        heat_df = gi_df[gi_df["reaction_clean"].isin(top_rxns)]
        heat = pd.crosstab(heat_df["reaction_clean"], heat_df["glp1_drug"])
        heat_pct = heat.div(heat.sum(axis=1), axis=0) * 100
        fig_heat = px.imshow(
            heat_pct,
            text_auto=".1f",
            color_continuous_scale="YlOrRd",
            labels=dict(x="GLP-1 Drug", y="MedDRA Preferred Term", color="% of row"),
        )
        fig_heat.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=400)
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("No severe GI events match the current filters.")

with row2_col2:
    st.subheader("Outcome Severity Hierarchy")
    sun_df = filtered_glp1.copy()
    sun_df["gi_label"] = sun_df["gi_severe_flag"].map(
        {1: "GI Severe", 0: "No GI Severe"}
    )
    sun_data = (
        sun_df[sun_df["glp1_drug"] != "CONTROL/OTHER"]
        .groupby(["glp1_drug", "gi_label", "severity_label"])
        .size()
        .reset_index(name="count")
    )
    if not sun_data.empty:
        fig_sun = px.sunburst(
            sun_data,
            path=["glp1_drug", "gi_label", "severity_label"],
            values="count",
            color="glp1_drug",
            color_discrete_map=DRUG_COLORS,
        )
        fig_sun.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=400)
        st.plotly_chart(fig_sun, use_container_width=True)
    else:
        st.info("No data matches the current filters.")

st.divider()

# ── Row 3: Weight Boxplot + PRR by Drug ───────────────────────────────────
row3_col1, row3_col2 = st.columns(2)

with row3_col1:
    st.subheader("Weight Distribution by GI Event Status")
    wt_df = filtered_glp1[filtered_glp1["wt_kg"].notna() & (filtered_glp1["wt_kg"] < 300)].copy()
    wt_df["GI Event"] = wt_df["gi_severe_flag"].map({1: "GI Severe", 0: "No GI Event"})
    if not wt_df.empty:
        fig_wt = px.box(
            wt_df,
            x="GI Event",
            y="wt_kg",
            color="GI Event",
            color_discrete_map={"GI Severe": CORAL, "No GI Event": TEAL},
            labels={"wt_kg": "Weight (kg)"},
        )
        fig_wt.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=380)
        st.plotly_chart(fig_wt, use_container_width=True)
    else:
        st.info("No weight data matches the current filters.")

with row3_col2:
    st.subheader("PRR by GLP-1 Drug vs Metformin/Control")
    drug_prr_rows = []
    c_gi = int(ctrl_df["gi_severe_flag"].sum())
    c_total = len(ctrl_df)
    for drug_name in ["SEMAGLUTIDE", "LIRAGLUTIDE", "DULAGLUTIDE", "TIRZEPATIDE", "EXENATIDE"]:
        sub = filtered_glp1[filtered_glp1["glp1_drug"] == drug_name]
        n = len(sub)
        n_gi = int(sub["gi_severe_flag"].sum())
        if n > 0 and c_gi > 0:
            drug_prr_val = (n_gi / n) / (c_gi / c_total)
            drug_prr_rows.append({"drug": drug_name, "prr": round(drug_prr_val, 3), "n_gi": n_gi})
    if drug_prr_rows:
        prr_df = pd.DataFrame(drug_prr_rows).sort_values("prr", ascending=True)
        colors = [CORAL if p >= 2 else YELLOW if p >= 1.5 else TEAL for p in prr_df["prr"]]
        fig_prr = go.Figure(
            go.Bar(
                x=prr_df["prr"],
                y=prr_df["drug"],
                orientation="h",
                marker_color=colors,
                text=[f"n={r}" for r in prr_df["n_gi"]],
                textposition="outside",
            )
        )
        fig_prr.add_vline(x=2.0, line_dash="dash", line_color=CORAL,
                          annotation_text="PRR=2 (WHO-UMC signal)")
        fig_prr.add_vline(x=1.0, line_dash="dot", line_color=MUTED)
        fig_prr.update_layout(margin=dict(l=0, r=0, t=30, b=0), height=380,
                               xaxis_title="PRR")
        st.plotly_chart(fig_prr, use_container_width=True)
    else:
        st.info("Insufficient data for per-drug PRR with current filters.")

st.divider()

# ── Live Machine Learning: Risk Calculator ────────────────────────────────
st.subheader("⚕️ Live Patient Risk Calculator (Random Forest)")
st.markdown(
    "Enter patient characteristics to evaluate the probability of a severe outcome "
    "(Hospitalization / Life-Threatening / Death). "
    "This form queries the trained `scikit-learn` Random Forest model directly — no heuristics."
)

with st.container(border=True):
    rc_col1, rc_col2, rc_col3 = st.columns([1, 1, 1.5])

    with rc_col1:
        rc_age = st.slider("Age (years)", 18, 95, 60)
        rc_wt = st.slider("Weight (kg)", 40, 200, 90)
        rc_poly = st.slider("Polypharmacy Count", 1, 20, 4)
        rc_tto = st.slider("Time to Onset (days)", 1, 730, 90)

    with rc_col2:
        rc_drug = st.selectbox(
            "GLP-1 Drug",
            ["SEMAGLUTIDE", "TIRZEPATIDE", "LIRAGLUTIDE", "DULAGLUTIDE", "EXENATIDE"],
        )
        rc_sex = st.selectbox("Sex", ["Female", "Male"])
        rc_opioid = st.selectbox("Concurrent Opioid", ["No", "Yes"])
        rc_gi = st.selectbox("GI Severe Event Flag", ["No", "Yes"])
        rc_us = st.selectbox("Reporter Country", ["US", "Other"])

    with rc_col3:
        if rf_model is not None:
            # Reconstruct feature vector exactly as trained in 03_data_mining.py
            # LabelEncoder on GLP-1 cohort glp1_drug (alphabetical): CONTROL/OTHER=0,
            # DULAGLUTIDE=1, EXENATIDE=2, LIRAGLUTIDE=3, SEMAGLUTIDE=4, TIRZEPATIDE=5
            drug_map = {
                "SEMAGLUTIDE": 4,
                "TIRZEPATIDE": 5,
                "LIRAGLUTIDE": 3,
                "DULAGLUTIDE": 1,
                "EXENATIDE": 2,
            }

            features = pd.DataFrame(
                [
                    {
                        "age_yr": rc_age,
                        "wt_kg": rc_wt,
                        "polypharmacy_count": rc_poly,
                        "concurrent_opioid": 1 if rc_opioid == "Yes" else 0,
                        "sex_bin": 1 if rc_sex == "Female" else 0,
                        "is_us": 1 if rc_us == "US" else 0,
                        "gi_severe_flag": 1 if rc_gi == "Yes" else 0,
                        "glp1_drug_enc": drug_map.get(rc_drug, 4),
                        "time_to_onset_days": rc_tto,
                        "log_poly": np.log1p(rc_poly),
                        "age_wt_interaction": (rc_age * rc_wt) / 1000,
                    }
                ]
            )

            prob = rf_model.predict_proba(features)[0][1]
            pct = prob * 100

            if prob > 0.60:
                color = CORAL
                risk_lvl = "🔴 HIGH RISK"
                badge_bg = "rgba(249,97,103,0.15)"
            elif prob > 0.35:
                color = YELLOW
                risk_lvl = "🟡 MODERATE RISK"
                badge_bg = "rgba(249,199,79,0.15)"
            else:
                color = TEAL
                risk_lvl = "🟢 LOWER RISK"
                badge_bg = "rgba(2,195,154,0.15)"

            # Contextual insights
            insights = []
            if rc_opioid == "Yes":
                insights.append(
                    "⚠️ Concurrent opioid use significantly elevates risk — opioids also delay gastric emptying."
                )
            if rc_poly >= 8:
                insights.append(
                    f"⚠️ High polypharmacy ({rc_poly} drugs) is the strongest modifiable risk factor."
                )
            if rc_gi == "Yes":
                insights.append(
                    "🔴 GI severe event already flagged — hospitalization probability elevated substantially."
                )
            if rc_age >= 65:
                insights.append(
                    f"📌 Age {rc_age}: older patients (65+) show disproportionate GI complication rates."
                )
            if rc_tto < 30:
                insights.append(
                    "⏱️ Rapid onset (<30 days) suggests acute GI reaction — warrants urgent monitoring."
                )
            if not insights:
                insights.append("✅ No acute high-risk flags. Continue standard monitoring protocol.")

            st.markdown(
                f"""
                <div style="
                    background:{badge_bg};
                    border:2px solid {color};
                    border-radius:14px;
                    padding:24px;
                    text-align:center;
                ">
                    <div style="font-size:0.8rem; color:{MUTED}; margin-bottom:6px;">
                        Estimated Probability of Severe Adverse Event
                    </div>
                    <div style="font-size:3rem; font-weight:800; color:{color};">
                        {pct:.1f}%
                    </div>
                    <div style="
                        margin-top:10px;
                        padding:6px 18px;
                        border-radius:20px;
                        display:inline-block;
                        font-weight:700;
                        font-size:0.9rem;
                        background:{badge_bg};
                        color:{color};
                        border:1px solid {color};
                    ">{risk_lvl}</div>
                    <div style="
                        font-size:0.8rem;
                        color:{MUTED};
                        margin-top:14px;
                        text-align:left;
                        line-height:1.6;
                    ">
                        {"<br>".join(insights)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.warning(
                "Random Forest model not found. Please run `03_data_mining.py` first."
            )

st.divider()

# ── Footer ─────────────────────────────────────────────────────────────────
st.caption(
    "Data source: FDA FAERS ASCII files 2023Q1–2026Q1 · "
    "For research purposes only — not for clinical decision-making."
)
