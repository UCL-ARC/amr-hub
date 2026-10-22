# Reconstructed from the build history of the amr-advanced-demo:latest image.
FROM python:3.12-slim
RUN pip install --no-cache-dir duckdb numpy pandas matplotlib
WORKDIR /app
COPY generate_advanced_demo_analysis.py /app/generate_advanced_demo_analysis.py
ENTRYPOINT ["python", "/app/generate_advanced_demo_analysis.py"]
