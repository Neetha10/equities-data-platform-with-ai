"""Desk-query implementation over columnar tables; no SQL engine is involved here."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from .core import ColumnarTable, Engine


def _round(value: Decimal | float | None, places: str = "0.01") -> Decimal | None:
    return Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP) if value is not None else None


def _daily_by_symbol(engine: Engine) -> dict[str, list[dict]]:
    table = engine.tables["daily_bars"]
    result: dict[str, list[dict]] = defaultdict(list)
    for row_id in range(table.row_count):
        row = table.row(row_id)
        result[str(row["symbol"])].append(row)
    for rows in result.values():
        rows.sort(key=lambda row: row["trading_date"])
    return result


def _returns(by_symbol: dict[str, list[dict]], as_of: date) -> tuple[list[dict], dict[tuple[str, date], Decimal]]:
    result: list[dict] = []
    values: dict[tuple[str, date], Decimal] = {}
    for symbol, rows in by_symbol.items():
        for previous, current in pairwise(rows):
            if current["trading_date"] == as_of and previous["close"]:
                value = Decimal(100) * (current["close"] / previous["close"] - 1)
                values[(symbol, as_of)] = value
                result.append({"symbol": symbol, "close": _round(current["close"]), "return_pct": _round(value)})
    return sorted(result, key=lambda row: (row["return_pct"], row["symbol"]), reverse=True), values


def run_desk_queries(engine: Engine, as_of: date) -> dict[str, list[dict]]:
    """Return the same named result sets as the seven Phase 1 SQL files."""
    by_symbol = _daily_by_symbol(engine)
    returns, return_values = _returns(by_symbol, as_of)

    gainers = [{"direction": "gainer", **row} for row in returns[:5]]
    losers = [{"direction": "loser", **row} for row in sorted(returns, key=lambda row: (row["return_pct"], row["symbol"]))[:5]]

    spikes: list[dict] = []
    gaps: list[dict] = []
    extremes: list[dict] = []
    for symbol, rows in by_symbol.items():
        for position, current in enumerate(rows):
            if current["trading_date"] != as_of:
                continue
            history = rows[max(0, position - 20) : position]
            if history:
                average = sum(row["volume"] for row in history) / len(history)
                spikes.append(
                    {
                        "symbol": symbol,
                        "volume": current["volume"],
                        "avg_20d_volume": _round(average, "1"),
                        "volume_multiple": _round(current["volume"] / average),
                    }
                )
            if position:
                prior = rows[position - 1]["close"]
                gaps.append(
                    {
                        "symbol": symbol,
                        "open": _round(current["open"]),
                        "prior_close": _round(prior),
                        "gap_pct": _round(Decimal(100) * (current["open"] / prior - 1)),
                    }
                )
            high_window = rows[max(0, position - 251) : position + 1]
            if high_window:
                high, low = max(row["close"] for row in high_window), min(row["close"] for row in high_window)
                if current["close"] in {high, low}:
                    extremes.append(
                        {
                            "symbol": symbol,
                            "close": _round(current["close"]),
                            "high_52w": _round(high),
                            "low_52w": _round(low),
                            "extreme": "52w_high" if current["close"] == high else "52w_low",
                        }
                    )

    minute_table = engine.tables["minute_bars"]
    minute_stats: dict[str, dict[str, Decimal | int]] = defaultdict(lambda: {"weighted": Decimal(0), "volume": 0, "min": None, "max": None})
    for row_id in range(minute_table.row_count):
        row = minute_table.row(row_id)
        if row["ts"].date() != as_of or not row["volume"]:
            continue
        entry = minute_stats[str(row["symbol"])]
        price = row["vwap"] or row["close"]
        entry["weighted"] += price * row["volume"]  # type: ignore[operator]
        entry["volume"] += row["volume"]  # type: ignore[operator]
        entry["min"] = row["close"] if entry["min"] is None else min(entry["min"], row["close"])
        entry["max"] = row["close"] if entry["max"] is None else max(entry["max"], row["close"])
    vwaps = [
        {
            "symbol": symbol,
            "session_vwap": _round(item["weighted"] / item["volume"]),  # type: ignore[operator]
            "intraday_close_range": _round(item["max"] - item["min"]),  # type: ignore[operator]
            "minute_volume": item["volume"],
        }
        for symbol, item in minute_stats.items()
    ]

    # Exercise the engine's Week 4 hash join + group-by path for sector returns.
    return_table = ColumnarTable.from_rows(
        "daily_returns",
        [{"symbol": symbol, "return_pct": value} for (symbol, trading_date), value in return_values.items() if trading_date == as_of],
    )
    engine.register(return_table)
    joined = engine.hash_join("daily_returns", "companies", "symbol", "symbol", (("sector", "right.sector"), ("return_pct", "left.return_pct")))
    sectors = Engine.group_by(joined, ("sector",), {"constituents": ("count", None), "raw_return": ("avg", "return_pct")})
    sector_rows = [
        {"sector": row["sector"], "constituents": row["constituents"], "equal_weight_return_pct": _round(row["raw_return"])}
        for row in sectors
    ]
    return {
        "01_returns": returns,
        "02_gainers_losers": sorted(gainers + losers, key=lambda row: (row["direction"], -row["return_pct"])),
        "03_volume_spikes": sorted(spikes, key=lambda row: (-row["volume_multiple"], row["symbol"]))[:10],
        "04_vwap": sorted(vwaps, key=lambda row: (-row["minute_volume"], row["symbol"]))[:10],
        "05_sector_performance": sorted(sector_rows, key=lambda row: (-row["equal_weight_return_pct"], row["sector"])),
        "06_gaps": sorted(gaps, key=lambda row: (-abs(row["gap_pct"]), row["symbol"]))[:10],
        "07_52_week_extremes": sorted(extremes, key=lambda row: (row["extreme"], row["symbol"])),
    }
