#!/bin/sh
# Run a Python file inside the ClearRail lab image.
#   ./run.sh check.py
#   ./run.sh some_step.py data/uc1_supplier_payments/PAY-202611001
cd "$(dirname "$0")" || exit 1
[ -f .env ] || cp .env.example .env
docker build -q -t clearrail:lab . >/dev/null || { echo "Docker build failed: is Docker Desktop running?"; exit 1; }
exec docker run --rm --env-file .env -v "$PWD:/app" -w /app -e PYTHONPATH=/app clearrail:lab python "$@"
