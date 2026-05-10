# GLP-1 FAERS — Reproducible Pipeline

This repository contains an end-to-end pipeline to analyze FDA FAERS adverse event data for GLP-1 receptor agonists.

## Submission Files

- Final presentation: `reports/GLP1_CMPE255_Final_Main_Anu.pptx`
- HTML demo dashboard: `demo/GLP1_FAERS_Risk_Simulator.html`
- Combined result summary: `reports/PROJECT_FULL_SUMMARY.md` and `reports/PROJECT_FULL_SUMMARY.pdf`
- Methods and validation: `reports/METHODS_VALIDATION.md` and `reports/METHODS_VALIDATION.pdf`
- Latest numeric results: `reports/RESULTS_LATEST.md`
- Generated visuals: `reports/figures/*.png`

The raw FAERS ZIP files and processed CSV/model outputs are intentionally not
committed because they are large and can be regenerated from the scripts.

Quick start (macOS / zsh):

1. Install Python dependencies (prefer a venv):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Point the ETL to your FAERS ZIP files. You can either place them in a folder and set FAERS_DIR, or provide an explicit ordered list in FAERS_ZIP_LIST.

Example (zsh):

```bash
export FAERS_ZIP_LIST="/Users/anumyad/Downloads/faers_ascii_2023q1.zip:/Users/anumyad/Downloads/faers_ascii_2023q2.zip:/Users/anumyad/Downloads/faers_ascii_2023q3.zip"
./run_full_pipeline.sh
```

3. Outputs:

- Processed CSVs: `data/processed/fact_adverse_event.csv`, `drug_records.csv`, `reaction_records.csv`
- Figures: `reports/figures/*.png`
- EDA & mining JSON summaries: `reports/eda_results.json`, `reports/mining_results.json`, `reports/extended_mining_results.json`
- Model comparison table: `reports/extended_model_comparison.csv` and `reports/figures/extended_model_comparison_table.png`
- HTML demo dashboard: `demo/GLP1_FAERS_Risk_Simulator.html`
- Presentation and summary PDFs under `reports/`

Notes:
- The pipeline is designed to run on the full FAERS quarterly ZIPs you provide — these can be large. Ensure you have sufficient disk space.
- If you want me to run the pipeline here, upload the FAERS zip files into the workspace or set `FAERS_ZIP_LIST` accordingly and ask me to execute the pipeline.
