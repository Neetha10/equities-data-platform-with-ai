from datetime import UTC, date, datetime
from decimal import Decimal

from engine import ColumnarTable, Engine, parse
from engine.desk import run_desk_queries
from engine.index import BPlusTree


def _bars() -> ColumnarTable:
    table = ColumnarTable.from_rows(
        "bars",
        [
            {"symbol": "AAA", "timestamp": datetime(2026, 1, 2, 14, tzinfo=UTC), "close": 10.0, "volume": 20},
            {"symbol": "AAA", "timestamp": datetime(2026, 1, 3, 14, tzinfo=UTC), "close": 11.0, "volume": 30},
            {"symbol": "BBB", "timestamp": datetime(2026, 1, 2, 14, tzinfo=UTC), "close": 5.0, "volume": 40},
        ],
    )
    table.create_btree_index("symbol", "timestamp")
    return table


def test_parser_and_btree_range_plan() -> None:
    engine = Engine()
    engine.register(_bars())
    result = engine.execute(
        "SELECT symbol, close FROM bars WHERE symbol = 'AAA' AND timestamp >= '2026-01-03T00:00:00+00:00' ORDER BY close DESC LIMIT 1"
    )
    assert result.plan.strategy == "full_scan"  # A tiny table is cheaper to scan.
    assert result.rows == [{"symbol": "AAA", "close": 11.0}]
    assert parse("SELECT * FROM bars LIMIT 2").limit == 2


def test_btree_range_and_cost_based_index_choice() -> None:
    tree = BPlusTree([(key, key) for key in range(300)], leaf_size=8, fanout=4)
    assert tree.range() == list(range(300))
    assert tree.range(17, 19) == [17, 18, 19]
    table = ColumnarTable.from_rows(
        "large_bars",
        [
            {"symbol": "AAA" if index < 30 else "BBB", "timestamp": datetime(2026, 1, 1, tzinfo=UTC), "close": index}
            for index in range(300)
        ],
    )
    # Give the date range an actual span so it forms an indexable range predicate.
    table.columns["timestamp"] = [datetime(2026, 1, 1 + index % 20, tzinfo=UTC) for index in range(300)]
    table.create_btree_index("symbol", "timestamp")
    engine = Engine()
    engine.register(table)
    plan = engine.execute("SELECT symbol FROM large_bars WHERE symbol = 'AAA' AND timestamp >= '2026-01-10T00:00:00+00:00'").plan
    assert plan.strategy == "index_range_scan"


def test_date_only_timestamp_literal_inherits_utc() -> None:
    engine = Engine()
    engine.register(_bars())
    result = engine.execute("SELECT symbol FROM bars WHERE symbol = 'AAA' AND timestamp >= '2026-01-03'")
    assert result.rows == [{"symbol": "AAA"}]


def test_hash_join_and_group_by() -> None:
    engine = Engine()
    engine.register(_bars())
    engine.register(ColumnarTable.from_rows("companies", [{"symbol": "AAA", "sector": "Tech"}, {"symbol": "BBB", "sector": "Health"}]))
    joined = engine.hash_join("bars", "companies", "symbol", "symbol", (("sector", "right.sector"), ("volume", "left.volume")))
    summary = Engine.group_by(joined, ("sector",), {"total_volume": ("sum", "volume"), "rows": ("count", None)})
    assert sorted(summary, key=lambda item: item["sector"]) == [
        {"sector": "Health", "total_volume": 40, "rows": 1},
        {"sector": "Tech", "total_volume": 50, "rows": 2},
    ]


def test_desk_queries_use_columnar_engine() -> None:
    as_of = date(2026, 1, 3)
    engine = Engine()
    engine.register(
        ColumnarTable.from_rows(
            "daily_bars",
            [
                {"symbol": "AAA", "trading_date": date(2026, 1, 2), "open": Decimal(10), "close": Decimal(10), "volume": 100},
                {"symbol": "AAA", "trading_date": as_of, "open": Decimal("10.5"), "close": Decimal(11), "volume": 300},
                {"symbol": "BBB", "trading_date": date(2026, 1, 2), "open": Decimal(20), "close": Decimal(20), "volume": 100},
                {"symbol": "BBB", "trading_date": as_of, "open": Decimal(19), "close": Decimal(18), "volume": 300},
            ],
        )
    )
    engine.register(
        ColumnarTable.from_rows(
            "minute_bars",
            [
                {"symbol": "AAA", "ts": datetime(2026, 1, 3, 14, 30, tzinfo=UTC), "close": Decimal("10.5"), "vwap": Decimal("10.4"), "volume": 50},
                {"symbol": "AAA", "ts": datetime(2026, 1, 3, 14, tzinfo=UTC), "close": Decimal(99), "vwap": Decimal(99), "volume": 50},
            ],
        )
    )
    engine.register(ColumnarTable.from_rows("companies", [{"symbol": "AAA", "sector": "Tech"}, {"symbol": "BBB", "sector": "Financial"}]))
    results = run_desk_queries(engine, as_of)
    assert results["01_returns"][0]["symbol"] == "AAA"
    assert results["05_sector_performance"][0]["sector"] == "Tech"
    assert results["04_vwap"][0]["session_vwap"] == Decimal("10.40")
