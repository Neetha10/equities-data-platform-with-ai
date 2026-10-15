.PHONY: up down install test lint backfill nightly brief benchmark

up:
	docker compose up -d

down:
	docker compose down

install:
	python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'

test:
	PYTHONPATH=. .venv/bin/pytest -q

lint:
	.venv/bin/ruff check .

backfill:
	PYTHONPATH=. .venv/bin/python -m market_brief.cli backfill

nightly:
	PYTHONPATH=. .venv/bin/python -m market_brief.cli run-all

benchmark:
	PYTHONPATH=. .venv/bin/python scripts/benchmark.py --as-of $${AS_OF:?Set AS_OF=YYYY-MM-DD}
