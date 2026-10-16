from datetime import date
from decimal import Decimal

from market_brief import ingest


def test_detects_adjustment_change_in_refreshed_daily_bar(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest,
        "query",
        lambda *_: [
            {
                "symbol": "AAA",
                "trading_date": date(2026, 10, 15),
                "open": Decimal(10),
                "high": Decimal(11),
                "low": Decimal(9),
                "close": Decimal(10),
                "volume": 100,
            }
        ],
    )
    records = [{"symbol": "AAA", "t": "2026-10-15T00:00:00+00:00", "o": 5, "h": 5.5, "l": 4.5, "c": 5, "v": 200}]
    assert ingest._adjustment_changed_symbols(records) == {"AAA"}


def test_ignores_price_difference_below_postgres_numeric_precision(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest,
        "query",
        lambda *_: [
            {
                "symbol": "AAA",
                "trading_date": date(2026, 10, 15),
                "open": Decimal("171.234568"),
                "high": Decimal("171.234568"),
                "low": Decimal("171.234568"),
                "close": Decimal("171.234568"),
                "volume": 100,
            }
        ],
    )
    records = [
        {
            "symbol": "AAA", "t": "2026-10-15T00:00:00+00:00", "o": 171.23456789,
            "h": 171.23456789, "l": 171.23456789, "c": 171.23456789, "v": 100,
        }
    ]
    assert ingest._adjustment_changed_symbols(records) == set()


def test_adjustment_repair_starts_at_stored_backfill_boundary(monkeypatch) -> None:
    monkeypatch.setattr(
        ingest,
        "query",
        lambda *_: [{"symbol": "AAA", "start_date": date(2025, 10, 15)}],
    )
    calls: list[tuple] = []
    monkeypatch.setattr(
        ingest.alpaca,
        "bars",
        lambda symbols, timeframe, start, end: calls.append((symbols, timeframe, start, end)) or [],
    )
    assert ingest._repair_adjusted_daily({"AAA"}, date(2026, 10, 15)) == []
    assert calls == [(["AAA"], "1Day", date(2025, 10, 15), date(2026, 10, 16))]


def test_new_symbols_are_loaded_before_bar_upserts(monkeypatch) -> None:
    monkeypatch.setattr(ingest, "query", lambda *_: [{"symbol": "AAA"}])
    added: list[list[str]] = []
    monkeypatch.setattr(ingest, "upsert_companies", lambda symbols: added.append(list(symbols)) or len(symbols))
    assert ingest._ensure_companies(["AAA", "BBB"]) == 1
    assert added == [["BBB"]]
