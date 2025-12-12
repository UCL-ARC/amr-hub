#!/usr/bin/env bash
set -euxo pipefail

IN_DIR="${IN_DIR:-/in}"
DXF_DIR="${DXF_DIR:-/work}"
mkdir -p "$DXF_DIR"

# Fresh, correct permissions for Qt runtime dir
export XDG_RUNTIME_DIR=/tmp/runtime-qt
rm -rf "$XDG_RUNTIME_DIR"
mkdir -m 700 -p "$XDG_RUNTIME_DIR"

# Converter binary (ODA provides both names in some builds)
ODA_BIN="$(command -v oda-file-converter || true)"
if [ -z "$ODA_BIN" ]; then ODA_BIN="$(command -v TeighaFileConverter || true)"; fi
if [ -z "$ODA_BIN" ]; then echo "ODA converter not found" >&2; exit 127; fi

# List inputs
mapfile -t FILES < <(find "$IN_DIR" -maxdepth 1 -type f \( -name '*.dwg' -o -name '*.DWG' \) -printf '%f\n' | sort)
if [ ${#FILES[@]} -eq 0 ]; then
  echo "No DWG files found in ${IN_DIR}" >&2
  exit 2
fi
printf ' - %s\n' "${FILES[@]}"

# Use xvfb-run to manage X server + cookie (avoids xauth errors and Xvfb races)
for fname in "${FILES[@]}"; do
  echo "[$(date -Is)] Converting: ${fname}"
  timeout 900s xvfb-run -a -s "-screen 0 1024x768x24 -nolisten tcp" \
    "$ODA_BIN" "$IN_DIR" "$DXF_DIR" "ACAD2013" "DXF" 0 0

  base="${fname%.*}"
  compgen -G "$DXF_DIR/${base}".[dD][xX][fF] >/dev/null && ls -al "$DXF_DIR"/${base}.[dD][xX][fF] || echo "WARNING: No DXF for ${fname}"
done

echo "Done. Outputs in $DXF_DIR"
