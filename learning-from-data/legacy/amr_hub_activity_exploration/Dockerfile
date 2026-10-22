# Reconstructed from the build history of the amr-activity-exploration:latest image.
FROM python:3.11-slim
RUN pip install --no-cache-dir \
    duckdb==1.4.0 \
    pandas==2.3.1 \
    numpy==2.2.6 \
    matplotlib==3.10.3
WORKDIR /app
COPY generate_activity_exploration.py /app/generate_activity_exploration.py
COPY run_activity_exploration.sh /app/run_activity_exploration.sh
RUN chmod +x /app/run_activity_exploration.sh
ENTRYPOINT ["/app/run_activity_exploration.sh"]
