FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip install --no-cache-dir dxf2geo
RUN pip install --no-cache-dir pyyaml

COPY run_conversion.py /app/run_conversion.py
COPY run_process.sh    /usr/local/bin/run_process.sh
RUN chmod +x /usr/local/bin/run_process.sh

RUN useradd -m -u 10001 appuser
USER appuser

WORKDIR /work
ENTRYPOINT ["/usr/bin/tini","--","/usr/local/bin/run_process.sh"]
