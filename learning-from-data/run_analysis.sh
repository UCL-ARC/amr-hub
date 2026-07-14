#!/bin/bash
# Runs the full learnability sequence against the mounted DuckDB file and
# writes every artefact intended for egress into /outputs.
# Usage inside the TRE:
#   docker run --rm -v /path/to/dbdir:/data:ro -v /path/to/out:/outputs \
#       amr-bc-analysis [db-filename]
# If db-filename is omitted, the first *.db / *.duckdb file in /data is used.

set -uo pipefail  # NOT -e: one failing stage should not kill the rest

DB="${1:-}"
if [ -z "$DB" ]; then
    DB=$(ls /data/*.db /data/*.duckdb 2>/dev/null | head -1)
fi
if [ -z "$DB" ] || [ ! -f "${DB/#\//}" ] && [ ! -f "$DB" ]; then
    # allow bare filename relative to /data
    [ -f "/data/$DB" ] && DB="/data/$DB"
fi
if [ -z "$DB" ] || [ ! -f "$DB" ]; then
    echo "ERROR: no database found. Mount its folder at /data (found: $(ls /data 2>/dev/null))"
    exit 1
fi

mkdir -p /outputs
cd /outputs
echo "== AMR-HUB BC analysis ==" | tee run_summary.log
echo "db: $DB"                    | tee -a run_summary.log
date -u                           | tee -a run_summary.log
python -c "import duckdb, numpy, sys; print('python', sys.version.split()[0], '| duckdb', duckdb.__version__, '| numpy', numpy.__version__)" | tee -a run_summary.log

run_stage () {  # run_stage <logname> <args...>
    local log="$1"; shift
    echo "--- $log : python bc_prototype.py $* ---" | tee -a run_summary.log
    if python /app/bc_prototype.py "$@" > "$log" 2>&1; then
        echo "OK  $log" | tee -a run_summary.log
    else
        echo "FAIL $log (see file for traceback)" | tee -a run_summary.log
    fi
}

# 1. Workstation placement (produces ws_crosswalk.csv used by all later stages)
run_stage infer_ws.log        --db "$DB" infer-ws --out /outputs/ws_crosswalk.csv
XW=""
[ -s /outputs/ws_crosswalk.csv ] && XW="--crosswalk /outputs/ws_crosswalk.csv"

# 2-4. Movement question (next location)
run_stage battery.log         --db "$DB" battery $XW
run_stage ruleout.log         --db "$DB" ruleout $XW
run_stage sweep.log           --db "$DB" sweep   $XW

# 5-6. Activity question (next class) — the fallback axis if movement rules out
run_stage battery_class.log   --db "$DB" battery $XW --action next_class
run_stage ruleout_class.log   --db "$DB" ruleout $XW --action next_class

echo "== done ==" | tee -a run_summary.log
ls -l /outputs | tee -a run_summary.log
echo "Egress set: run_summary.log, infer_ws.log, battery*.log, ruleout*.log, sweep.log, ws_crosswalk.csv"
