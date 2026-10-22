#!/bin/sh
set -eu

mkdir -p /outputs

# Working copy lives on /outputs so edits persist; an existing copy is kept.
NOTEBOOK=/outputs/AMR_HUB_BC_Triage.ipynb
if [ ! -f "$NOTEBOOK" ]; then
    cp /app/AMR_HUB_BC_Triage.ipynb "$NOTEBOOK"
fi

PORT="${JUPYTER_PORT:-8888}"
TOKEN="${JUPYTER_TOKEN:-}"

echo "Starting JupyterLab"
echo "  notebook: $NOTEBOOK"
echo "  data:     /data (mount read-only)"
echo "  outputs:  /outputs"
if [ -z "$TOKEN" ]; then
    echo "  auth:     token disabled; bind/publish the port only within the TRE"
else
    echo "  auth:     JUPYTER_TOKEN enabled"
fi

exec jupyter lab "$NOTEBOOK" \
    --ip=0.0.0.0 \
    --port="$PORT" \
    --no-browser \
    --allow-root \
    --ServerApp.root_dir=/outputs \
    --ServerApp.open_browser=False \
    --IdentityProvider.token="$TOKEN"
