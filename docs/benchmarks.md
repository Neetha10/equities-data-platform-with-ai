# Benchmarks

The benchmark harness runs the same market-data snapshot against PostgreSQL, DuckDB, and the custom engine. It measures three workloads: a daily `(symbol, date)` range scan, a minute-bar range scan, and sector performance (return calculation, hash join, and group-by).

```bash
.venv/bin/pip install -e '.[benchmark]'
AS_OF=2026-10-15 make benchmark
```

It does one untimed warmup and 20 timed iterations by default; pass `--repetitions 100` for the published results. Loading data is deliberately excluded from the timed section. Results are written to `benchmarks/results/raw_samples.csv` and `benchmarks/results/summary.md`; the latter reports median and inclusive p95. Keep both artifacts with the exact machine, Python, PostgreSQL, DuckDB, OS, data row counts, and command used.

For a fair execution-time comparison, the harness opens one PostgreSQL connection before timing and reuses it across iterations. It converts Decimal price columns to typed numeric columns and materializes DuckDB tables before warmup. The custom engine's hot window is also loaded before timing. Connection setup and data loading are therefore intentionally outside the reported query timings.

Interpretation guidance:

- PostgreSQL is the durable system of record and should be expected to win when concurrent writes, reliability, and query breadth matter.
- DuckDB is a vectorized analytical baseline, not an operational database comparison.
- The custom engine is a constrained learning implementation. It should only be credited where saved measurements show it wins; its snapshot load cost and limited SQL grammar are real costs.
