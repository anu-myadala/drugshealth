# Dockerfile for Streamlit dashboard (lightweight)
FROM python:3.11-slim

WORKDIR /app

# Copy only essentials
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8501

ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501

CMD ["streamlit", "run", "04_dashboard_streamlit.py", "--server.port", "8501", "--server.headless", "true"]
