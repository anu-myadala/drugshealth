"""
scripts/01_etl.py
GLP-1 FAERS Adverse Event Study — ETL Pipeline
Covers 13 quarters: 2023Q1 → 2026Q1 (3.25 years)

Data sources: FDA FAERS ASCII quarterly zip files
  Tables used: DEMO (demographics), DRUG (medications),
               REAC (reactions), OUTC (outcomes), THER (therapy dates)

GLP-1 drugs: SEMAGLUTIDE, LIRAGLUTIDE, DULAGLUTIDE, TIRZEPATIDE, EXENATIDE
GI reactions: GASTROPARESIS, PANCREATITIS, INTESTINAL OBSTRUCTION, ILEUS,
              DELAYED GASTRIC EMPTYING, NAUSEA/VOMITING (broad), BOWEL OBSTRUCTION

Star Schema:
  Fact_Adverse_Event → primaryid (PK)
    Dim_Patient       → demographics (age, sex, weight, country)
    Dim_Drug_Profile  → drug name, GLP-1 flag, polypharmacy count, concurrent opioid
    Dim_Reaction      → MedDRA PT term, GI flag, severity
"""

import os, io, glob, zipfile, re, logging
from pathlib import Path
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR     = PROJECT_ROOT / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)
# By default the pipeline expects FAERS zip files in FAERS_DIR. For local runs
# you can set either the FAERS_DIR env var (a folder) or FAERS_ZIP_LIST env var
# containing a list of absolute zip paths separated by os.pathsep (":" on mac/linux).
FAERS_DIR = Path(os.environ.get("FAERS_DIR", "/mnt/user-data/uploads"))


def _parse_env_zip_list() -> list[Path] | None:
    """Parse FAERS_ZIP_LIST environment variable into Path list.
    Supports os.pathsep (':' on mac/linux) or ';' separated lists.
    """
    raw = os.environ.get("FAERS_ZIP_LIST")
    if not raw:
        return None
    # Support common separators
    parts = []
    if os.pathsep in raw:
        parts = raw.split(os.pathsep)
    elif ";" in raw:
        parts = raw.split(";")
    elif "," in raw:
        parts = raw.split(",")
    else:
        parts = [raw]
    paths = [Path(p).expanduser().resolve() for p in parts if p]
    return paths

# ── Drug filters ──────────────────────────────────────────────────────────────
GLP1_DRUGS = ["SEMAGLUTIDE", "LIRAGLUTIDE", "DULAGLUTIDE", "TIRZEPATIDE", "EXENATIDE"]
CONTROL_DRUGS = ["METFORMIN", "SITAGLIPTIN", "EMPAGLIFLOZIN",
                 "DAPAGLIFLOZIN", "GLIPIZIDE", "GLIMEPIRIDE"]
OPIOID_DRUGS  = ["OXYCODONE", "HYDROCODONE", "MORPHINE", "FENTANYL",
                 "TRAMADOL", "CODEINE", "HYDROMORPHONE", "BUPRENORPHINE"]

# ── Reaction filters (MedDRA Preferred Terms) ─────────────────────────────────
GI_TERMS = [
    "GASTROPARESIS", "PANCREATITIS", "INTESTINAL OBSTRUCTION",
    "BOWEL OBSTRUCTION", "ILEUS", "DELAYED GASTRIC EMPTYING",
    "GASTRIC EMPTYING IMPAIRED", "SMALL INTESTINAL OBSTRUCTION",
    "LARGE INTESTINAL OBSTRUCTION", "PARALYTIC ILEUS",
    "ACUTE PANCREATITIS", "CHRONIC PANCREATITIS", "NECROTISING PANCREATITIS",
]

# MedDRA GI broader terms (for PRR background)
GI_BROAD = ["NAUSEA", "VOMITING", "DIARRHEA", "CONSTIPATION", "ABDOMINAL PAIN",
            "GASTRITIS", "GASTROENTERITIS", "DYSPEPSIA"]

# Outcome code → severity
OUTC_SEVERITY = {
    "DE": "Death",
    "LT": "Life-Threatening",
    "HO": "Hospitalization",
    "DS": "Disability",
    "CA": "Congenital Anomaly",
    "RI": "Required Intervention",
    "OT": "Other",
}
SERIOUS_CODES = {"DE", "LT", "HO", "DS"}


def list_quarter_zips() -> list[Path]:
    """Return all FAERS quarterly zip files sorted chronologically."""
    # If FAERS_ZIP_LIST env var is provided, use that exact ordering.
    env_list = _parse_env_zip_list()
    if env_list:
        found = [p for p in env_list if p.exists()]
        log.info(f"Using FAERS_ZIP_LIST with {len(found)} files")
        return found

    pattern = str(FAERS_DIR / "faers_ascii_*.zip")
    zips = sorted(glob.glob(pattern))
    log.info(f"Found {len(zips)} quarterly zip files in FAERS_DIR={FAERS_DIR}")
    return [Path(z) for z in zips]


def find_file(archive: zipfile.ZipFile, prefix: str) -> str | None:
    """Find a file inside the zip matching a prefix (e.g. 'DEMO', 'DRUG')."""
    for name in archive.namelist():
        if prefix.upper() in name.upper() and name.endswith(".txt"):
            return name
    return None


def read_table(archive: zipfile.ZipFile, prefix: str) -> pd.DataFrame:
    """Read a FAERS ASCII table (dollar-delimited) from the zip archive."""
    fname = find_file(archive, prefix)
    if fname is None:
        log.warning(f"  Table {prefix} not found in archive")
        return pd.DataFrame()
    data = archive.read(fname)
    df = pd.read_csv(io.BytesIO(data), sep="$", engine="python",
                     dtype=str, na_values=["", ".", "NULL", "null", "NA"])
    df.columns = [c.strip().lower() for c in df.columns]
    log.info(f"    {prefix}: {len(df):,} rows")
    return df


def process_quarter(zip_path: Path) -> dict[str, pd.DataFrame]:
    """Extract and filter one quarter's FAERS data."""
    quarter = zip_path.stem.replace("faers_ascii_", "").upper()
    log.info(f"Processing {quarter} ...")

    with zipfile.ZipFile(zip_path) as arch:
        demo = read_table(arch, "DEMO")
        drug = read_table(arch, "DRUG")
        reac = read_table(arch, "REAC")
        outc = read_table(arch, "OUTC")
        ther = read_table(arch, "THER")

    if demo.empty or drug.empty or reac.empty:
        return {}

    # ── Normalise primaryid to string ──────────────────────────────────────
    for df in [demo, drug, reac, outc, ther]:
        if "primaryid" in df.columns:
            df["primaryid"] = df["primaryid"].astype(str).str.strip()
        if "caseid" in df.columns:
            df["caseid"] = df["caseid"].astype(str).str.strip()

    # ── Deduplicate DEMO: keep latest version per case ─────────────────────
    demo["caseversion"] = pd.to_numeric(demo.get("caseversion", pd.Series(dtype=float)), errors="coerce")
    demo["fda_dt"]      = pd.to_numeric(demo.get("fda_dt", pd.Series(dtype=float)), errors="coerce")
    demo = (demo.sort_values(["caseid", "caseversion", "fda_dt"], ascending=[True, False, False])
                .drop_duplicates(subset="caseid", keep="first")
                .reset_index(drop=True))

    # ── Tag GLP-1 vs control drugs ─────────────────────────────────────────
    drug["prod_ai_upper"] = drug["prod_ai"].fillna("").str.upper()
    glp1_pat    = "|".join(GLP1_DRUGS)
    control_pat = "|".join(CONTROL_DRUGS)
    opioid_pat  = "|".join(OPIOID_DRUGS)

    drug["is_glp1"]    = drug["prod_ai_upper"].str.contains(glp1_pat, regex=True, na=False)
    drug["is_control"] = drug["prod_ai_upper"].str.contains(control_pat, regex=True, na=False)
    drug["is_opioid"]  = drug["prod_ai_upper"].str.contains(opioid_pat, regex=True, na=False)

    # Specific GLP-1 drug name
    drug["glp1_drug"] = ""
    for name in GLP1_DRUGS:
        mask = drug["prod_ai_upper"].str.contains(name, na=False)
        drug.loc[mask, "glp1_drug"] = name

    # ── primaryids in GLP-1 or control cohorts ─────────────────────────────
    glp1_pids    = set(drug.loc[drug["is_glp1"],    "primaryid"])
    control_pids = set(drug.loc[drug["is_control"], "primaryid"])
    all_pids     = glp1_pids | control_pids

    if not all_pids:
        return {}

    # ── Polypharmacy count per patient ─────────────────────────────────────
    poly = (drug.groupby("primaryid")["prod_ai_upper"]
                .nunique().reset_index()
                .rename(columns={"prod_ai_upper": "polypharmacy_count"}))

    # Opioid flag per patient
    opioid_pids = set(drug.loc[drug["is_opioid"], "primaryid"])

    # Primary GLP-1 drug per patient (first PS/SS role, or first listed)
    primary_drug = (drug[drug["primaryid"].isin(glp1_pids) & drug["is_glp1"]]
                    .drop_duplicates(subset="primaryid", keep="first")
                    [["primaryid", "glp1_drug"]])

    # ── Filter REAC for GI terms ───────────────────────────────────────────
    reac["pt_upper"] = reac["pt"].fillna("").str.upper().str.strip()
    gi_pat   = "|".join(GI_TERMS)
    gi_b_pat = "|".join(GI_BROAD)
    reac["is_gi_severe"] = reac["pt_upper"].str.contains(gi_pat,   regex=True, na=False)
    reac["is_gi_broad"]  = reac["pt_upper"].str.contains(gi_b_pat, regex=True, na=False)
    reac["gi_term"]      = reac.loc[reac["is_gi_severe"], "pt"].fillna("")

    gi_pids_severe = set(reac.loc[reac["is_gi_severe"], "primaryid"])

    # ── Filter OUTC — worst outcome per patient ────────────────────────────
    outc_order = {"DE": 0, "LT": 1, "HO": 2, "DS": 3, "CA": 4, "RI": 5, "OT": 6}
    outc["outc_rank"] = outc["outc_cod"].map(outc_order).fillna(7)
    worst_outc = (outc.sort_values("outc_rank")
                      .drop_duplicates(subset="primaryid", keep="first")
                      [["primaryid", "outc_cod"]])
    worst_outc["severity_label"] = worst_outc["outc_cod"].map(OUTC_SEVERITY)
    worst_outc["severity_flag"]  = worst_outc["outc_cod"].isin(SERIOUS_CODES).astype(int)

    # ── THER: compute time-to-onset ────────────────────────────────────────
    # Parse therapy start date robustly (accept YYYYMMDD numeric or text)
    ther["start_dt_parsed"] = pd.to_datetime(ther["start_dt"].astype(str).str.replace(r'\.0+$','', regex=True),
                                              format="%Y%m%d", errors="coerce")
    time_onset = ther.groupby("primaryid")["start_dt_parsed"].min().reset_index()
    time_onset.columns = ["primaryid", "drug_start_date"]

    # ── Build cohort DEMO slice ────────────────────────────────────────────
    cohort_demo = demo[demo["primaryid"].isin(all_pids)].copy()
    cohort_demo["age_num"] = pd.to_numeric(cohort_demo["age"], errors="coerce")
    # Standardise age to years
    age_factor = {"YR": 1, "MON": 1/12, "WK": 1/52, "DY": 1/365, "DEC": 10, "HR": 1/8760}
    cohort_demo["age_yr"] = cohort_demo.apply(
        lambda r: r["age_num"] * age_factor.get(str(r.get("age_cod","YR")).strip().upper(), 1)
                  if pd.notna(r["age_num"]) else np.nan, axis=1
    )
    # Weight: standardise to kg
    cohort_demo["wt_num"] = pd.to_numeric(cohort_demo["wt"], errors="coerce")
    cohort_demo["wt_kg"]  = cohort_demo.apply(
        lambda r: r["wt_num"] * 0.453592 if str(r.get("wt_cod","")).upper() == "LBS"
                  else r["wt_num"], axis=1
    )
    cohort_demo["sex_clean"] = cohort_demo["sex"].map(
        {"F": "Female", "M": "Male", "UNK": "Unknown"}).fillna("Unknown")
    # Parse event date robustly
    cohort_demo["event_date"] = pd.to_datetime(cohort_demo["event_dt"].astype(str).str.replace(r'\.0+$','', regex=True),
                                                  format="%Y%m%d", errors="coerce")

    # Clip implausible weights to NaN (will be median-imputed later)
    cohort_demo["wt_kg"] = cohort_demo["wt_kg"].where(cohort_demo["wt_kg"].between(30, 300), np.nan)

    # ── Assemble fact rows ─────────────────────────────────────────────────
    fact = cohort_demo[["primaryid", "caseid", "age_yr", "wt_kg", "sex_clean",
                         "event_date", "fda_dt", "reporter_country", "occr_country"]].copy()
    fact["quarter"] = quarter

    # Cohort label
    fact["cohort"] = "other"
    fact.loc[fact["primaryid"].isin(glp1_pids),    "cohort"] = "glp1"
    fact.loc[fact["primaryid"].isin(control_pids), "cohort"] = "control"

    # GI severe flag
    fact["gi_severe_flag"]   = fact["primaryid"].isin(gi_pids_severe).astype(int)

    # Concurrent opioid
    fact["concurrent_opioid"] = fact["primaryid"].isin(opioid_pids).astype(int)

    # Merge polypharmacy
    fact = fact.merge(poly, on="primaryid", how="left")

    # Merge primary GLP-1 drug
    fact = fact.merge(primary_drug, on="primaryid", how="left")
    fact["glp1_drug"] = fact["glp1_drug"].fillna("CONTROL/OTHER")

    # Merge outcomes
    fact = fact.merge(worst_outc[["primaryid","outc_cod","severity_label","severity_flag"]],
                      on="primaryid", how="left")
    fact["outc_cod"]       = fact["outc_cod"].fillna("OT")
    fact["severity_label"] = fact["severity_label"].fillna("Other")
    fact["severity_flag"]  = fact["severity_flag"].fillna(0).astype(int)

    # Merge therapy start date for time-to-onset computation later
    fact = fact.merge(time_onset, on="primaryid", how="left")
    # Compute time_to_onset in days using real datetime difference when available
    fact["time_to_onset_days"] = (fact["event_date"] - fact["drug_start_date"]).dt.days
    # If any remaining invalid or extreme values, set to NaN
    fact.loc[(fact["time_to_onset_days"] < -3650) | (fact["time_to_onset_days"] > 3650), "time_to_onset_days"] = np.nan

    # GI reaction term (primary term if multiple)
    gi_term_map = (reac[reac["is_gi_severe"]]
                   .drop_duplicates(subset="primaryid", keep="first")
                   [["primaryid", "pt"]]
                   .rename(columns={"pt": "gi_reaction_term"}))
    fact = fact.merge(gi_term_map, on="primaryid", how="left")
    fact["gi_reaction_term"] = fact["gi_reaction_term"].fillna("None")

    return {"fact": fact, "drug": drug[drug["primaryid"].isin(all_pids)],
            "reac": reac[reac["primaryid"].isin(all_pids)]}


def _yyyymmdd_diff_days(diff_val: float) -> float:
    """Very rough conversion of YYYYMMDD-format date difference to approximate days."""
    try:
        diff = int(abs(diff_val))
        years = diff // 10000
        months = (diff % 10000) // 100
        days = diff % 100
        return years * 365 + months * 30 + days
    except Exception:
        return np.nan


def run_etl() -> pd.DataFrame:
    """Run full ETL across all 13 quarters and return combined fact table."""
    zips = list_quarter_zips()
    all_facts = []
    all_drugs = []
    all_reacs = []

    for zpath in zips:
        result = process_quarter(zpath)
        if result:
            all_facts.append(result["fact"])
            all_drugs.append(result["drug"])
            all_reacs.append(result["reac"])

    fact_df = pd.concat(all_facts, ignore_index=True)
    drug_df = pd.concat(all_drugs, ignore_index=True)
    reac_df = pd.concat(all_reacs, ignore_index=True)

    # ── Global deduplication: keep latest caseid across all quarters ────────
    log.info("Global deduplication across quarters ...")
    before = len(fact_df)
    fact_df["fda_dt_n"] = pd.to_numeric(fact_df["fda_dt"], errors="coerce")
    fact_df = (fact_df.sort_values(["caseid", "fda_dt_n"], ascending=[True, False])
                      .drop_duplicates(subset="caseid", keep="first")
                      .reset_index(drop=True))
    log.info(f"  Deduplication: {before:,} → {len(fact_df):,} rows ({before-len(fact_df):,} removed)")

    # ── Imputation: age and weight, grouped by sex and cohort ───────────────
    log.info("Median imputation for age and weight ...")
    for col in ["age_yr", "wt_kg"]:
        fact_df[col] = fact_df.groupby(["sex_clean", "cohort"])[col].transform(
            lambda x: x.fillna(x.median())
        )
        # Fallback: global median
        fact_df[col] = fact_df[col].fillna(fact_df[col].median())

    # ── Save processed outputs ──────────────────────────────────────────────
    fact_df.to_csv(DATA_DIR / "fact_adverse_event.csv", index=False)
    drug_df.to_csv(DATA_DIR / "drug_records.csv", index=False)
    reac_df.to_csv(DATA_DIR / "reaction_records.csv", index=False)

    log.info(f"Saved fact table: {len(fact_df):,} unique cases")
    log.info(f"  GLP-1 cohort:    {(fact_df['cohort']=='glp1').sum():,}")
    log.info(f"  Control cohort:  {(fact_df['cohort']=='control').sum():,}")
    log.info(f"  GI severe events:{fact_df['gi_severe_flag'].sum():,}")
    log.info(f"  Severity=1:      {fact_df['severity_flag'].sum():,}")

    return fact_df


if __name__ == "__main__":
    fact = run_etl()
    print("\nETL complete.")
    print(fact.describe(include="all").to_string())
