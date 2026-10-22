FROM --platform=linux/amd64 python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JUPYTER_PORT=8888 \
    AMR_DATA_DIR=/data \
    AMR_OUTPUT_DIR=/outputs

# All packages are baked into the image because the TRE has no internet.
RUN pip install --no-cache-dir \
      duckdb \
      numpy \
      pandas \
      matplotlib \
      jupyterlab

WORKDIR /app
COPY AMR_HUB_BC_Triage.ipynb /app/AMR_HUB_BC_Triage.ipynb
COPY generate_progress_report.py /app/generate_progress_report.py
COPY run_progress_report.sh /app/run_progress_report.sh
COPY start_jupyter.sh /app/start_jupyter.sh
RUN chmod +x /app/start_jupyter.sh /app/generate_progress_report.py /app/run_progress_report.sh

VOLUME ["/data", "/outputs"]
EXPOSE 8888

ENTRYPOINT ["/app/start_jupyter.sh"]
