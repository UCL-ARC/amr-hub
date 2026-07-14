# AMR-HUB BC learnability analysis — built OUTSIDE the TRE, run inside (no internet there).
# Build (on Apple Silicon Macs the --platform flag is REQUIRED for the TRE's x86 VMs):
#   docker build --platform linux/amd64 -t amr-bc-analysis .
#   docker save -o amr-bc-analysis.tar amr-bc-analysis
# Then upload amr-bc-analysis.tar through the airlock.

FROM --platform=linux/amd64 python:3.12-slim

# All dependencies baked in at build time (no pip inside the TRE).
# jax/flax/optax deliberately excluded for v1: keeps the tar small; the
# count-based rule-out is the primary result and needs neither.
RUN pip install --no-cache-dir duckdb numpy

WORKDIR /app
COPY bc_prototype.py /app/bc_prototype.py
COPY run_analysis.sh /app/run_analysis.sh
RUN chmod +x /app/run_analysis.sh

# Conventions (mounted at run time):
#   /data     -> folder containing the .db file (read-only mount)
#   /outputs  -> folder where logs + CSVs land (these are the egress files)
ENTRYPOINT ["/app/run_analysis.sh"]
