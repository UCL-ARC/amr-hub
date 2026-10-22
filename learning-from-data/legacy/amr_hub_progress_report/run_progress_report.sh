#!/bin/sh
set -u
exec python /app/generate_progress_report.py "$@"
