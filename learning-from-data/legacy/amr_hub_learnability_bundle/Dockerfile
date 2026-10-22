FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir duckdb
COPY generate_learnability_analysis.py /app/generate_learnability_analysis.py

ENTRYPOINT ["python", "/app/generate_learnability_analysis.py"]
