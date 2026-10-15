"""Narrow, comparable engine workloads used by the benchmark harness."""

from __future__ import annotations

from datetime import date

from .core import ColumnarTable, Engine
from .desk import _daily_by_symbol, _returns


def sector_performance(engine: Engine, as_of: date) -> list[dict]:
    """Hash-join daily returns to sector reference and group by sector."""
    _, returns = _returns(_daily_by_symbol(engine), as_of)
    engine.register(
        ColumnarTable.from_rows(
            "benchmark_returns",
            [
                {"symbol": symbol, "return_pct": value}
                for (symbol, trading_date), value in returns.items()
                if trading_date == as_of
            ],
        )
    )
    joined = engine.hash_join(
        "benchmark_returns",
        "companies",
        "symbol",
        "symbol",
        (("sector", "right.sector"), ("return_pct", "left.return_pct")),
    )
    return Engine.group_by(joined, ("sector",), {"constituents": ("count", None), "return_pct": ("avg", "return_pct")})
