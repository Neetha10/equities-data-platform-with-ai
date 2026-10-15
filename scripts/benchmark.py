#!/usr/bin/env python3
"""Run comparable PostgreSQL, DuckDB, and custom-engine measurements."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
from pathlib import Path
from statistics import median, quantiles
from time import perf_counter_ns

from engine.benchmarks import sector_performance
from engine.loader import load_hot_window
from market_brief.db import connection, query


def _time(callback, repetitions: int) -> list[float]:
    timings: list[float] = []
    for _ in range(repetitions):
        start = perf_counter_ns()
        callback()
        timings.append((perf_counter_ns() - start) / 1_000_000)
    return timings


def _postgres_callback(conn, sql: str, params: tuple):
    def run() -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    return run


def _materialize_duckdb_table(duck, name: str, rows: list[dict], pandas) -> None:
    """Load typed columns once; benchmark queries, not Python object conversion."""
    frame = pandas.DataFrame(rows)
    for column in ("open", "high", "low", "close", "vwap"):
        if column in frame:
            frame[column] = pandas.to_numeric(frame[column], errors="raise").astype("float64")
    if "volume" in frame:
        frame["volume"] = pandas.to_numeric(frame["volume"], errors="raise").astype("int64")
    staging_name = f"_{name}_input"
    duck.register(staging_name, frame)
    duck.execute(f"CREATE TABLE {name} AS SELECT * FROM {staging_name}")
    duck.unregister(staging_name)


def _write(raw: list[dict], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "raw_samples.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["system", "case", "iteration", "milliseconds"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(raw)
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in raw:
        grouped.setdefault((row["system"], row["case"]), []).append(row["milliseconds"])
    lines = ["# Benchmark results", "", "Generated from the raw samples beside this file.", "", "| System | Case | Median ms | p95 ms |", "| --- | --- | ---: | ---: |"]
    for (system, case), values in sorted(grouped.items()):
        p95 = quantiles(values, n=100, method="inclusive")[94] if len(values) > 1 else values[0]
        lines.append(f"| {system} | {case} | {median(values):.3f} | {p95:.3f} |")
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the same snapshot across three engines")
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results"))
    args = parser.parse_args()
    if args.repetitions < 2:
        raise ValueError("use at least two repetitions to calculate a p95")
    try:
        import duckdb
        import pandas as pd
    except ImportError as exc:
        raise SystemExit("Install benchmark dependencies with: pip install -e '.[benchmark]'") from exc

    start = args.as_of - timedelta(days=30)
    daily_sql = """SELECT symbol, close FROM daily_bars
                   WHERE symbol = %s AND trading_date >= %s AND trading_date <= %s
                   ORDER BY trading_date DESC LIMIT 30"""
    minute_sql = """SELECT symbol, close FROM minute_bars
                    WHERE symbol = %s AND ts >= %s::date AND ts < (%s::date + INTERVAL '1 day')
                    ORDER BY ts DESC LIMIT 390"""
    sector_sql = """WITH prices AS (
                      SELECT d.symbol, d.trading_date, d.close,
                             lag(d.close) OVER (PARTITION BY d.symbol ORDER BY d.trading_date) AS prior_close
                      FROM daily_bars d WHERE d.trading_date <= %s
                    )
                    SELECT c.sector, count(*) AS constituents,
                           avg(100 * (p.close / p.prior_close - 1)) AS return_pct
                    FROM prices p JOIN companies c USING (symbol)
                    WHERE p.trading_date = %s AND p.prior_close IS NOT NULL GROUP BY c.sector"""
    engine = load_hot_window(args.as_of)
    duck = duckdb.connect(":memory:")
    _materialize_duckdb_table(
        duck,
        "daily_bars",
        query("SELECT * FROM daily_bars WHERE trading_date <= %s", (args.as_of,)),
        pd,
    )
    _materialize_duckdb_table(
        duck,
        "minute_bars",
        query("SELECT * FROM minute_bars WHERE ts < (%s::date + INTERVAL '1 day')", (args.as_of,)),
        pd,
    )
    _materialize_duckdb_table(duck, "companies", query("SELECT symbol, sector FROM companies"), pd)
    cases = [
        ("daily_range", daily_sql, (args.symbol, start, args.as_of), lambda: engine.execute(f"SELECT symbol, close FROM daily_bars WHERE symbol = '{args.symbol}' AND trading_date >= '{start.isoformat()}' ORDER BY trading_date DESC LIMIT 30").rows),
        ("minute_range", minute_sql, (args.symbol, args.as_of, args.as_of), lambda: engine.execute(f"SELECT symbol, close FROM minute_bars WHERE symbol = '{args.symbol}' AND ts >= '{args.as_of.isoformat()}' ORDER BY ts DESC LIMIT 390").rows),
        ("sector_group", sector_sql, (args.as_of, args.as_of), lambda: sector_performance(engine, args.as_of)),
    ]
    raw: list[dict] = []
    with connection() as postgres_conn:
        for case, sql, params, custom in cases:
            postgres = _postgres_callback(postgres_conn, sql, params)
            duck_sql = sql.replace("%s", "?").replace("::date", "")
            duck_callback = lambda sql=duck_sql, params=params: duck.execute(sql, params).fetchall()
            # One warmup per implementation; connection and data loading are excluded from timings.
            for callback in (postgres, duck_callback, custom):
                callback()
            for system, callback in (("postgres", postgres), ("duckdb", duck_callback), ("custom_engine", custom)):
                for iteration, milliseconds in enumerate(_time(callback, args.repetitions), start=1):
                    raw.append({"system": system, "case": case, "iteration": iteration, "milliseconds": milliseconds})
    _write(raw, args.output)
    print(f"wrote {args.output / 'summary.md'} and raw_samples.csv")


if __name__ == "__main__":
    main()
