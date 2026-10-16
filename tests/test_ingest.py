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


def test_new_symbols_are_loaded_before_bar_upserts(monkeypatch) -> None:
    monkeypatch.setattr(ingest, "query", lambda *_: [{"symbol": "AAA"}])
    added: list[list[str]] = []
    monkeypatch.setattr(ingest, "upsert_companies", lambda symbols: added.append(list(symbols)) or len(symbols))
    assert ingest._ensure_companies(["AAA", "BBB"]) == 1
    assert added == [["BBB"]]
