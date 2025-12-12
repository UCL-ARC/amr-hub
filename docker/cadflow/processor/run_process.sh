#!/usr/bin/env bash
set -euo pipefail
DXF_DIR="${DXF_DIR:-/work}"
OUT_DIR="${OUT_DIR:-/out}"
CONF_DIR="${CONF_DIR:-/config}"
FORMAT="${FORMAT:-geopackage}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
mkdir -p "$OUT_DIR"

# Wait for at least one DXF
echo "Waiting for DXFs in $DXF_DIR ..."
for i in $(seq 1 600); do  # up to ~10 minutes
  if compgen -G "$DXF_DIR/*.dxf" > /dev/null; then
    break
  fi
  sleep 1
done

# If still none, fail clearly
if ! compgen -G "$DXF_DIR/*.dxf" > /dev/null; then
  echo "No DXFs found in $DXF_DIR after waiting; aborting." >&2
  exit 2
fi

python /app/run_conversion.py --input "$DXF_DIR" --output "$OUT_DIR" --config-dir "$CONF_DIR"
echo "DXF → ${FORMAT} complete: $OUT_DIR"
