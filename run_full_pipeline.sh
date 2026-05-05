#!/bin/zsh
# Run the full ETL → EDA → Data Mining pipeline
set -euo pipefail
BASEDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BASEDIR"

# If you want to point the ETL to specific FAERS zip files, set FAERS_ZIP_LIST env var:
# export FAERS_ZIP_LIST="/Users/you/Downloads/faers_ascii_2023q1.zip:/Users/you/Downloads/faers_ascii_2023q2.zip"

python3 01_etl.py
python3 02_eda_stats.py
python3 03_data_mining.py

echo "Pipeline complete. Outputs in reports/"