-- Star schema for GLP-1 FAERS study (Postgres/SQLite compatible)

CREATE TABLE IF NOT EXISTS dim_patient (
    patient_id TEXT PRIMARY KEY,
    caseid TEXT,
    age_yr REAL,
    wt_kg REAL,
    sex_clean TEXT,
    reporter_country TEXT,
    occr_country TEXT
);

CREATE TABLE IF NOT EXISTS dim_time (
    time_id TEXT PRIMARY KEY,
    event_date TEXT,
    fda_dt TEXT,
    quarter TEXT,
    fda_dt_n REAL,
    drug_start_date TEXT
);

CREATE TABLE IF NOT EXISTS dim_outcome (
    outcome_id TEXT PRIMARY KEY,
    outc_cod TEXT,
    severity_label TEXT,
    severity_flag INTEGER,
    gi_severe_flag INTEGER,
    gi_reaction_term TEXT
);

CREATE TABLE IF NOT EXISTS fact_adverse_event (
    fact_id TEXT PRIMARY KEY,
    patient_id TEXT REFERENCES dim_patient(patient_id),
    time_id TEXT REFERENCES dim_time(time_id),
    outcome_id TEXT REFERENCES dim_outcome(outcome_id),
    cohort TEXT,
    concurrent_opioid INTEGER,
    polypharmacy_count INTEGER,
    glp1_drug TEXT,
    time_to_onset_days REAL
);

CREATE TABLE IF NOT EXISTS dim_drug (
    drug_id INTEGER PRIMARY KEY,
    prod_ai_upper TEXT,
    drugname TEXT,
    route TEXT,
    dose_amt TEXT,
    dose_unit TEXT,
    dose_form TEXT,
    dose_freq TEXT,
    is_glp1 INTEGER,
    is_control INTEGER,
    is_opioid INTEGER
);

CREATE TABLE IF NOT EXISTS bridge_drug (
    fact_id TEXT REFERENCES fact_adverse_event(fact_id),
    drug_id INTEGER REFERENCES dim_drug(drug_id)
);

CREATE TABLE IF NOT EXISTS dim_reaction (
    reaction_id INTEGER PRIMARY KEY,
    pt_upper TEXT,
    gi_term TEXT,
    is_gi_severe INTEGER,
    is_gi_broad INTEGER
);

CREATE TABLE IF NOT EXISTS bridge_reaction (
    fact_id TEXT REFERENCES fact_adverse_event(fact_id),
    reaction_id INTEGER REFERENCES dim_reaction(reaction_id)
);
