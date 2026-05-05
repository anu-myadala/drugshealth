"""Build star schema tables from processed FAERS outputs.

Usage:
  DB_URL=postgresql+psycopg2://user:pass@host:5432/dbname \
  python 06_star_schema_loader.py

Defaults to a local SQLite database at data/processed/glp1_star.db.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_SQL = PROJECT_ROOT / "schema" / "star_schema.sql"
DEFAULT_DB = f"sqlite:///{PROJECT_ROOT / 'data' / 'processed' / 'glp1_star.db'}"
DB_URL = os.getenv("DB_URL", DEFAULT_DB)


def load_star_schema() -> None:
    engine = create_engine(DB_URL)

    # Create schema tables
    ddl = SCHEMA_SQL.read_text()
    with engine.begin() as conn:
        if DB_URL.startswith("sqlite"):
            conn.connection.executescript(ddl)
        else:
            for stmt in ddl.split(";"):
                if stmt.strip():
                    conn.exec_driver_sql(stmt)

    fact_cols = [
        "primaryid", "caseid", "age_yr", "wt_kg", "sex_clean", "reporter_country", "occr_country",
        "event_date", "fda_dt", "quarter", "fda_dt_n", "drug_start_date",
        "outc_cod", "severity_label", "severity_flag", "gi_severe_flag", "gi_reaction_term",
        "cohort", "concurrent_opioid", "polypharmacy_count", "glp1_drug", "time_to_onset_days",
    ]
    max_rows = int(os.getenv("MAX_ROWS", "0") or 0)
    nrows = max_rows if max_rows > 0 else None

    fact = pd.read_csv(
        DATA_DIR / "fact_adverse_event.csv",
        usecols=fact_cols,
        dtype={"primaryid": str, "caseid": str},
        low_memory=False,
        nrows=nrows,
    )

    drug_cols = [
        "primaryid", "prod_ai_upper", "drugname", "route", "dose_amt", "dose_unit",
        "dose_form", "dose_freq", "is_glp1", "is_control", "is_opioid",
    ]
    drug = pd.read_csv(
        DATA_DIR / "drug_records.csv",
        usecols=drug_cols,
        dtype={"primaryid": str},
        low_memory=False,
        nrows=nrows,
    )

    reaction_cols = ["primaryid", "pt_upper", "gi_term", "is_gi_severe", "is_gi_broad"]
    reaction = pd.read_csv(
        DATA_DIR / "reaction_records.csv",
        usecols=reaction_cols,
        dtype={"primaryid": str},
        low_memory=False,
        nrows=nrows,
    )

    # Dimension: patient
    dim_patient = fact[[
        "primaryid", "caseid", "age_yr", "wt_kg", "sex_clean", "reporter_country", "occr_country"
    ]].drop_duplicates().rename(columns={"primaryid": "patient_id"})

    # Dimension: time
    dim_time = fact[[
        "primaryid", "event_date", "fda_dt", "quarter", "fda_dt_n", "drug_start_date"
    ]].drop_duplicates().rename(columns={"primaryid": "time_id"})

    # Dimension: outcome
    dim_outcome = fact[[
        "primaryid", "outc_cod", "severity_label", "severity_flag", "gi_severe_flag", "gi_reaction_term"
    ]].drop_duplicates().rename(columns={"primaryid": "outcome_id"})

    # Fact table (one row per primaryid)
    fact_table = fact[[
        "primaryid", "cohort", "concurrent_opioid", "polypharmacy_count", "glp1_drug", "time_to_onset_days"
    ]].rename(columns={
        "primaryid": "fact_id",
    })
    fact_table["patient_id"] = fact_table["fact_id"]
    fact_table["time_id"] = fact_table["fact_id"]
    fact_table["outcome_id"] = fact_table["fact_id"]

    # Dimension: drug (unique prod_ai_upper)
    dim_drug = drug[[
        "prod_ai_upper", "drugname", "route", "dose_amt", "dose_unit", "dose_form", "dose_freq",
        "is_glp1", "is_control", "is_opioid"
    ]].drop_duplicates().reset_index(drop=True)
    dim_drug.insert(0, "drug_id", dim_drug.index + 1)

    # Bridge: drug usage
    bridge_drug = drug[["primaryid", "prod_ai_upper"]].merge(
        dim_drug[["drug_id", "prod_ai_upper"]], on="prod_ai_upper", how="left"
    ).rename(columns={"primaryid": "fact_id"})[["fact_id", "drug_id"]].drop_duplicates()

    # Dimension: reaction
    dim_reaction = reaction[["pt_upper", "gi_term", "is_gi_severe", "is_gi_broad"]].drop_duplicates().reset_index(drop=True)
    dim_reaction.insert(0, "reaction_id", dim_reaction.index + 1)

    # Bridge: reaction usage
    bridge_reaction = reaction[["primaryid", "pt_upper"]].merge(
        dim_reaction[["reaction_id", "pt_upper"]], on="pt_upper", how="left"
    ).rename(columns={"primaryid": "fact_id"})[["fact_id", "reaction_id"]].drop_duplicates()

    # Load tables
    dim_patient.to_sql("dim_patient", engine, if_exists="replace", index=False)
    dim_time.to_sql("dim_time", engine, if_exists="replace", index=False)
    dim_outcome.to_sql("dim_outcome", engine, if_exists="replace", index=False)
    fact_table.to_sql("fact_adverse_event", engine, if_exists="replace", index=False)
    dim_drug.to_sql("dim_drug", engine, if_exists="replace", index=False)
    bridge_drug.to_sql("bridge_drug", engine, if_exists="replace", index=False)
    dim_reaction.to_sql("dim_reaction", engine, if_exists="replace", index=False)
    bridge_reaction.to_sql("bridge_reaction", engine, if_exists="replace", index=False)

    print(f"Star schema loaded into {DB_URL}")


if __name__ == "__main__":
    load_star_schema()
