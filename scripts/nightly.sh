#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs
PYTHONPATH=. .venv/bin/python -m market_brief.cli run-all >> "logs/nightly.log" 2>&1
