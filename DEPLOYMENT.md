Deployment Guide — Streamlit Dashboard

This guide explains how to run the interactive Streamlit dashboard locally, and how to containerize it with Docker for deployment.

Local run (development)
1) Create and activate a virtual environment (macOS / zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2) Start the Streamlit dashboard (from project root):

```bash
streamlit run 04_dashboard_streamlit.py
```

The app will open at http://localhost:8501 by default.

Docker (recommended for reproducible deployment)
1) Build the Docker image (from project root):

```bash
docker build -t glp1-faers-dashboard:latest .
```

2) Run the container, mounting local data or pointing to a data volume (example):

```bash
docker run -p 8501:8501 \
  -v $(pwd)/data/processed:/app/data/processed:ro \
  -v $(pwd)/reports:/app/reports:ro \
  glp1-faers-dashboard:latest
```

This will expose the Streamlit app at http://localhost:8501.

Notes
- Ensure that `data/processed/fact_adverse_event.csv` and `models/random_forest.pkl` exist and are readable inside the container.
- For cloud deployment (e.g., Cloud Run, App Service), follow provider-specific guidance for container images and persistent volumes.
